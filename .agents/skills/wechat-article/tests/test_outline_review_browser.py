"""Optional Chromium checks with loopback transport and no actual chat submission."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest

from test_jiuwenswarm_feedback import CHAPTER_TITLE, SECTION_NOTE, section_review
from render_outline_review import render, replace_current
from serve_outline_review import ReviewServer

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Optional Playwright dependency is unavailable")
class OutlineBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        playwright = sync_playwright().start()
        cls.addClassCleanup(playwright.stop)
        if not Path(playwright.chromium.executable_path).is_file():
            raise unittest.SkipTest("Optional Playwright Chromium is unavailable")
        cls.browser = playwright.chromium.launch()
        cls.addClassCleanup(cls.browser.close)

    @patch("serve_outline_review.subprocess.run", return_value=SimpleNamespace(returncode=0))
    def test_c1_input_survives_disconnect_and_confirmation_shows_queued(self, run):
        with TemporaryDirectory() as folder:
            review = section_review()
            source = Path(folder) / "current.json"
            replace_current(source, json.dumps(review))
            with ReviewServer(review, "test", "local-test-thread", source=source) as server:
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    context = self.browser.new_context(permissions=["clipboard-read", "clipboard-write"])
                    page = context.new_page()
                    page.goto(server.url)
                    note = page.locator('[data-section-id="C1"] textarea')
                    note.fill(SECTION_NOTE)
                    page.reload()
                    expect(note).to_have_value(SECTION_NOTE)
                    page.route("**/current", lambda route: route.abort())
                    expect(page.locator("[data-delivery-status]")).to_contain_text("本机反馈服务已断开", timeout=9000)
                    expect(note).to_have_value(SECTION_NOTE)
                    page.locator("[data-copy-draft]").click()
                    expect(page.locator("[data-copy-status]")).to_contain_text("已复制")
                    copied = json.loads(page.evaluate("navigator.clipboard.readText()"))
                    self.assertEqual(copied["decisions"], [{"id": "C1", "decision": "revise", "value": SECTION_NOTE}])
                    run.assert_not_called()
                    page.unroute("**/current")
                    latest = {**review, "review_id": "jiuwenswarm-ext-sections-r42"}
                    replace_current(source, json.dumps(latest))
                    expect(page.locator("[data-refresh-review]")).to_be_visible(timeout=9000)
                    expect(note).to_have_value(SECTION_NOTE)
                    page.locator("[data-refresh-review]").click()
                    expect(page.locator(f"#outline-review-{latest['review_id']}")).to_be_visible()
                    expect(note).to_have_value("")
                    page.get_by_role("button", name="确认", exact=True).click()
                    expect(page.locator("[data-delivery-status]")).to_have_text("确认结果已提交，等待当前对话处理。")
                    run.assert_called_once()
                    sent = json.loads(run.call_args.args[0][-1])
                    self.assertEqual(sent["decisions"], [{"id": "C1", "decision": "accept"}])
                    context.close()
                finally:
                    server.shutdown()
                    thread.join()

    def test_final_outline_anchors_and_copy_in_standalone_browser_at_two_widths(self):
        note = "文章标题改为“Agent 也能「心想事成」？openJiuwen 发布 RSI 原生 AgentOS，让 Agent自由变身，持续迭代！”"
        review = {"review_id": "jiuwenswarm-ext-final-r7", "stage": "final",
                  "markdown": f"# 文章标题\n\n全文导语。\n\n## {CHAPTER_TITLE}\n\n第一节。\n\n"
                              "## 认识 JiuwenSwarm 扩展包\n\n**章导语概述**　先说创建、使用和回退。\n\n### 3.1 和 Agent 对话"}
        with TemporaryDirectory() as folder:
            path = Path(folder) / "outline.html"
            path.write_text(render(review, standalone=True), encoding="utf-8")
            for width in (1440, 390):
                with self.subTest(width=width):
                    page = self.browser.new_page(viewport={"width": width, "height": 850})
                    try:
                        page.goto(path.as_uri())
                        expect(page.locator("[data-final-fields] textarea")).to_be_visible()
                        page.locator("[data-final-fields] textarea").fill(note)
                        directory = page.locator("[data-title-outline]")
                        if directory.get_attribute("open") is None:
                            directory.locator("summary").click()
                        for name in ("导语", "章节导语", "3.1 和 Agent 对话"):
                            link = directory.get_by_role("link", name=name, exact=True)
                            expect(link).to_be_visible()
                            target = link.get_attribute("href")
                            self.assertEqual(page.locator(target).count(), 1)
                        directory.get_by_role("link", name="章节导语", exact=True).click()
                        self.assertTrue(page.evaluate("location.hash.length > 1"))
                        expect(page.locator("[data-final-fields] textarea")).to_have_value(note)
                        page.locator("[data-copy-draft]").click()
                        expect(page.locator("[data-fallback]")).to_be_visible()
                        feedback = json.loads(page.locator("[data-fallback] textarea").input_value())
                        self.assertEqual(feedback["decisions"], [{"id": "outline", "decision": "revise", "value": note}])
                        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
                    finally:
                        page.close()


if __name__ == "__main__":
    unittest.main()
