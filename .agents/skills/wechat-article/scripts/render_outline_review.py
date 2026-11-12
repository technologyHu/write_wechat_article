"""Render one immutable review round as an HTML fragment or browser page."""
import argparse
import json
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
import webbrowser


TEMPLATES = Path(__file__).resolve().parents[1] / "assets/outlines"


def validate_review(review):
    stage = review["stage"]
    if stage not in ("titles", "sections", "final"):
        raise ValueError("stage must be titles, sections, or final")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", review["review_id"]):
        raise ValueError("review_id must use lowercase letters, digits, and hyphens")
    if review.get("channel", "html") not in {"html", "chat"}:
        raise ValueError("review channel must be html or chat")
    if "title_revision" in review and stage != "titles":
        raise ValueError("title_revision is only valid in the titles stage")
    individual = review.get("section_mode") == "individual"
    if "section_mode" in review and (stage != "sections" or not individual):
        raise ValueError("individual section mode requires the sections stage")
    step = review.get("title_step")
    if step is not None:
        if stage != "titles" or type(step["index"]) is not int or type(step["total"]) is not int:
            raise ValueError("title_step requires an integer index and total in the titles stage")
        if not 1 <= step["index"] <= step["total"]:
            raise ValueError("title_step index is outside the title sequence")
    outline = review.get("title_outline")
    outline_ids = validate_title_outline(outline) if outline is not None else None
    if stage == "final":
        require_text(review["markdown"])
        return

    groups = review["groups"]
    if not isinstance(groups, list) or not groups:
        raise ValueError("groups must be a nonempty list")
    seen = set()
    for group in groups:
        require_text(group["label"])
        items = group["items"]
        if not isinstance(items, list) or not items:
            raise ValueError("items must be a nonempty list")
        if individual and len(items) > 1 and "chapter_intro" not in items[0]:
            raise ValueError("a chapter with subsections needs a chapter_intro decision")
        for item in items:
            item_id = item["id"]
            if require_text(item_id) != item_id:
                raise ValueError("item IDs cannot have leading or trailing whitespace")
            require_text(item["label"])
            if item_id in seen:
                raise ValueError(f"duplicate item ID: {item_id}")
            seen.add(item_id)
            if stage == "sections":
                require_text(item["body"])
                if type(item.get("confirmed", False)) is not bool:
                    raise ValueError("section confirmed must be a boolean")
                if "chapter_intro" in item:
                    if not individual or len(items) < 2 or item is not items[0]:
                        raise ValueError("chapter_intro belongs to the parent of a chapter group")
                    intro = item["chapter_intro"]
                    if intro is not None and type(intro) is not bool:
                        raise ValueError("chapter_intro must be a boolean or null")
                    if intro is None and item.get("confirmed", False):
                        raise ValueError("confirmed chapters need a chapter_intro decision")
                if "chapter_intro_for" in item:
                    parent = items[0]
                    if (not individual or len(items) < 3 or item is not items[1]
                            or item["chapter_intro_for"] != parent["id"] or parent.get("chapter_intro") is not True):
                        raise ValueError("chapter intro must follow its parent chapter with an accepted intro choice")
                continue
            options = item["options"]
            if not isinstance(options, list) or len(options) not in (2, 3):
                raise ValueError(f"{item_id} needs two or three title candidates")
            titles = set()
            for option in options:
                titles.add(require_text(option["title"]))
                require_text(option["note"])
            if len(titles) != len(options):
                raise ValueError(f"{item_id} contains duplicate titles")
    if step is not None and len(seen) != 1:
        raise ValueError("a sequential title review must contain exactly one item")
    if step is not None and outline_ids is not None:
        if len(outline_ids) != step["total"] or not seen.issubset(outline_ids):
            raise ValueError("the title outline must include the full sequence and current item")
    if revision := review.get("title_revision"):
        if len(seen) != 1 or revision["candidate"] not in ("A", "B", "C"):
            raise ValueError("title revision must refer to one candidate in the previous round")
        if revision["review_id"] == review["review_id"]:
            raise ValueError("a title revision must have a new review ID")
        base = require_text(revision["base_title"])
        prefix, suffix = revision.get("locked_prefix", ""), revision.get("locked_suffix", "")
        options = groups[0]["items"][0]["options"]
        if any(not title.startswith(prefix) or not title.endswith(suffix)
               for title in [base, *(option["title"] for option in options)]):
            raise ValueError("title revision changed locked wording")


def validate_title_revision(review, previous):
    validate_review(previous)
    revision = review["title_revision"]
    if previous["stage"] != "titles" or previous["review_id"] != revision["review_id"]:
        raise ValueError("title revision refers to the wrong previous round")
    current_item = review["groups"][0]["items"][0]
    prior_item = next((item for group in previous["groups"] for item in group["items"]
                       if item["id"] == current_item["id"]), None)
    index = ord(revision["candidate"]) - ord("A")
    if prior_item is None or index >= len(prior_item["options"]) or prior_item["options"][index]["title"] != revision["base_title"]:
        raise ValueError("title revision does not match the selected previous candidate")
    if previous.get("title_outline") and review.get("title_outline"):
        def confirmed_titles(node):
            confirmed = {node["id"]: node["title"]} if node["confirmed"] else {}
            for child in node.get("children", []):
                confirmed.update(confirmed_titles(child))
            return confirmed

        before = confirmed_titles(previous["title_outline"])
        after = confirmed_titles(review["title_outline"])
        if any(after.get(ident) != title for ident, title in before.items() if ident != current_item["id"]):
            raise ValueError("title revision changed another confirmed title")


def validate_title_outline(root):
    seen = set()

    def visit(node, level):
        item_id = require_text(node["id"])
        if item_id in seen or level > 3:
            raise ValueError("the title outline requires unique IDs and at most three levels")
        seen.add(item_id)
        require_text(node["label"])
        require_text(node["title"])
        if type(node["confirmed"]) is not bool:
            raise ValueError("title outline confirmed must be a boolean")
        children = node.get("children", [])
        if not isinstance(children, list):
            raise ValueError("title outline children must be a list")
        for child in children:
            visit(child, level + 1)

    visit(root, 1)
    return seen


def require_text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected nonempty text")
    return value.strip()


def render(review, *, standalone=False, local_delivery=False):
    validate_review(review)
    if review.get("channel") == "chat":
        raise ValueError("This review uses chat; do not open or publish an HTML page")
    payload = json.dumps(review, ensure_ascii=False).replace("<", r"\u003c")
    fragment = (TEMPLATES / "outline-review.html").read_text(encoding="utf-8")
    fragment = fragment.replace("__REVIEW_ID__", review["review_id"]).replace("__REVIEW_DATA__", payload)
    if not standalone:
        return fragment
    page = (TEMPLATES / "outline-review-page.html").read_text(encoding="utf-8")
    page = page.replace("__REVIEW_ID__", review["review_id"])
    page = page.replace("__REVIEW_LOCAL_DELIVERY__", ' data-outline-delivery="local"' if local_delivery else "")
    return page.replace("__REVIEW_FRAGMENT__", fragment)


def replace_current(path, text):
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as temp:
            temporary = Path(temp.name)
            temp.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def register_review_outputs(paths, origin, *, version=None):
    if any(parent.name == ".tmp" and (parent.parent / "article").is_dir() for parent in paths[0].absolute().parents):
        from article_temp import record_generated
        record_generated(paths, origin, version=version)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="UTF-8 review JSON file or '-' for stdin")
    parser.add_argument("output", type=Path, help="new HTML output path")
    parser.add_argument("--standalone", action="store_true", help="write a self-contained browser page")
    parser.add_argument("--open-browser", action="store_true", help="write and open a standalone browser page")
    parser.add_argument("--publish-current", action="store_true", help="update the existing browser page and review JSON")
    parser.add_argument("--previous", type=Path, help="previous title review JSON for a targeted title revision")
    parser.add_argument("--version", help="Article or outline version of temporary review outputs")
    args = parser.parse_args()
    try:
        source = (sys.stdin.buffer.read().decode("utf-8-sig") if args.input == "-"
                  else Path(args.input).read_text(encoding="utf-8-sig"))
        review = json.loads(source)
        validate_review(review)
        if "title_revision" in review:
            if not args.previous:
                raise ValueError("a targeted title revision needs --previous")
            validate_title_revision(review, json.loads(args.previous.read_text(encoding="utf-8-sig")))
        if args.publish_current and args.open_browser:
            raise ValueError("publishing to the current page cannot open another browser tab")
        if args.publish_current and review["stage"] == "titles" and (
            review.get("title_step") is None or review.get("title_outline") is None
        ):
            raise ValueError("publishing a title review requires title_step, title_outline and one title item")
        html = render(review, standalone=args.standalone or args.open_browser or args.publish_current)
        if args.output.suffix != ".html" or len(html.encode("utf-8")) >= 1_000_000:
            raise ValueError("output must be HTML under 1 MB")
        if args.publish_current:
            current_json = args.output.with_suffix(".json")
            if args.input != "-" and current_json.resolve() == Path(args.input).resolve():
                raise ValueError("keep the round input separate from the current page")
            replace_current(args.output, html)
            replace_current(current_json, source)
            outputs = [args.output, current_json]
        else:
            with args.output.open("x", encoding="utf-8", newline="\n") as output:
                output.write(html)
            outputs = [args.output]
        register_review_outputs(outputs, f"render_outline_review ({review['review_id']})", version=args.version)
        if args.open_browser and not webbrowser.open(args.output.resolve().as_uri(), new=2):
            raise ValueError(f"Could not open the browser. Page saved at {args.output.resolve()}")
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
