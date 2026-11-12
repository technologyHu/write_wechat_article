"""Replay selected feedback from the JiuwenSwarm article against isolated fixtures."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import test_article_workflow as fixture
from article_state import asset_link, extract_sections, numbered_placeholder, proof, text_digest
from article_workflow import commit_work, edit_caption, edit_section, load_state
from render_outline_review import render, validate_review, validate_title_revision
from validate_outline_feedback import FORMAT, feedback_targets


CHAPTER_TITLE = "让自己变身桌宠？JiuwenSwarm 靠的是 RSI 原生 AgentOS"
TITLE_PREFIX = "让自己变身桌宠？"
TITLE_BASE = "让自己变身桌宠？看 JiuwenSwarm 背后的 RSI 原生 AgentOS 如何支撑桌面扩展"
SECTION_NOTE = "整体优化一下导语大纲内容概述的逻辑"
CAPTION = "网关和服务端加载扩展包并注册处理函数，事件总线在业务事件触发时调用对应函数。"
VIDEO_TITLE = "通过自然语言生成并迭代 Token Weather 系统插件"


def review_feedback(review, *decisions):
    return {"format": FORMAT, "stage": review["stage"], "review_id": review["review_id"], "decisions": list(decisions)}


def section_review():
    return {"review_id": "jiuwenswarm-ext-sections-r40", "stage": "sections", "section_mode": "individual",
            "title_outline": {"id": "T", "label": "文章标题", "title": "Agent 也能「心想事成」？", "confirmed": True,
                              "children": [{"id": "C1", "label": "第一节", "title": CHAPTER_TITLE, "confirmed": True}]},
            "groups": [{"label": "导语", "items": [{"id": "T", "label": "导语", "confirmed": True,
                                               "body": "从 Agent 做任务发现缺少功能引出 RSI 原生 AgentOS。"}]},
                       {"label": CHAPTER_TITLE, "items": [{"id": "C1", "label": CHAPTER_TITLE,
                                                        "body": "随手聊两句时，想把工作台切换成桌宠。"}]}]}


class JiuwenSwarmOutlineFeedbackTests(unittest.TestCase):
    def test_previous_a_and_first_half_stay_locked(self):
        # r20 chose A as the basis; r21 explicitly asked to restore its first half.
        def titles(review_id, a, b):
            return {"review_id": review_id, "stage": "titles", "groups": [{"label": "第一节",
                    "items": [{"id": "C1", "label": "一 · 桌宠开场", "options": [
                        {"title": a, "note": "A"}, {"title": b, "note": "B"}]}]}]}

        previous = titles("jiuwenswarm-ext-titles-r20", TITLE_BASE,
                          "JiuwenSwarm 为什么能变身桌宠？背后是 RSI 原生 AgentOS 的桌面扩展能力")
        feedback = review_feedback(previous, {"id": "C1", "decision": "revise",
                                             "value": "不通顺，不朗朗上口，没有吸引力，再基于A继续优化"})
        self.assertEqual(feedback_targets(previous, feedback)[0]["id"], "C1")
        fixed = titles("jiuwenswarm-ext-titles-r22", CHAPTER_TITLE, TITLE_PREFIX + "JiuwenSwarm 背后有一套 RSI 原生 AgentOS")
        fixed["title_revision"] = {"review_id": previous["review_id"], "candidate": "A",
                                   "base_title": TITLE_BASE, "locked_prefix": TITLE_PREFIX}
        validate_review(fixed)
        validate_title_revision(fixed, previous)
        wrong = deepcopy(fixed)
        wrong["title_revision"]["candidate"] = "B"
        with self.assertRaisesRegex(ValueError, "selected previous candidate"):
            validate_title_revision(wrong, previous)
        # Historical r21 candidate A broke the wording lock.
        wrong = deepcopy(fixed)
        wrong["groups"][0]["items"][0]["options"][0]["title"] = "JiuwenSwarm 一键变桌宠，背后是 RSI 原生 AgentOS 的扩展能力"
        with self.assertRaisesRegex(ValueError, "locked wording"):
            validate_review(wrong)

    def test_c1_feedback_does_not_target_the_article_lead_and_chat_keeps_scope(self):
        review = section_review()
        feedback = review_feedback(review, {"id": "C1", "decision": "revise", "value": SECTION_NOTE})
        targets = feedback_targets(review, feedback)
        self.assertEqual(targets, [{"stage": "sections", "id": "C1", "label": CHAPTER_TITLE, "action": "revise"}])
        # User said「现在已经不需要通过网站来进行引导和确认了」.
        self.assertEqual(feedback_targets({**review, "channel": "chat"}, feedback), targets)
        with self.assertRaisesRegex(ValueError, "uses chat"):
            render({**review, "channel": "chat"}, standalone=True)


class JiuwenSwarmManuscriptFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="wechat-jiuwenswarm-feedback-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.meta, self.progress, self.units = fixture.make_article(self.root)
        article = self.root / "article"
        version = article / "v001"
        version.mkdir()
        (article / self.progress["working_file"]).rename(version / "article-working.md")
        (article / "assets").rename(version / "assets")
        self.progress["working_file"] = "v001/article-working.md"
        for item in self.progress["media"]:
            item["file"] = "v001/" + item["file"]
            for source in item["source_files"]:
                source["file"] = "v001/" + source["file"]
        for section in self.progress["sections"]:
            section["confirmation"]["media"] = [proof(item) for item in self.progress["media"]
                                                 if section["section_id"] in item["section_ids"]]
        self.working = article / self.progress["working_file"]

    def save_fixture(self):
        fixture.save(self.root, self.meta, self.progress, self.units)

    def add_confirmed(self, ident, title, text, reply, parent=None):
        original = deepcopy(self.progress["sections"][0])
        original.update(section_id=ident, title=title, draft_ref=ident + "-r1")
        original["confirmation"].update(draft_ref=original["draft_ref"], user_message=reply,
                                        content_sha256=text_digest(text))
        if parent:
            original["parent_section_id"] = parent
        self.progress["sections"].append(original)
        self.units[ident] = text

    def test_section_intro_and_subsections_can_be_confirmed_and_reopened_independently(self):
        self.add_confirmed("main-03", "认识 JiuwenSwarm 扩展包：从创建、使用到故障回退",
                           "## 认识 JiuwenSwarm 扩展包：从创建、使用到故障回退\n\n这里介绍创建、使用和故障回退。",
                           "第三节导语确认，继续给我看 3.1 节正文，直接在对话里确认。")
        self.add_confirmed("main-03-01", "3.1 和 Agent 对话，边写边调试你的第一个扩展包",
                           "### 3.1 和 Agent 对话，边写边调试你的第一个扩展包\n\n可以和 Agent 对话来创建和调试。",
                           "确认3.1内容", "main-03")
        old = '输入 `/extension install "扩展包路径"`。这里填的是 JiuwenSwarm 运行端能读取的 ZIP 文件的绝对路径。'
        self.add_confirmed("main-03-02", "3.2 扩展包怎么用？从安装到确认生效",
                           "### 3.2 扩展包怎么用？从安装到确认生效\n\n" + old,
                           "确认 3.2 内容，继续给我看 3.3 节正文，直接在对话里确认。", "main-03")
        self.add_confirmed("main-03-03", "3.3 扩展包出了问题，怎么回退到可用状态？",
                           "### 3.3 扩展包出了问题，怎么回退到可用状态？\n\n从存档点恢复系统插件配置。",
                           "确认 3.3 内容", "main-03")
        self.save_fixture()
        ident = "main-03-02"
        digest = text_digest(self.units[ident])
        replacement = "在 JiuwenSwarm 的对话框中使用 `/extension install`，即可安装本地扩展包。"
        original_metadata = (self.root / "article/metadata.json").read_bytes()
        preview = edit_section(self.root, ident, digest, "3.2-r2", text=replacement, old_text=old)
        self.assertTrue(preview["read_only"])
        self.assertFalse((self.working.parent / ".drafts").exists())
        with self.assertRaisesRegex(ValueError, "exactly once"):
            edit_section(self.root, ident, digest, "3.2-r2", text=replacement, old_text="这是全文导语")
        applied = edit_section(self.root, ident, digest, "3.2-r2", text=replacement, old_text=old, apply=True)
        _, current = load_state(self.root)
        after = extract_sections(self.working.read_text(encoding="utf-8"))[1]
        self.assertEqual(after, {**self.units, ident: self.units[ident].replace(old, replacement)})
        for previous, updated in zip(self.progress["sections"], current["sections"]):
            if previous["section_id"] == ident:
                self.assertIsNone(updated["confirmation"])
                self.assertEqual(updated["status"], "awaiting_confirmation")
            else:
                self.assertEqual(previous, updated)
        with self.assertRaisesRegex(ValueError, "changed since"):
            edit_section(self.root, ident, digest, "3.2-r3", text=replacement)
        # Replay「回到上一版」 against the exact saved section, leaving other approvals alone.
        restored = edit_section(self.root, ident, applied["after_sha256"], "3.2-r3",
                                restore_from=Path(applied["snapshot"]), apply=True)
        self.assertTrue(restored["restored_confirmation"])
        self.assertEqual(load_state(self.root)[1]["sections"], self.progress["sections"])
        self.assertEqual(extract_sections(self.working.read_text(encoding="utf-8"))[1], self.units)
        self.assertEqual((self.root / "article/metadata.json").read_bytes(), original_metadata)
        self.assertFalse((self.root / "article/v002").exists())

    def test_caption_deletion_preserves_title_asset_and_existing_approval(self):
        image = self.progress["media"][0]
        image["caption"] = {"number": 1, "title": "JIuwenSwarm扩展机制原理图", "description": CAPTION}
        label = "图1：JIuwenSwarm扩展机制原理图"
        picture = f"![{label}](<{asset_link(image['file'])}>)\n\n{label}"
        self.units["main-01"] = f"## 整体介绍\n\n{picture}\n\n{CAPTION}\n\n后续说明。"
        approved = self.progress["sections"][1]["confirmation"]
        approved.update(content_sha256=text_digest(self.units["main-01"]), media=[proof(image)])
        self.save_fixture()
        asset = self.root / "article" / image["file"]
        original_asset = asset.read_bytes()
        original_outline = (self.root / "outline/outline-v001.md").read_bytes()
        edit_caption(self.root, image["id"], f"删除“{CAPTION}”", remove_description=True, apply=True)
        _, result = load_state(self.root)
        self.assertEqual(result["sections"][1]["confirmation"], approved)
        self.assertEqual(result["sections"][1]["media_updates"][-1]["kind"], "caption")
        self.assertEqual(asset.read_bytes(), original_asset)
        self.assertEqual((self.root / "outline/outline-v001.md").read_bytes(), original_outline)
        self.assertEqual(extract_sections(self.working.read_text(encoding="utf-8"))[1]["main-01"],
                         f"## 整体介绍\n\n{picture}\n\n后续说明。")

    def test_real_video_feedback_adopts_only_the_available_placeholder_in_v001(self):
        old = "演示通过对话提出需求，生成 Token Weather 系统插件，再按反馈继续调整"
        video = {"id": "VID-02", "type": "video", "role": "body", "title": VIDEO_TITLE, "section_ids": ["main-01"],
                 "revision": None, "file": None, "url": None, "sha256": None, "source_files": [],
                 "status": "planned", "adoption": None, "caption": {"number": 2, "title": VIDEO_TITLE, "description": old}}
        placeholder = numbered_placeholder(video)
        self.units["main-01"] += "\n\n" + placeholder
        section = self.progress["sections"][1]
        section["confirmation"]["content_sha256"] = text_digest(self.units["main-01"])
        section["confirmation"]["media"].append(proof(video))
        self.progress["media"].append(video)
        pending = {**video, "id": "VID-08", "title": "新建会话时切换三种 Harness",
                   "caption": {"number": 9, "title": "新建会话时切换三种 Harness", "description": "待提供。"}}
        deferred = numbered_placeholder(pending)
        self.units["main-01"] += "\n\n" + deferred
        section["confirmation"]["content_sha256"] = text_digest(self.units["main-01"])
        section["confirmation"]["media"].append(proof(pending))
        self.progress["media"].append(pending)
        self.progress["pending_media"].append({"media_id": pending["id"], "disposition": "deferred",
                                              "allow_in_final": False, "basis": fixture.evidence("视频9先保留占位")})
        self.progress["phase"] = "waiting_media"
        self.save_fixture()
        media_dir = self.working.parent / "assets/videos"
        media_dir.mkdir()
        source = media_dir / "飞书20261110-005331.mp4"
        source.write_bytes(b"isolated media test fixture")
        target = media_dir / f"视频2_{VIDEO_TITLE}_v001.mp4"
        source.rename(target)
        basis = fixture.evidence("确认 3.3 内容，先帮我替换所有的视频占位，替换成已有的视频（还没有的可以先不替换），并优化和完善视频编号、视频标题和视频描述，视频编号都采用“视频1”类型的格式，图片编号都采用“图1”类似的格式")
        video.update(status="approved", adoption=basis, revision="v001", sha256=fixture.state.digest(target.read_bytes()),
                     file=target.relative_to(self.root / "article").as_posix())
        paragraph = f"[视频2：{VIDEO_TITLE}](<{asset_link(video['file'])}>)\n\n{old}。"
        before = self.units["main-01"]
        self.units["main-01"] = before.replace(placeholder, paragraph, 1)
        section["media_updates"].append({"kind": "adopt", "basis": basis, "media": proof(video),
                                         "before_sha256": text_digest(before), "after_sha256": text_digest(self.units["main-01"]),
                                         "replacements": [{"before": placeholder, "after": paragraph, "after_start": before.index(placeholder)}]})
        outline = (self.root / "outline/outline-v001.md").read_bytes()
        commit_work(self.root, fixture.render(self.units), self.progress, apply=True)
        text = "用自然语言向 Agent 提出需求，生成 Token Weather 系统插件，再根据试用反馈调整。"
        edit_caption(self.root, video["id"], "优化所有的视频描述，只是描述视频内容即可，不要说“演示xxx”",
                     description=text, apply=True)
        self.assertFalse(source.exists())
        self.assertTrue(target.exists())
        self.assertEqual((self.root / "outline/outline-v001.md").read_bytes(), outline)
        self.assertIn(f"\n\n{text}\n", self.working.read_text(encoding="utf-8"))
        self.assertIn(deferred, self.working.read_text(encoding="utf-8"))
        self.assertFalse(load_state(self.root)[1]["pending_media"][0]["allow_in_final"])
        self.assertFalse((self.root / "article/v002").exists())


if __name__ == "__main__":
    unittest.main()
