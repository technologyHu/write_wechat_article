"""Validate pasted or uploaded outline feedback against the current review JSON."""
import argparse
import json
from pathlib import Path
import sys

from render_outline_review import require_text, validate_review


FORMAT = "wechat-article-outline-feedback/v1"
ALLOWED_DECISIONS = {
    "titles": {"select", "custom", "revise"},
    "sections": {"accept", "revise"},
    "final": {"confirm", "revise"},
}


def validate_feedback(review, feedback):
    validate_review(review)
    stage = review["stage"]
    if feedback["format"] != FORMAT:
        raise ValueError("unsupported feedback format")
    if feedback["review_id"] != review["review_id"] or feedback["stage"] != stage:
        raise ValueError("feedback does not match the current review round and stage")
    if set(feedback) - {"format", "review_id", "stage", "decisions", "structure_note", "chapter_feedback"}:
        raise ValueError("feedback contains unknown fields")

    decisions = feedback["decisions"]
    if not isinstance(decisions, list):
        raise ValueError("decisions must be a list")
    if "structure_note" in feedback:
        if stage != "titles":
            raise ValueError("structure_note is only valid for title review")
        require_text(feedback["structure_note"])
    if "chapter_feedback" in feedback:
        if stage != "titles" or not (review.get("title_outline") or {}).get("children"):
            raise ValueError("chapter_feedback requires a title review with chapters")
        require_text(feedback["chapter_feedback"])
    if not decisions and "structure_note" not in feedback and "chapter_feedback" not in feedback:
        raise ValueError("feedback contains no decisions or notes")
    individual = review.get("section_mode") == "individual"
    if individual and len(decisions) != 1:
        raise ValueError("individual section review requires exactly one decision")

    if stage == "final":
        if len(decisions) != 1:
            raise ValueError("final review requires exactly one decision")
        items = {"outline": None}
    else:
        items = {item["id"]: item for group in review["groups"] for item in group["items"]}
    parents = {item["id"]: group["items"][0]
               for group in review["groups"] for item in group["items"]} if individual else {}
    intros = {item["chapter_intro_for"]: item for item in items.values()
              if "chapter_intro_for" in item} if individual else {}

    seen = set()
    for entry in decisions:
        item_id = entry["id"]
        if item_id not in items or item_id in seen:
            raise ValueError(f"unknown or repeated item ID: {item_id}")
        seen.add(item_id)
        decision = entry["decision"]
        if decision not in ALLOWED_DECISIONS[stage]:
            raise ValueError(f"{decision} is not valid for {stage}")
        if decision == "accept" and items[item_id].get("confirmed", False):
            raise ValueError(f"section is already confirmed: {item_id}")
        needs_value = decision not in ("accept", "confirm")
        expected_fields = {"id", "decision", "value"} if needs_value else {"id", "decision"}
        if individual and decision == "accept":
            parent = parents[item_id]
            intro = intros.get(parent["id"])
            if intro and item_id not in (parent["id"], intro["id"]) and not intro.get("confirmed", False):
                raise ValueError("confirm the chapter intro before accepting a subsection")
            if parent.get("chapter_intro", False) is None:
                if parent["id"] != item_id:
                    raise ValueError("confirm the chapter intro choice before accepting a subsection")
                expected_fields.add("chapter_intro")
                if type(entry.get("chapter_intro")) is not bool:
                    raise ValueError("confirm whether to include a chapter intro")
        if set(entry) != expected_fields:
            raise ValueError(f"unexpected fields for {item_id} decision {decision}")
        if not needs_value:
            continue
        value = entry["value"]
        require_text(value)
        if decision == "select" and not any(
            value == option["title"] for option in items[item_id]["options"]
        ):
            raise ValueError(f"selected title is not a candidate for {item_id}")
        if decision == "custom" and len(value.splitlines()) != 1:
            raise ValueError("a custom title must be a single line")


def load_feedback(source):
    source = source.strip()
    lines = source.splitlines()
    if len(lines) >= 3 and lines[0] in ("```", "```json") and lines[-1] == "```":
        source = "\n".join(lines[1:-1])
    return json.loads(source)


def feedback_targets(review, feedback):
    validate_feedback(review, feedback)
    stage = review["stage"]
    labels = {item["id"]: item["label"] for group in review.get("groups", []) for item in group["items"]}
    labels["outline"] = "完整大纲"
    return [{"stage": stage, "id": entry["id"], "label": labels[entry["id"]], "action": entry["decision"]}
            for entry in feedback["decisions"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path, help="JSON used to render the current review round")
    parser.add_argument("feedback", help="feedback JSON path or '-' for pasted stdin")
    parser.add_argument("--targets", action="store_true", help="return validated item scopes with the original feedback")
    args = parser.parse_args()
    try:
        review = json.loads(args.review.read_text(encoding="utf-8-sig"))
        source = (sys.stdin.buffer.read().decode("utf-8-sig") if args.feedback == "-"
                  else Path(args.feedback).read_text(encoding="utf-8-sig"))
        feedback = load_feedback(source)
        targets = feedback_targets(review, feedback)
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(1, f"Invalid feedback: {error}\n")
    output = {"feedback": feedback, "targets": targets} if args.targets else feedback
    sys.stdout.buffer.write((json.dumps(output, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
