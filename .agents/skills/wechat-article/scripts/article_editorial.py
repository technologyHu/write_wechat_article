"""Article preferences and read-only, reader-facing Markdown checks."""
from __future__ import annotations

import os
import re
import tempfile
from bisect import bisect_right
from html import escape
from pathlib import Path

from markdown_it import MarkdownIt

from article_state import StateError, extract_sections, inside, read_json, reject_links


DEFAULT_MEDIA = {"image_caption": "below", "video_caption": "separate", "description_required": False,
                 "numbering": "stable"}
OPENJIUWEN_MEDIA = {**DEFAULT_MEDIA, "video_caption": "linked", "description_required": True,
                    "numbering": "appearance"}
PLACEHOLDER = re.compile(r"^【(?:图片|视频)占位\s+([^：｜；】]+).*】$")
IMAGE_CAPTION = re.compile(r"^图(\d+)：([^｜]+)(?:｜(.+))?$")
VIDEO_CAPTION = re.compile(r"^视频(\d+)：([^｜]+)(?:｜(.+))?$")


def preferences(root, scenario):
    path = inside(root, root / "article", "preferences.json")
    settings = read_json(path) if path.exists() else {}
    if settings.keys() - {"media", "global_notes", "sections", "terms", "long_paragraph"}:
        raise StateError("Unknown editorial preference field")
    media = {**(OPENJIUWEN_MEDIA if scenario == "openjiuwen" else DEFAULT_MEDIA), **settings.get("media", {})}
    if (media.keys() != DEFAULT_MEDIA.keys() or media["image_caption"] not in {"below", "above"}
            or media["video_caption"] not in {"linked", "separate"} or media["numbering"] not in {"appearance", "stable"}
            or not isinstance(media["description_required"], bool)):
        raise StateError("Invalid media layout preferences")
    settings["media"] = media
    settings.setdefault("global_notes", [])
    settings.setdefault("sections", {})
    settings.setdefault("terms", [])
    settings.setdefault("long_paragraph", 180)
    if (not isinstance(settings["global_notes"], list) or not isinstance(settings["sections"], dict)
            or not isinstance(settings["terms"], list)):
        raise StateError("Invalid editorial notes or terms")
    if type(settings["long_paragraph"]) is not int or settings["long_paragraph"] < 1:
        raise StateError("long_paragraph must be a positive character count")
    for term in settings["terms"]:
        if (not isinstance(term.get("avoid"), str) or not term["avoid"] or not isinstance(term.get("prefer"), str)
                or not term["prefer"] or not isinstance(term.get("sections", []), list)):
            raise StateError("Each term needs avoid, prefer and optional section IDs")
    return settings


def visible_placeholders(text):
    tokens = MarkdownIt("commonmark", {"html": True}).parse(text)
    return [{"id": match[1], "line": token.map[0] + offset + 1, "text": line}
            for token in tokens if token.type == "inline" and token.map
            for offset, line in enumerate(token.content.splitlines()) if (match := PLACEHOLDER.fullmatch(line.strip()))]


def link_labels(children):
    label = None
    for child in children:
        if child.type == "link_open":
            label = []
        elif child.type == "link_close" and label is not None:
            yield "".join(label)
            label = None
        elif label is not None and child.type in {"text", "code_inline"}:
            label.append(child.content)


def review_markdown(text, settings, *, spans=None):
    issues = []

    def note(line, code, message, level="warning"):
        issues.append({"line": line, "code": code, "level": level, "message": message})

    tokens = MarkdownIt("commonmark", {"html": True}).parse(text)
    lines = text.splitlines()
    if spans is None:
        spans = {}
        if "<!-- section:lead -->" in text:
            extract_sections(text, spans=spans)
    section_at = sorted((start, end, name) for name, (start, end) in spans.items())
    starts = [item[0] for item in section_at]
    inline = [(token, index) for index, token in enumerate(tokens) if token.type == "inline" and token.map]
    media = settings["media"]
    images, videos = [], []
    previous_heading, title_count = 0, 0

    for index, (token, token_index) in enumerate(inline):
        line = token.map[0] + 1
        children = token.children or []
        visible = "".join(child.content for child in children if child.type == "text")
        position = bisect_right(starts, line - 1) - 1
        section = section_at[position][2] if position >= 0 and line - 1 < section_at[position][1] else None
        if "**" in visible and re.search(r"(?<!\\)\*\*", token.content):
            note(line, "literal-bold", "有加粗标记被解析为普通文字，检查标点和空格。")
        opener = tokens[token_index - 1]
        if opener.type == "heading_open":
            level = int(opener.tag[1:])
            if level == 1:
                title_count += 1
            if level > 3 or level > previous_heading + 1 or title_count > 1:
                note(line, "heading-level", "检查唯一主标题及 H2、H3 的层级关系。")
            if len(visible) > 46:
                note(line, "long-heading", "标题较长，可检查手机端换行。", "hint")
            previous_heading = level
        if opener.type == "paragraph_open" and len(visible) > settings["long_paragraph"]:
            note(line, "long-paragraph", f"段落约 {len(visible)} 字，可检查手机端阅读节奏。", "hint")
        for term in settings["terms"]:
            if term.get("sections") and section not in term["sections"]:
                continue
            if term["avoid"] in visible:
                note(line, "preferred-term", f'检查「{term["avoid"]}」是否应写作「{term["prefer"]}」。', "hint")

        for child in children:
            if child.type == "image" and (image := IMAGE_CAPTION.fullmatch(child.content)):
                images.append((int(image[1]), line))
                nearby = index + (1 if media["image_caption"] == "below" else -1)
                caption_token = inline[nearby][0] if 0 <= nearby < len(inline) else None
                caption = IMAGE_CAPTION.fullmatch(caption_token.content) if caption_token else None
                if caption:
                    left, right = sorted((caption_token, token), key=lambda item: item.map[0])
                    if any(value.strip() for value in lines[left.map[1]:right.map[0]]):
                        caption = None
                if not caption or caption.group(1, 2) != image.group(1, 2):
                    note(line, "image-caption", "图片的相邻图注位置、编号或标题与配置不符。")
                elif media["description_required"] and not caption[3]:
                    note(line, "image-description", "图注缺少简短内容说明。")
        for video in filter(None, (VIDEO_CAPTION.fullmatch(label) for label in link_labels(children))):
            videos.append((int(video[1]), line))
            if media["video_caption"] == "linked" and not video[3]:
                note(line, "video-caption", "视频编号、标题和描述应在同一个链接中。")
        if re.search(r"(?<![\w/])/extension(?:\s+install)?\b", visible):
            note(line, "inline-command", "命令建议使用行内代码格式。", "hint")

    for placeholder in visible_placeholders(text):
        note(placeholder["line"], "media-placeholder", placeholder["text"])
        if match := re.fullmatch(r"视频(\d+)", placeholder["id"]):
            videos.append((int(match[1]), placeholder["line"]))
        elif match := re.fullmatch(r"图(\d+)", placeholder["id"]):
            images.append((int(match[1]), placeholder["line"]))
    if media["numbering"] == "appearance":
        for kind, found in (("图片", images), ("视频", videos)):
            seen = set()
            for number, line in sorted(found, key=lambda pair: pair[1]):
                if number in seen:
                    continue
                expected = len(seen) + 1
                if number != expected:
                    note(line, "media-number", f"{kind}按首次出现顺序应编号 {expected}，当前为 {number}。")
                seen.add(number)
    return sorted(issues, key=lambda issue: (issue["line"], issue["code"]))


def mobile_preview(source: Path, markdown: str, output: Path, *, apply=False) -> dict:
    output = output.absolute()
    if output.suffix.lower() != ".html" or not output.parent.is_dir():
        raise StateError("Choose an .html path in an existing directory for the mobile preview.")
    reject_links(output)
    result = {"read_only": not apply, "source": str(source), "preview": str(output), "width_px": 430}
    if not apply:
        return result
    body = MarkdownIt("commonmark", {"html": False}).render(markdown)
    page = f'''<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<base href="{escape(source.parent.as_uri() + '/', quote=True)}">
<title>公众号文章手机预览</title>
<style>
body {{ margin: 0; background: #f3f4f5; color: #202124; font: 16px/1.75 system-ui, "Microsoft YaHei", sans-serif; }}
article {{ box-sizing: border-box; max-width: 430px; margin: auto; padding: 24px 20px; background: #fff; overflow-wrap: anywhere; }}
h1 {{ font-size: 24px; line-height: 1.4; }}
h2, h3 {{ line-height: 1.5; }}
img {{ display: block; height: auto; max-width: 100%; }}
a {{ color: #165d97; }}
pre {{ overflow: auto; }}
</style>
<article>{body}</article>
</html>
'''
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as stream:
        pending = Path(stream.name)
        try:
            stream.write(page)
            stream.close()
            os.replace(pending, output)
        finally:
            pending.unlink(missing_ok=True)
    return result
