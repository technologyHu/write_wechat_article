"""Show the prose and captions associated with a displayed media number."""
from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from article_export import select_body
from article_revision import working_outline
from article_state import StateError, display_media_number, extract_sections, inside, read_json, references
from article_temp import temporary_version


def context_blocks(text, document, item, article, *, offset=0):
    number, ident = display_media_number(item), item["id"]
    label = re.compile(rf"^(?:[-*+]\s+)?(?:!?\[|【(?:图片|视频)占位\s+)?"
                       rf"(?:{re.escape(number)}|(?:(?:图|视频)\s+)?{re.escape(ident)})[：:｜；\s]")
    stable_marker = f"<!-- media-id: {ident} -->"
    registered = (article / item["file"]).resolve() if item.get("file") else None
    lines = text.splitlines()
    blocks = [(token.map[0], token.map[1], "\n".join(lines[token.map[0]:token.map[1]]))
              for token in MarkdownIt("commonmark", {"html": True}).parse(text)
              if token.type in {"inline", "html_block"} and token.map]

    def matches(block):
        if stable_marker in block or label.match(block.lstrip()):
            return True
        for link, _ in references(block, include_linked_media=True):
            if item.get("url") == link:
                return True
            parsed = urlsplit(link)
            if (registered and not parsed.scheme and not parsed.netloc and parsed.path
                    and (document.parent / unquote(parsed.path)).resolve() == registered):
                return True
        return False

    found = []
    for index, (start, end, block) in enumerate(blocks):
        if not matches(block):
            continue
        if found and found[-1]["index"] == index - 1:
            found[-1].update(index=index, end=end, text=found[-1]["text"] + "\n\n" + block)
        else:
            found.append({"index": index, "start": start, "end": end, "text": block,
                          "preceding_text": blocks[index - 1][2] if index else None})
    return [{"line": row["start"] + offset + 1, "end_line": row["end"] + offset,
             "media_text": row["text"], "preceding_text": row["preceding_text"],
             "following_text": blocks[row["index"] + 1][2] if row["index"] + 1 < len(blocks) else None}
            for row in found]


def review_media(root, number, *, version=None):
    article = root / "article"
    metadata = read_json(article / "metadata.json")
    progress_path = article / "progress.json"
    progress = read_json(progress_path) if progress_path.is_file() else None
    active = progress and progress["is_active"] and (version is None or version == temporary_version(root))
    if active and version not in metadata["articles"]:
        version = version or temporary_version(root)
        document = inside(root, article, progress["working_file"], exists=True)
        text = document.read_text(encoding="utf-8")
        spans = {}
        extract_sections(text, spans=spans)
        record, source_type = progress, "working_draft"
    else:
        version = version or metadata["latest_article_version"]
        if not version:
            raise StateError("No active draft or archived version to review")
        document, content, source_type, record, spans = select_body(article, version)
        text = content.decode("utf-8-sig")
        if source_type == "archived":
            spans = {entry["section_id"]: (entry["span"]["start_line"] - 1, entry["span"]["end_line"])
                     for entry in record.get("chapter_confirmations", [])}
        else:
            spans = {name: (span["start_line"] - 1, span["end_line"]) for name, span in spans.items()}

    selected = [item for item in record["media"] if item["role"] == "body" and item.get("caption")
                and item["status"] != "retired" and display_media_number(item) == number]
    if len(selected) != 1:
        raise StateError(f"Select one registered body media number: {number}")
    item = selected[0]
    lines = text.splitlines()
    body = []
    for name in item["section_ids"]:
        if name not in spans:
            continue
        start, end = spans[name]
        body.extend({"section_id": name, **row}
                    for row in context_blocks("\n".join(lines[start:end]), document, item, article, offset=start))
    outline = inside(root, article, metadata["outlines"][record["outline_version"]]["file"], exists=True)
    outlines = [outline]
    if source_type == "working_draft":
        mirror = working_outline(root, outline)
        if mirror.is_file():
            outlines.append(mirror)
    return {"read_only": True, "version": version, "source_type": source_type, "number": number,
            "media_id": item["id"], "registered_caption": item["caption"], "body_file": str(document), "body": body,
            "outlines": [{"file": str(path), "matches": context_blocks(path.read_text(encoding="utf-8"), path, item, article)}
                         for path in outlines]}
