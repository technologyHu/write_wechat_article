"""Portable feedback contract tests with synthetic user input."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_outline_feedback import FORMAT, load_feedback, validate_feedback
from render_outline_review import validate_review


class OutlineFeedbackTest(unittest.TestCase):
    def setUp(self):
        self.review = {
            "stage": "titles",
            "review_id": "example-titles-r2",
            "groups": [{"label": "文章", "items": [
                {"id": "T", "label": "标题", "options": [
                    {"title": "标题甲", "note": "从案例切入"},
                    {"title": "标题乙", "note": "强调原理"},
                ]},
                {"id": "C1", "label": "第一章", "options": [
                    {"title": "第一章甲", "note": "突出任务"},
                    {"title": "第一章乙", "note": "突出结果"},
                ]},
            ]}],
        }
        self.feedback = {
            "format": FORMAT,
            "review_id": self.review["review_id"],
            "stage": "titles",
            "decisions": [{"id": "T", "decision": "select", "value": "标题甲"}],
        }

    def test_partial_pasted_feedback_and_structure_only(self):
        fenced = "```json\n" + json.dumps(self.feedback, ensure_ascii=False) + "\n```"
        validate_feedback(self.review, load_feedback(fenced))
        validate_feedback(self.review, dict(self.feedback, decisions=[], structure_note="交换章节顺序"))

    def test_rejects_stale_round_and_unrecognized_decisions(self):
        for change in [
            {"review_id": "example-titles-r1"},
            {"stage": "final"},
            {"decisions": [{"id": "C9", "decision": "revise", "value": "重拟"}]},
            {"decisions": [{"id": "T", "decision": "select", "value": "未展示的标题"}]},
            {"decisions": self.feedback["decisions"] * 2},
        ]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_feedback(self.review, dict(self.feedback, **change))

    def test_final_review_requires_its_own_explicit_confirmation(self):
        review = {"review_id": "example-final-r1", "stage": "final", "markdown": "# 待确认稿"}
        feedback = dict(self.feedback, stage="final", review_id=review["review_id"])
        validate_feedback(review, dict(feedback, decisions=[{"id": "outline", "decision": "confirm"}]))
        with self.assertRaises(ValueError):
            validate_feedback(review, dict(feedback, decisions=[{"id": "outline", "decision": "accept"}]))

    def test_sections_keep_confirmed_content_available_for_revision(self):
        review = {
            "review_id": "example-sections-r2",
            "stage": "sections",
            "groups": [{"label": "导语与第一章", "items": [
                {"id": "T", "label": "导语", "body": "已确认导语", "confirmed": True},
                {"id": "C1", "label": "第一章", "body": "待确认内容", "confirmed": False},
            ]}],
        }
        feedback = dict(self.feedback, review_id=review["review_id"], stage="sections")
        validate_feedback(review, dict(feedback, decisions=[{"id": "C1", "decision": "accept"}]))
        validate_feedback(review, dict(feedback, decisions=[{"id": "T", "decision": "revise", "value": "调整导语"}]))
        with self.assertRaisesRegex(ValueError, "section is already confirmed"):
            validate_feedback(review, dict(feedback, decisions=[{"id": "T", "decision": "accept"}]))
        review["groups"][0]["items"][0]["confirmed"] = "true"
        with self.assertRaisesRegex(ValueError, "section confirmed must be a boolean"):
            validate_review(review)

    def test_individual_sections_require_a_separate_chapter_intro_choice(self):
        parent = {"id": "C3", "label": "第三章", "body": "主章概述", "chapter_intro": None}
        child = {"id": "C3.1", "label": "第一节", "body": "子章概述"}
        review = {
            "review_id": "example-sections-r3",
            "stage": "sections",
            "section_mode": "individual",
            "groups": [{"label": "第三章", "items": [parent, child]}],
        }
        feedback = dict(self.feedback, review_id=review["review_id"], stage="sections")
        chapter = {"id": "C3", "decision": "accept"}
        subsection = {"id": "C3.1", "decision": "accept"}
        for include in (True, False):
            validate_feedback(review, dict(feedback, decisions=[dict(chapter, chapter_intro=include)]))
        with self.assertRaisesRegex(ValueError, "include a chapter intro"):
            validate_feedback(review, dict(feedback, decisions=[chapter]))
        with self.assertRaisesRegex(ValueError, "before accepting a subsection"):
            validate_feedback(review, dict(feedback, decisions=[subsection]))
        with self.assertRaisesRegex(ValueError, "exactly one decision"):
            validate_feedback(review, dict(feedback, decisions=[dict(chapter, chapter_intro=True), subsection]))
        validate_feedback(review, dict(feedback, decisions=[{"id": "C3.1", "decision": "revise", "value": "调整概述"}]))
        parent.update(chapter_intro=False, confirmed=True)
        validate_feedback(review, dict(feedback, decisions=[subsection]))

    def test_chapter_intro_is_confirmed_before_subsections(self):
        parent = {"id": "C3", "label": "第三章", "body": "主章概述", "chapter_intro": True, "confirmed": True}
        intro = {"id": "C3-intro", "label": "第三章导语", "body": "章导语概述", "chapter_intro_for": "C3"}
        child = {"id": "C3.1", "label": "第一节", "body": "子章概述"}
        review = {
            "review_id": "example-sections-r4",
            "stage": "sections",
            "section_mode": "individual",
            "groups": [{"label": "第三章", "items": [parent, intro, child]}],
        }
        feedback = dict(self.feedback, review_id=review["review_id"], stage="sections")
        validate_feedback(review, dict(feedback, decisions=[{"id": "C3-intro", "decision": "accept"}]))
        subsection = dict(feedback, decisions=[{"id": "C3.1", "decision": "accept"}])
        with self.assertRaisesRegex(ValueError, "confirm the chapter intro"):
            validate_feedback(review, subsection)
        intro["confirmed"] = True
        validate_feedback(review, subsection)
        parent["chapter_intro"] = False
        with self.assertRaisesRegex(ValueError, "chapter intro must follow its parent"):
            validate_review(review)

    def test_sequential_title_round_has_one_item(self):
        sequential = dict(self.review, title_step={"index": 1, "total": 2})
        with self.assertRaises(ValueError):
            validate_review(sequential)
        group = self.review["groups"][0]
        sequential["groups"] = [dict(group, items=group["items"][:1])]
        validate_feedback(sequential, self.feedback)
        with self.assertRaises(ValueError):
            validate_feedback(sequential, dict(self.feedback, decisions=self.feedback["decisions"] + [
                {"id": "C1", "decision": "select", "value": "第一章甲"},
            ]))

    def test_title_outline_includes_current_item_without_accepting_other_titles(self):
        group = self.review["groups"][0]
        node = {"id": "C1", "label": "第一章", "title": "第一章甲", "confirmed": False}
        sequential = dict(
            self.review,
            groups=[dict(group, items=group["items"][1:])],
            title_step={"index": 2, "total": 2},
            title_outline={"id": "T", "label": "文章标题", "title": "标题甲",
                           "confirmed": True, "children": [node]},
        )
        validate_review(sequential)
        with self.assertRaises(ValueError):
            validate_feedback(sequential, self.feedback)
        node["id"] = "C2"
        with self.assertRaises(ValueError):
            validate_review(sequential)

    def test_chapter_feedback_can_be_submitted_without_selecting_a_title(self):
        root = {"id": "T", "label": "文章标题", "title": "标题甲", "confirmed": True}
        chapter = {"id": "C1", "label": "第一章", "title": "第一章甲", "confirmed": False}
        group = self.review["groups"][0]
        review = dict(self.review, title_outline=dict(root, children=[chapter]),
                      groups=[dict(group, items=group["items"][1:])], title_step={"index": 2, "total": 2})
        feedback = dict(self.feedback, decisions=[], chapter_feedback="第一章和后面的章节都突出技术机制。")
        validate_feedback(review, feedback)
        with self.assertRaises(ValueError):
            validate_feedback(self.review, feedback)
        with self.assertRaises(ValueError):
            validate_feedback(review, dict(feedback, chapter_feedback="  "))


if __name__ == "__main__":
    unittest.main()
