"""Offline behavioral fixtures. All user replies in these fixtures are synthetic test data."""
import copy
import base64
import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import uuid
import zlib
from pathlib import Path

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import article_state as state
import article_workflow as workflow

AT = "2026-11-08T18:00:00+08:00"


def evidence(message="测试用户明确确认采用", kind="user"):
    return {"kind": kind, "message": message, "at": AT}


def png(color=b"\x20\x40\x60"):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    return state.PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x00" + color)) + chunk(b"IEND", b"")


def jpeg():
    # Actual 1x1 JPEG; no image library is required by the test suite.
    return base64.b64decode('/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFAEBAAAAAAAAAAAAAAAAAAAABf/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AJyATHP/2Q==')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render(units):
    return "# 测试文章\n\n" + "\n\n".join(f"<!-- section:{name} -->\n{content}\n<!-- /section:{name} -->" for name, content in units.items()) + "\n"


def image(root, ident, title, role="body", sections=None):
    name = f"{ident}_{title}_v001"
    path = root / f"article/assets/{name}.png"
    path.write_bytes(png())
    source_files = []
    if role == "body":
        source = root / f"article/assets/{name}.svg"
        source.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>', encoding="utf-8")
        source_files.append({"file": "assets/" + source.name, "sha256": state.digest(source.read_bytes())})
    return {"id": ident, "type": "image", "role": role, "title": title,
            "section_ids": sections if sections is not None else ["main-01"], "revision": "v001",
            "file": "assets/" + path.name, "url": None, "sha256": state.digest(path.read_bytes()),
            "source_files": source_files, "status": "approved", "adoption": evidence(),
            "filename_verified": True, "verified_at": AT, "canonical_name": path.name}


def make_article(root):
    for name in ["refs", "outline", "article/assets"]:
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "refs/source.py").write_text("def task(value):\n    return value\n", encoding="utf-8")
    (root / "outline/outline-v001.md").write_text("# 测试文章\n\n导语与整体介绍。\n", encoding="utf-8")
    body_image = image(root, "IMG-01", "整体架构")
    cover = image(root, "IMG-02", "发布封面", "cover", [])
    units = {"lead": "这是一份离线测试导语。", "main-01": "## 整体介绍\n\n根据测试源码说明任务。\n\n![IMG-01 整体架构](assets/IMG-01_整体架构_v001.png)\n\n图 IMG-01：整体架构"}
    progress = {"schema_version": 3, "session_id": "fixture-session", "is_active": True,
                "phase": "ready_to_archive", "outline_version": "v001", "based_on_article_version": None,
                "archived_article_version": None, "finalized_article_version": None, "completion_basis": None,
                "working_file": "article-working.md", "sections": [],
                "sources": [{"id": "code-1", "kind": "code", "path": "refs/source.py", "url": None,
                             "revision": "fixture-commit", "checked_at": AT, "note": "离线测试唯一来源；不是实际技术核查记录"}],
                "media": [body_image, cover], "pending_media": [], "candidates": []}
    for name, content in units.items():
        progress["sections"].append({"section_id": name, "title": "正文导语" if name == "lead" else "整体介绍",
            "status": "confirmed", "draft_ref": name + "测试第1轮", "source_refs": ["code-1"],
            "confirmation": {"draft_ref": name + "测试第1轮", "confirmed_at": AT, "user_message": "测试确认：此单元通过",
                             "outline_version_at_confirmation": "v001", "content_sha256": state.text_digest(content),
                             "media": [state.proof(m) for m in progress["media"] if name in m["section_ids"]]},
            "media_updates": [], "inheritance": None})
    metadata = {"schema_version": 3, "scenario": "openjiuwen", "latest_outline_version": "v001", "latest_article_version": None,
                "outlines": {"v001": {"file": "../outline/outline-v001.md", "title": "测试文章", "based_on": None,
                            "content_sha256": state.digest((root / "outline/outline-v001.md").read_bytes()),
                            "created_at": AT, "confirmation": {"draft_ref": "测试完整大纲", "confirmed_at": AT,
                            "user_message": "测试确认：完整大纲通过"}, "change_summary": "离线测试数据"}},
                "articles": {}, "asset_maintenance": []}
    (root / "article/article-working.md").write_text(render(units), encoding="utf-8")
    write_json(root / "article/progress.json", progress)
    write_json(root / "article/metadata.json", metadata)
    return metadata, progress, units


def save(root, metadata, progress, units):
    write_json(root / "article/metadata.json", metadata)
    write_json(root / "article/progress.json", progress)
    (root / "article/article-working.md").write_text(render(units), encoding="utf-8")


def archive(root, metadata, progress, units):
    number = max((int(v[1:]) for v in metadata["articles"]), default=0) + 1
    version = f"v{number:03d}"
    body, spans = state.assemble(render(units))
    path = root / f"article/article-{version}.md"
    path.write_text(body, encoding="utf-8")
    snapshots = [{**copy.deepcopy(s), "span": spans[s["section_id"]]} for s in progress["sections"]]
    metadata["articles"][version] = {"record_schema_version": 3, "file": path.name, "outline_version": "v001",
        "title": "测试文章", "based_on": metadata["latest_article_version"], "created_at": AT, "change_summary": "测试版本",
        "content_sha256": state.digest(path.read_bytes()), "chapter_confirmations": snapshots,
        "sources": copy.deepcopy(progress["sources"]), "media": copy.deepcopy(progress["media"]),
        "pending_media": copy.deepcopy(progress["pending_media"])}
    metadata["latest_article_version"] = version
    progress.update(phase="archived", is_active=False, archived_article_version=version)
    save(root, metadata, progress, units)
    return version


def add_pending_video(progress, units, *, defer=True):
    video = {"id": "VID-01", "type": "video", "role": "body", "title": "任务演示", "section_ids": ["main-01"],
             "revision": None, "file": None, "url": None, "sha256": None, "source_files": [], "status": "planned",
             "adoption": None, "filename_verified": False, "verified_at": None, "canonical_name": None}
    progress["media"].append(video)
    units["main-01"] += "\n\n【视频占位 VID-01：任务演示；待提供】"
    section = progress["sections"][1]
    section["confirmation"]["content_sha256"] = state.text_digest(units["main-01"])
    section["confirmation"]["media"].append(state.proof(video))
    progress["pending_media"].append({"media_id": "VID-01", "disposition": "deferred" if defer else "awaiting",
                                      "allow_in_final": False, "basis": evidence("测试：阶段稿保留视频占位") if defer else None})
    return video


class ArticleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wechat-workflow-test-")
        self.root = Path(self.temp.name) / "openjiuwen/test-article"
        self.metadata, self.progress, self.units = make_article(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def flush(self):
        save(self.root, self.metadata, self.progress, self.units)

    def assert_valid(self):
        self.assertEqual([], state.inspect(self.root)["errors"])

    def assert_invalid(self, fragment):
        self.assertIn(fragment, " ".join(state.inspect(self.root)["errors"]))

    def test_code_repository_can_be_the_only_source(self):
        self.assert_valid()

    def test_external_code_source_is_read_only_and_allowed(self):
        self.progress["sources"][0]["path"] = str(Path(self.temp.name))
        self.flush()
        self.assert_valid()

    def test_no_source_is_rejected(self):
        self.progress["sources"] = []
        self.flush()
        self.assert_invalid("sources")

    def test_pending_chapter_cannot_hide_pre_written_text(self):
        self.progress["phase"] = "waiting_section"
        self.progress["sections"][0].update(status="awaiting_confirmation", confirmation=None)
        self.progress["sections"][1].update(status="pending", confirmation=None)
        self.flush()
        self.assert_invalid("Pending section already contains")

    def test_later_section_cannot_skip_confirmation_gate(self):
        self.progress["phase"] = "waiting_section"
        self.progress["sections"][0].update(status="awaiting_confirmation", confirmation=None)
        self.flush()
        self.assert_invalid("before the earlier section")

    def test_fenced_markers_and_headings_do_not_split_sections(self):
        text = self.units["main-01"] + "\n\n```python\n## not a chapter\n<!-- section:fake -->\n```"
        title, units = state.extract_sections(render({"lead": self.units["lead"], "main-01": text}))
        self.assertEqual(["lead", "main-01"], list(units))
        self.assertEqual(state.text_digest(text), state.text_digest(units["main-01"]))

    def test_duplicate_markers_rejected(self):
        with self.assertRaisesRegex(state.StateError, "duplicate"):
            state.extract_sections(render(self.units) + "\n<!-- section:lead -->\n重复\n<!-- /section:lead -->")

    def test_confirmed_text_tamper_detected(self):
        self.units["lead"] += "悄悄新增一句。"
        self.flush()
        self.assert_invalid("Confirmed section text changed")

    def test_file_changed_even_after_registry_hash_updated(self):
        media = self.progress["media"][0]
        path = self.root / "article" / media["file"]
        path.write_bytes(png(b"\x80\x20\x10"))
        media["sha256"] = state.digest(path.read_bytes())
        self.flush()
        self.assert_invalid("media changed without")

    def test_truncated_png_not_accepted_as_png(self):
        media = self.progress["media"][0]
        path = self.root / "article" / media["file"]
        path.write_bytes(state.PNG_SIGNATURE + b"garbage")
        media["sha256"] = state.digest(path.read_bytes())
        self.flush()
        self.assert_invalid("real PNG")

    def test_caption_and_title_need_to_match_filename(self):
        self.units["main-01"] = self.units["main-01"].replace("图 IMG-01：整体架构", "图 IMG-01：另一个标题")
        self.progress["sections"][1]["confirmation"]["content_sha256"] = state.text_digest(self.units["main-01"])
        self.flush()
        self.assert_invalid("Visible caption/title differs")

    def test_bad_filename_detected(self):
        media = self.progress["media"][0]
        old = self.root / "article" / media["file"]
        new = old.with_name("wrong.png")
        old.rename(new)
        media["file"] = "assets/wrong.png"
        self.flush()
        self.assert_invalid("filename does not match")

    def test_unknown_phase_rejected_by_contract(self):
        self.progress["phase"] = "almost-done"
        self.flush()
        self.assert_invalid("almost-done")

    def test_deferred_image_needs_explicit_basis(self):
        media = self.progress["media"][0]
        old = state.proof(media)
        media.update(status="planned", file=None, sha256=None, revision=None, source_files=[], adoption=None)
        self.units["main-01"] = "## 整体介绍\n\n【图片占位 IMG-01：整体架构；待提供】"
        self.progress["sections"][1]["confirmation"].update(content_sha256=state.text_digest(self.units["main-01"]), media=[state.proof(media)])
        self.progress["pending_media"] = [{"media_id": "IMG-01", "disposition": "deferred", "allow_in_final": False, "basis": None}]
        self.flush()
        self.assert_invalid("Unresolved media choice")
        self.progress["pending_media"][0]["basis"] = evidence("测试：本章通过，图片暂留占位")
        self.flush()
        self.assert_valid()

    def test_video_waiting_does_not_block_confirmed_chapters(self):
        add_pending_video(self.progress, self.units, defer=False)
        self.progress["phase"] = "waiting_media"
        self.flush()
        self.assert_valid()

    def test_stage_placeholder_does_not_automatically_allow_finalization(self):
        add_pending_video(self.progress, self.units)
        version = archive(self.root, self.metadata, self.progress, self.units)
        self.progress.update(phase="finalized", finalized_article_version=version, completion_basis=evidence("测试最终任务完成", "task_completion"))
        self.flush()
        self.assert_invalid("not approved as a final placeholder")

    def test_add_video_after_archive_creates_new_body_and_keeps_old_bytes(self):
        video = add_pending_video(self.progress, self.units)
        for key in ["filename_verified", "verified_at", "canonical_name"]:
            video.pop(key)
        first = archive(self.root, self.metadata, self.progress, self.units)
        first_path = self.root / f"article/article-{first}.md"
        old_bytes = first_path.read_bytes()
        before_text = self.units["main-01"]
        before = state.text_digest(before_text)
        video.update(revision="v001", url="https://example.test/VID-01_任务演示_v001.mp4", status="approved",
                     adoption=evidence("测试：采用所提供视频"), filename_verified=True, verified_at=AT,
                     canonical_name="VID-01_任务演示_v001.mp4")
        self.units["main-01"] = self.units["main-01"].replace("【视频占位 VID-01：任务演示；待提供】", "[视频 VID-01：任务演示](https://example.test/VID-01_任务演示_v001.mp4)")
        self.progress["sections"][1]["media_updates"].append({"kind": "adopt", "before_sha256": before,
            "after_sha256": state.text_digest(self.units["main-01"]), "media": state.proof(video), "basis": evidence("测试：采用此视频"),
            "replacements": [{"before": "【视频占位 VID-01：任务演示；待提供】", "after": "[视频 VID-01：任务演示](https://example.test/VID-01_任务演示_v001.mp4)",
                              "after_start": self.units["main-01"].index("[视频 VID-01：")}]} )
        self.progress["pending_media"] = []
        self.progress.update(phase="ready_to_archive", is_active=True, based_on_article_version=first, archived_article_version=None)
        self.flush()
        self.assert_valid()
        second = archive(self.root, self.metadata, self.progress, self.units)
        self.assertEqual("v002", second)
        self.assertEqual(old_bytes, first_path.read_bytes())
        self.assert_valid()

    def test_cleanup_preview_keeps_cover_svg_and_confirmed_outline_picture(self):
        assets = self.root / "article/assets"
        (assets / "unused.png").write_bytes(png())
        (assets / "outline-only.png").write_bytes(png())
        outline = self.root / "outline/outline-v001.md"
        outline.write_text(outline.read_text(encoding="utf-8") + "\n![参考图](../article/assets/outline-only.png)\n", encoding="utf-8")
        self.metadata["outlines"]["v001"]["content_sha256"] = state.digest(outline.read_bytes())
        archive(self.root, self.metadata, self.progress, self.units)
        before = {p: state.digest(p.read_bytes()) for p in self.root.rglob("*") if p.is_file()}
        plan = workflow.stage_unused(self.root)
        self.assertTrue(plan["read_only"])
        self.assertEqual(["article/assets/unused.png"], [p["source"] for p in plan["moves"]])
        self.assertIn("article/assets/IMG-02_发布封面_v001.png", plan["protected"])
        self.assertIn("article/assets/IMG-01_整体架构_v001.svg", plan["protected"])
        self.assertEqual(before, {p: state.digest(p.read_bytes()) for p in self.root.rglob("*") if p.is_file()})

    def test_stage_moves_only_unused_images_and_records_results(self):
        archive(self.root, self.metadata, self.progress, self.units)
        path = self.root / "article/assets/unused.png"
        path.write_bytes(png())
        result = workflow.stage_unused(self.root, apply=True)
        self.assertFalse(path.exists())
        self.assertTrue((self.root / result["moved"][0]).is_file())
        self.assertEqual(["planned", "completed"], [e["status"] for e in state.read_json(self.root / "article/metadata.json")["asset_maintenance"]])
        self.assert_valid()

    def test_staging_cannot_run_while_writing(self):
        with self.assertRaisesRegex(state.StateError, "only after"):
            workflow.stage_unused(self.root, apply=True)

    def test_clean_temp_refuses_stage_version(self):
        archive(self.root, self.metadata, self.progress, self.units)
        with self.assertRaisesRegex(state.StateError, "finalized"):
            workflow.clean_temp(self.root, apply=True)

    def finalize(self):
        self.progress = state.read_json(self.root / "article/progress.json")
        version = self.progress["archived_article_version"]
        self.progress.update(phase="finalized", finalized_article_version=version, completion_basis=evidence("测试：明确最终成稿任务已完成", "task_completion"))
        write_json(self.root / "article/progress.json", self.progress)

    def test_final_cleanup_handles_generated_candidate_inventory(self):
        archive(self.root, self.metadata, self.progress, self.units)
        (self.root / "article/assets/unused.png").write_bytes(png())
        workflow.stage_unused(self.root, apply=True)
        candidate = self.root / ".tmp/candidates/tool-variant.png"
        candidate.parent.mkdir(parents=True)
        candidate.write_bytes(png())
        self.progress["candidates"] = [{"file": "../.tmp/candidates/tool-variant.png", "sha256": state.digest(candidate.read_bytes()), "origin": "测试绘图工具输出副本"}]
        write_json(self.root / "article/progress.json", self.progress)
        self.finalize()
        preview = workflow.clean_temp(self.root)
        self.assertEqual(2, len(preview["candidates"]))
        self.assertTrue(candidate.exists())
        result = workflow.clean_temp(self.root, apply=True)
        self.assertEqual(2, len(result["deleted"]))
        self.assertFalse((self.root / ".tmp").exists())
        self.assert_valid()

    def test_unknown_temp_file_blocks_entire_delete_batch(self):
        archive(self.root, self.metadata, self.progress, self.units)
        temp = self.root / ".tmp"
        temp.mkdir()
        unknown = temp / "unknown.txt"
        unknown.write_text("unknown", encoding="utf-8")
        self.finalize()
        with self.assertRaisesRegex(state.StateError, "Unknown/protected"):
            workflow.clean_temp(self.root, apply=True)
        self.assertTrue(unknown.exists())

    def test_managed_paths_cannot_escape_root(self):
        with self.assertRaisesRegex(state.StateError, "escapes"):
            state.inside(self.root, self.root / "article", "../../outside.png")

    def test_symlink_target_is_not_followed(self):
        link = self.root / "article/assets/external"
        try:
            link.symlink_to(Path(self.temp.name), target_is_directory=True)
        except OSError as exc:
            if os.name != "nt":
                self.skipTest("Symlink privilege unavailable: " + str(exc))
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), self.temp.name], capture_output=True)
            if result.returncode:
                self.skipTest("Neither symbolic link nor junction can be created")
        with self.assertRaisesRegex(state.StateError, "Link/junction"):
            state.inside(self.root, self.root / "article", "assets/external/file.png")

    def transaction(self, *, valid=True):
        token = uuid.uuid4().hex
        entries = []
        changed = render(self.units).replace("离线测试导语", "修订导语")
        prospective = copy.deepcopy(self.progress)
        if valid:
            _, sections = state.extract_sections(changed)
            prospective["sections"][0]["confirmation"].update(content_sha256=state.text_digest(sections["lead"]), user_message="测试确认：修订导语通过")
        for name, data in [("article-working.md", changed.encode("utf-8")),
                           ("progress.json", json.dumps(prospective, ensure_ascii=False).encode("utf-8"))]:
            target = self.root / "article" / name
            pending = target.with_name("." + name + ".pending-" + token)
            pending.write_bytes(data)
            entries.append({"target": target.relative_to(self.root).as_posix(), "pending": pending.relative_to(self.root).as_posix(),
                            "before_sha256": state.digest(target.read_bytes()), "after_sha256": state.digest(data)})
        write_json(self.root / "article/transaction.json", {"schema_version": 1, "transaction_id": token, "files": entries})
        return entries

    def test_interrupted_two_file_save_recovers_without_approval_changes(self):
        entries = self.transaction()
        (self.root / entries[0]["pending"]).replace(self.root / entries[0]["target"])
        expected = (self.root / entries[1]["pending"]).read_bytes()
        preview = workflow.recover(self.root)
        self.assertTrue(preview["read_only"])
        self.assertTrue((self.root / "article/transaction.json").exists())
        workflow.recover(self.root, apply=True)
        self.assertFalse((self.root / "article/transaction.json").exists())
        self.assertEqual(expected, (self.root / "article/progress.json").read_bytes())
        self.assert_valid()

    def test_recovery_will_not_overwrite_external_work_edit(self):
        self.transaction()
        target = self.root / "article/article-working.md"
        target.write_text("external edit", encoding="utf-8")
        with self.assertRaisesRegex(state.StateError, "outside transaction"):
            workflow.recover(self.root, apply=True)
        self.assertEqual("external edit", target.read_text(encoding="utf-8"))

    def test_recovery_reconciles_a_move_finished_before_logging_result(self):
        archive(self.root, self.metadata, self.progress, self.units)
        source = self.root / "article/assets/unused.png"
        target = self.root / ".tmp/images/interrupted/unused.png"
        source.write_bytes(png())
        event = {"operation_id": "test-operation", "batch_id": "test-batch", "action": "move", "article_version": "v001",
                 "source": source.relative_to(self.root).as_posix(), "target": target.relative_to(self.root).as_posix(),
                 "sha256": state.digest(source.read_bytes()), "reason": "测试中断"}
        workflow.asset_event(self.root, event, "planned")
        target.parent.mkdir(parents=True)
        source.replace(target)
        result = workflow.recover(self.root, apply=True)
        self.assertEqual("completed", result["asset_operations"][0]["outcome"])
        self.assert_valid()

    def test_partial_edit_inherits_unchanged_text_without_new_confirmation(self):
        archive(self.root, self.metadata, self.progress, self.units)
        record = self.metadata["articles"]["v001"]
        lead = self.progress["sections"][0]
        lead.update(status="inherited", confirmation=None, source_refs=[],
                    inheritance={"article_version": "v001", **record["chapter_confirmations"][0]["span"]})
        self.progress.update(phase="ready_to_archive", is_active=True, based_on_article_version="v001", archived_article_version=None)
        self.flush()
        self.assert_valid()
        archive(self.root, self.metadata, self.progress, self.units)
        self.assert_valid()

    def test_active_session_cannot_be_replaced_by_a_different_session(self):
        candidate = copy.deepcopy(self.progress)
        candidate["session_id"] = "another-session"
        work_file = Path(self.temp.name) / "candidate.md"
        progress_file = Path(self.temp.name) / "candidate.json"
        work_file.write_text(render(self.units), encoding="utf-8")
        write_json(progress_file, candidate)
        with self.assertRaisesRegex(state.StateError, "Another authoring session"):
            workflow.save_work(self.root, work_file, progress_file, apply=True)

    def test_cli_check_is_read_only(self):
        before = {p: state.digest(p.read_bytes()) for p in self.root.rglob("*") if p.is_file()}
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "article_workflow.py"), "check", str(self.root)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, {p: state.digest(p.read_bytes()) for p in self.root.rglob("*") if p.is_file()})

    def test_successful_save_work_is_two_file_commit_and_preview_is_read_only(self):
        self.units["lead"] += "这是经测试用户确认的修改。"
        self.progress["sections"][0]["confirmation"].update(content_sha256=state.text_digest(self.units["lead"]), user_message="测试确认修改后的导语")
        work = Path(self.temp.name) / "candidate.md"
        progress = Path(self.temp.name) / "candidate.json"
        work.write_text(render(self.units), encoding="utf-8")
        write_json(progress, self.progress)
        previous = (self.root / "article/article-working.md").read_bytes()
        self.assertTrue(workflow.save_work(self.root, work, progress)["read_only"])
        self.assertEqual(previous, (self.root / "article/article-working.md").read_bytes())
        workflow.save_work(self.root, work, progress, apply=True)
        self.assertFalse((self.root / "article/transaction.json").exists())
        self.assert_valid()

    def test_reworking_first_chapter_does_not_force_unchanged_later_chapter_confirmation(self):
        archive(self.root, self.metadata, self.progress, self.units)
        self.progress.update(phase="waiting_section", is_active=True, based_on_article_version="v001", archived_article_version=None)
        self.units["lead"] += "本次修改导语，仍在等待确认。"
        self.progress["sections"][0].update(status="awaiting_confirmation", confirmation=None)
        self.flush()
        self.assert_valid()

    def test_wrong_section_media_mapping_is_detected(self):
        self.progress["media"][0]["section_ids"] = ["lead"]
        self.progress["sections"][0]["confirmation"]["media"] = [state.proof(self.progress["media"][0])]
        self.flush()
        self.assert_invalid("mapping differs")

    def test_unregistered_body_image_is_rejected(self):
        path = self.root / "article/assets/unregistered.png"
        path.write_bytes(png())
        self.units["lead"] += "\n\n![未登记图](assets/unregistered.png)"
        self.progress["sections"][0]["confirmation"]["content_sha256"] = state.text_digest(self.units["lead"])
        self.flush()
        self.assert_invalid("not in media inventory")

    def test_candidate_digest_change_blocks_deletion(self):
        archive(self.root, self.metadata, self.progress, self.units)
        candidate = self.root / ".tmp/candidates/variant.png"
        candidate.parent.mkdir(parents=True)
        candidate.write_bytes(png())
        self.progress["candidates"] = [{"file": "../.tmp/candidates/variant.png", "sha256": state.digest(candidate.read_bytes()), "origin": "测试候选"}]
        write_json(self.root / "article/progress.json", self.progress)
        self.finalize()
        candidate.write_bytes(png(b"\x90\x20\x40"))
        with self.assertRaisesRegex(state.StateError, "digest differs"):
            workflow.clean_temp(self.root, apply=True)
        self.assertTrue(candidate.exists())

    def test_reopened_work_cannot_reuse_old_finalization_marker(self):
        archive(self.root, self.metadata, self.progress, self.units)
        self.finalize()
        self.progress.update(phase="reopened", is_active=True)
        write_json(self.root / "article/progress.json", self.progress)
        self.assert_invalid("previous finalization marker")

    def test_reference_style_and_html_images_in_outlines_are_protected(self):
        assets = self.root / "article/assets"
        for name in ["html.png", "reference.png", "code-only.png"]:
            (assets / name).write_bytes(png())
        outline = self.root / "outline/outline-v001.md"
        outline.write_text('# 测试文章\n\n<img src="../article/assets/html.png">\n\n![图][ref]\n\n[ref]: ../article/assets/reference.png\n\n```markdown\n![代码中的图片](../article/assets/code-only.png)\n```\n', encoding="utf-8")
        self.metadata["outlines"]["v001"]["content_sha256"] = state.digest(outline.read_bytes())
        archive(self.root, self.metadata, self.progress, self.units)
        plan = workflow.plan_cleanup(self.root)
        self.assertEqual(["article/assets/code-only.png"], [m["source"] for m in plan["moves"]])

    def test_complete_examples_match_published_contract(self):
        examples = SCRIPTS.parent / "assets/examples"
        self.assertEqual([], state.schema_errors(state.read_json(examples / "progress.example.json"), "progress"))
        self.assertEqual([], state.schema_errors(state.read_json(examples / "metadata.example.json"), "metadata"))

    def test_unregistered_svg_dependency_blocks_cleanup(self):
        media = self.progress["media"][0]
        source = self.root / "article" / media["source_files"][0]["file"]
        dependency = self.root / "article/assets/embedded.png"
        dependency.write_bytes(png())
        source.write_text('<svg xmlns="http://www.w3.org/2000/svg"><image href="embedded.png"/></svg>', encoding="utf-8")
        media["source_files"][0]["sha256"] = state.digest(source.read_bytes())
        self.progress["sections"][1]["confirmation"]["media"] = [state.proof(media)]
        self.flush()
        self.assert_invalid("SVG dependency is not registered")

    def test_cli_preview_stage_and_final_cleanup_end_to_end(self):
        archive(self.root, self.metadata, self.progress, self.units)
        unused = self.root / "article/assets/unused.png"
        unused.write_bytes(png())
        def run(command, *flags):
            result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPTS / "article_workflow.py"), command, str(self.root), *flags], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            return json.loads(result.stdout)
        self.assertTrue(run("plan-cleanup")["read_only"])
        self.assertTrue(unused.exists())
        self.assertEqual(1, len(run("stage-unused", "--apply")["moved"]))
        self.finalize()
        self.assertEqual(1, len(run("clean-temp")["candidates"]))
        self.assertTrue((self.root / ".tmp").exists())
        self.assertEqual(1, len(run("clean-temp", "--apply")["deleted"]))
        self.assertFalse((self.root / ".tmp").exists())
        self.assertEqual([], run("check")["errors"])

    def test_media_revision_cannot_be_reused_after_title_change(self):
        archive(self.root, self.metadata, self.progress, self.units)
        old = self.progress["media"][0]
        replacement = image(self.root, "IMG-01", "新图标题")
        self.progress["media"][0] = replacement
        self.units["main-01"] = self.units["main-01"].replace("整体架构", "新图标题")
        section = self.progress["sections"][1]
        section["confirmation"].update(content_sha256=state.text_digest(self.units["main-01"]), media=[state.proof(replacement)])
        self.progress.update(phase="ready_to_archive", is_active=True, based_on_article_version="v001", archived_article_version=None)
        self.flush()
        self.assert_invalid("revision was reused")

    def test_media_update_cannot_cover_an_unconfirmed_prose_edit(self):
        section = self.progress["sections"][1]
        before = state.text_digest(self.units["main-01"])
        self.units["main-01"] += "\n\n新增未经确认的性能承诺。"
        section["media_updates"].append({"kind": "format", "before_sha256": before,
            "after_sha256": state.text_digest(self.units["main-01"]), "media": state.proof(self.progress["media"][0]),
            "basis": evidence("测试机械操作", "operation"), "replacements": []})
        self.flush()
        self.assert_invalid("outside its verified media replacements")

    def test_replacement_list_cannot_authorize_arbitrary_word_changes(self):
        original = self.units["main-01"]
        self.units["main-01"] = original.replace("说明任务", "宣称领先")
        section = self.progress["sections"][1]
        section["media_updates"].append({"kind": "format", "before_sha256": state.text_digest(original),
            "after_sha256": state.text_digest(self.units["main-01"]), "media": state.proof(self.progress["media"][0]),
            "basis": evidence("测试机械操作", "operation"),
            "replacements": [{"before": "说明任务", "after": "宣称领先", "after_start": self.units["main-01"].index("宣称领先")}]})
        self.flush()
        self.assert_invalid("changes ordinary prose")

    def test_pure_media_path_repair_needs_no_new_section_confirmation(self):
        media = self.progress["media"][0]
        original = self.units["main-01"]
        old_path = media["file"]
        new_file = self.root / "article/assets/normalized" / Path(old_path).name
        new_file.parent.mkdir()
        new_file.write_bytes((self.root / "article" / old_path).read_bytes())
        media["file"] = "assets/normalized/" + new_file.name
        self.units["main-01"] = original.replace(old_path, media["file"])
        confirmation = copy.deepcopy(self.progress["sections"][1]["confirmation"])
        self.progress["sections"][1]["media_updates"].append({"kind": "format", "before_sha256": state.text_digest(original),
            "after_sha256": state.text_digest(self.units["main-01"]), "media": state.proof(media),
            "basis": evidence("测试：执行不改变内容的引用修复", "operation"),
            "replacements": [{"before": old_path, "after": media["file"], "after_start": self.units["main-01"].index(media["file"])}]})
        self.flush()
        self.assert_valid()
        self.assertEqual(confirmation, self.progress["sections"][1]["confirmation"])

    def test_archived_outline_change_detected_even_when_title_is_unchanged(self):
        outline = self.root / "outline/outline-v001.md"
        outline.write_text(outline.read_text(encoding="utf-8") + "擅自改动已确认安排。", encoding="utf-8")
        self.assert_invalid("Archived outline bytes changed")

    def test_self_inheritance_cannot_bypass_section_confirmation(self):
        archive(self.root, self.metadata, self.progress, self.units)
        section = self.metadata["articles"]["v001"]["chapter_confirmations"][0]
        section.update(status="inherited", confirmation=None,
                       inheritance={"article_version": "v001", **section["span"]})
        write_json(self.root / "article/metadata.json", self.metadata)
        self.assert_invalid("earlier real baseline")

    def test_task_completion_cannot_authorize_deferred_media(self):
        add_pending_video(self.progress, self.units)
        self.progress["pending_media"][0]["basis"] = evidence("测试程序判定完成", "task_completion")
        self.flush()
        self.assert_invalid("Unresolved media choice")

    def test_unknown_outline_cannot_be_used_as_confirmation_context(self):
        self.progress["sections"][0]["confirmation"]["outline_version_at_confirmation"] = "v999"
        self.flush()
        self.assert_invalid("unknown outline")

    def test_reusing_confirmation_with_new_outline_requires_only_applicability_note(self):
        target = self.root / "outline/outline-v002.md"
        target.write_text("# 测试文章\n\n测试：已确认的新结构，既有单元仍可使用。\n", encoding="utf-8")
        self.metadata["outlines"]["v002"] = {**copy.deepcopy(self.metadata["outlines"]["v001"]),
            "file": "../outline/outline-v002.md", "based_on": "v001", "content_sha256": state.digest(target.read_bytes())}
        self.metadata["latest_outline_version"] = self.progress["outline_version"] = "v002"
        self.flush()
        self.assert_invalid("applicability check")
        confirmations = [copy.deepcopy(s["confirmation"]) for s in self.progress["sections"]]
        for section in self.progress["sections"]:
            section["outline_revalidation"] = {"outline_version": "v002", "checked_at": AT, "note": "测试核对：本节内容及论证仍适用"}
        self.flush()
        self.assert_valid()
        self.assertEqual(confirmations, [s["confirmation"] for s in self.progress["sections"]])

    def test_inactive_media_registry_cannot_silently_diverge_from_archive(self):
        archive(self.root, self.metadata, self.progress, self.units)
        self.progress["media"][1]["role"] = "publishing"
        self.flush()
        self.assert_invalid("media inventory differs")

    def test_recovery_rejects_inconsistent_candidate_before_any_replacement(self):
        self.transaction(valid=False)
        paths = [self.root / "article/article-working.md", self.root / "article/progress.json"]
        before = {p: p.read_bytes() for p in paths}
        with self.assertRaisesRegex(state.StateError, "Recovery candidate is inconsistent"):
            workflow.recover(self.root, apply=True)
        self.assertEqual(before, {p: p.read_bytes() for p in paths})
        self.assertTrue((self.root / "article/transaction.json").exists())

    def test_recovery_preserves_a_recreated_candidate_at_a_previously_deleted_path(self):
        archive(self.root, self.metadata, self.progress, self.units)
        candidate = self.root / ".tmp/candidates/recreated.png"
        candidate.parent.mkdir(parents=True)
        original = png()
        event = {"operation_id": "historical-delete", "batch_id": "old-clean", "action": "delete", "article_version": "v001",
                 "source": candidate.relative_to(self.root).as_posix(), "target": None,
                 "sha256": state.digest(original), "reason": "测试：过去一次删除"}
        workflow.asset_event(self.root, event, "completed")
        candidate.write_bytes(png(b"\x90\x10\x80"))
        self.progress["candidates"] = [{"file": "../.tmp/candidates/recreated.png", "sha256": state.digest(candidate.read_bytes()), "origin": "测试：重新生成的候选"}]
        write_json(self.root / "article/progress.json", self.progress)
        workflow.recover(self.root, apply=True)
        restored = state.read_json(self.root / "article/progress.json")
        self.assertEqual(self.progress["candidates"], restored["candidates"])
        self.assertTrue(candidate.exists())

    def test_final_placeholder_permission_can_be_recorded_without_reapproving_body(self):
        add_pending_video(self.progress, self.units)
        version = archive(self.root, self.metadata, self.progress, self.units)
        self.progress["pending_media"][0].update(allow_in_final=True, basis=evidence("测试：最终交付保留此视频占位"))
        self.progress.update(phase="finalized", finalized_article_version=version,
                             completion_basis=evidence("测试：该版本正式完稿", "task_completion"))
        self.flush()
        self.assert_valid()

    def test_missing_chapter_image_cannot_wait_without_user_permission(self):
        media = self.progress["media"][0]
        media.update(status="planned", file=None, sha256=None, revision=None, source_files=[], adoption=None)
        self.units["main-01"] = "## 整体介绍\n\n【图片占位 IMG-01：整体架构；待提供】"
        self.progress["sections"][1]["confirmation"].update(content_sha256=state.text_digest(self.units["main-01"]), media=[state.proof(media)])
        self.progress.update(phase="waiting_media")
        self.progress["pending_media"] = [{"media_id": "IMG-01", "disposition": "awaiting", "allow_in_final": False, "basis": None}]
        self.flush()
        self.assert_invalid("Unresolved media choice")
        self.progress["pending_media"][0].update(disposition="deferred", basis=evidence("测试：本章通过，图暂留占位"))
        self.flush()
        self.assert_valid()

    def test_version_filename_must_match_registered_number(self):
        archive(self.root, self.metadata, self.progress, self.units)
        old = self.root / "article/article-v001.md"
        old.rename(old.with_name("wrong.md"))
        self.metadata["articles"]["v001"]["file"] = "wrong.md"
        write_json(self.root / "article/metadata.json", self.metadata)
        self.assert_invalid("Version file does not match")

    def test_version_baseline_cannot_refer_to_itself(self):
        self.metadata["outlines"]["v001"]["based_on"] = "v001"
        self.flush()
        self.assert_invalid("baseline must exist and precede")

    def test_outline_only_task_still_checks_title_mapping(self):
        self.metadata["outlines"]["v001"]["title"] = "另一标题"
        write_json(self.root / "article/metadata.json", self.metadata)
        (self.root / "article/progress.json").unlink()
        self.assert_invalid("Outline title differs")

    def test_reopened_work_clears_completion_basis_as_well_as_final_version(self):
        archive(self.root, self.metadata, self.progress, self.units)
        self.finalize()
        self.progress.update(phase="reopened", is_active=True, finalized_article_version=None)
        write_json(self.root / "article/progress.json", self.progress)
        self.assert_invalid("previous completion basis")

    def test_legacy_contracts_are_read_only_without_inventing_approvals(self):
        for version in [1, 2]:
            with self.subTest(version=version):
                self.metadata["schema_version"] = self.progress["schema_version"] = version
                self.flush()
                report = state.inspect(self.root)
                self.assertEqual([], report["errors"])
                self.assertTrue(report["warnings"])
                before = (self.root / "article/progress.json").read_bytes()
                with self.assertRaises(state.StateError):
                    workflow.recover(self.root, apply=True)
                self.assertEqual(before, (self.root / "article/progress.json").read_bytes())

    def test_contract_three_preserves_original_contract_two_record(self):
        archive(self.root, self.metadata, self.progress, self.units)
        old = self.metadata["articles"]["v001"]
        old["record_schema_version"] = 2
        snapshot = copy.deepcopy(old)
        self.progress.update(phase="reopened", is_active=True, based_on_article_version="v001", archived_article_version=None)
        section = self.progress["sections"][0]
        section.update(status="inherited", confirmation=None, inheritance={"article_version": "v001", **old["chapter_confirmations"][0]["span"]})
        self.flush()
        self.assert_valid()
        self.assertEqual(snapshot, state.read_json(self.root / "article/metadata.json")["articles"]["v001"])

    def test_malformed_recovery_journal_fails_without_changing_work(self):
        before = (self.root / "article/article-working.md").read_bytes()
        for journal in [[], {"schema_version": 1, "files": [None, None]},
                        {"schema_version": 1, "files": [{"target": []}, {}]}]:
            with self.subTest(journal=journal):
                write_json(self.root / "article/transaction.json", journal)
                with self.assertRaises(state.StateError):
                    workflow.recover(self.root, apply=True)
                self.assertEqual(before, (self.root / "article/article-working.md").read_bytes())

    def test_finalization_cannot_point_to_an_older_archive(self):
        first = archive(self.root, self.metadata, self.progress, self.units)
        archive(self.root, self.metadata, self.progress, self.units)
        self.progress.update(phase="finalized", archived_article_version=first, finalized_article_version=first,
                             completion_basis=evidence("测试：旧版本完成", "task_completion"))
        self.flush()
        self.assert_invalid("latest archived article")

    def test_local_media_can_omit_online_only_verification_fields(self):
        for media in self.progress["media"]:
            for key in ["filename_verified", "verified_at", "canonical_name"]:
                media.pop(key)
        archive(self.root, self.metadata, self.progress, self.units)
        self.assert_valid()
        self.assertEqual([], workflow.plan_cleanup(self.root)["moves"])

    def test_online_video_still_requires_naming_verification_fields(self):
        video = add_pending_video(self.progress, self.units)
        video.update(status="ready", revision="v001", url="https://example.test/demo.mp4")
        for key in ["filename_verified", "verified_at", "canonical_name"]:
            video.pop(key)
        self.progress["phase"] = "waiting_media"
        self.flush()
        self.assert_invalid("filename_verified")

    def test_jpeg_publishing_image_is_preserved_without_png_conversion(self):
        cover = self.progress["media"][1]
        path = self.root / "article" / cover["file"]
        path.unlink()
        path = path.with_suffix('.jpg')
        path.write_bytes(jpeg())
        cover.update(file="assets/" + path.name, canonical_name=path.name, sha256=state.digest(path.read_bytes()))
        archive(self.root, self.metadata, self.progress, self.units)
        self.assert_valid()
        self.assertIn(path.relative_to(self.root).as_posix(), workflow.plan_cleanup(self.root)["protected"])
        self.finalize()
        workflow.clean_temp(self.root, apply=True)
        self.assertTrue(path.exists())

    def test_jpeg_body_image_still_requires_actual_png_conversion(self):
        media = self.progress["media"][0]
        path = self.root / "article" / media["file"]
        path.write_bytes(jpeg())
        media["sha256"] = state.digest(path.read_bytes())
        self.flush()
        self.assert_invalid("real PNG")

    def test_compact_live_media_can_reuse_full_historical_snapshot(self):
        archive(self.root, self.metadata, self.progress, self.units)
        old = copy.deepcopy(self.metadata["articles"]["v001"])
        for media in self.progress["media"]:
            for key in ["filename_verified", "verified_at", "canonical_name"]:
                media.pop(key)
        self.flush()
        self.assert_valid()
        self.assertEqual(old, state.read_json(self.root / "article/metadata.json")["articles"]["v001"])

    def test_publishing_role_cannot_bypass_png_requirement_when_embedded(self):
        media = self.progress["media"][1]
        path = self.root / "article" / media["file"]
        path.unlink()
        path = path.with_suffix('.jpg')
        path.write_bytes(jpeg())
        media.update(file="assets/" + path.name, canonical_name=path.name,
                     sha256=state.digest(path.read_bytes()), section_ids=["lead"])
        self.units["lead"] += f'\n\n![{media["id"]} {media["title"]}]({media["file"]})\n\n图 {media["id"]}：{media["title"]}'
        self.progress["sections"][0]["confirmation"].update(
            content_sha256=state.text_digest(self.units["lead"]), media=[state.proof(media)])
        self.flush()
        self.assert_invalid("non-local/non-PNG image")

    def test_delivered_media_requires_canonical_positive_revision(self):
        media = self.progress["media"][1]
        for revision in [None, "v000", "v0001"]:
            with self.subTest(revision=revision):
                previous = self.root / "article" / media["file"]
                target = previous.with_name(f'{media["id"]}_{media["title"]}_{revision}.png')
                previous.rename(target)
                media.update(revision=revision, file="assets/" + target.name, canonical_name=target.name)
                self.flush()
                self.assert_invalid("Media revision is not canonical")

    def test_media_revision_can_grow_beyond_three_digits(self):
        media = self.progress["media"][1]
        previous = self.root / "article" / media["file"]
        target = previous.with_name(f'{media["id"]}_{media["title"]}_v1000.png')
        previous.rename(target)
        media.update(revision="v1000", file="assets/" + target.name, canonical_name=target.name)
        self.flush()
        self.assert_valid()


if __name__ == "__main__":
    unittest.main()
