"""Read-only article contracts, section extraction and dependency checks."""
from __future__ import annotations

import hashlib
import json
import re
import struct
import zlib
import xml.etree.ElementTree as ET
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from markdown_it import MarkdownIt
except ImportError as exc:
    raise SystemExit("Install this skill's scripts/requirements.txt in the selected Python environment: " + str(exc))

SKILL = Path(__file__).resolve().parents[1]
SHARED_SAMPLES = SKILL / "references/samples"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MARKER = re.compile(r"^<!--\s*(/?)section:([a-z][a-z0-9-]*)\s*-->\s*$")
VERSION = re.compile(r"v[0-9]{3,}$")


class StateError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def text_digest(text: str) -> str:
    return digest(canonical(text).encode("utf-8"))


def valid_png(data: bytes) -> bool:
    if not data.startswith(PNG_SIGNATURE):
        return False
    offset, first, image_data = 8, True, []
    try:
        while offset < len(data):
            size = struct.unpack(">I", data[offset:offset + 4])[0]
            kind = data[offset + 4:offset + 8]
            payload = data[offset + 8:offset + 8 + size]
            crc = struct.unpack(">I", data[offset + 8 + size:offset + 12 + size])[0]
            if len(payload) != size or zlib.crc32(kind + payload) & 0xffffffff != crc:
                return False
            if first:
                if kind != b"IHDR" or size != 13 or not all(struct.unpack(">II", payload[:8])):
                    return False
                first = False
            if kind == b"IDAT":
                image_data.append(payload)
            offset += size + 12
            if kind == b"IEND":
                return size == 0 and offset == len(data) and bool(image_data) and bool(zlib.decompress(b"".join(image_data)))
    except (ValueError, struct.error, zlib.error):
        pass
    return False


def read_json(path: Path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise StateError("Expected a JSON object: " + str(path))
        return value
    except (OSError, ValueError) as exc:
        raise StateError(f"Cannot read {path}: {exc}") from exc


def checked_root(path) -> Path:
    supplied = Path(path).absolute()
    reject_links(supplied)
    root = supplied.resolve()
    if not root.is_dir() or not (root / "article").is_dir():
        raise StateError("Expected one article directory containing article/.")
    return root


def reject_links(path: Path):
    """Reject symlinks and Windows junctions in any existing path component."""
    for part in [path, *path.parents]:
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise StateError(f"Link/junction is not allowed for managed paths: {part}")


def inside(root: Path, base: Path, name: str, *, exists=False) -> Path:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise StateError("Empty or invalid managed path")
    candidate = base / name
    reject_links(candidate.absolute())
    target = candidate.resolve()
    if not target.is_relative_to(root) or target == root:
        raise StateError(f"Path escapes article directory: {name}")
    if exists and not target.is_file():
        raise StateError(f"Missing file: {target}")
    return target


def schema_errors(value, kind: str) -> list[str]:
    schema = read_json(SKILL / "assets/contracts/state.schema.json")
    selected = {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": f"#/$defs/{kind}"}
    return [f"{kind}:{'/'.join(map(str, e.absolute_path)) or '/'}: {e.message}"
            for e in sorted(Draft202012Validator(selected, format_checker=FormatChecker()).iter_errors(value),
                            key=lambda e: str(list(e.absolute_path)))]


def extract_sections(text: str, *, spans=None) -> tuple[str, dict[str, str]]:
    """Markers in fenced code are literal; markers outside fences delimit working units."""
    sections, current, buffer, outside = {}, None, [], []
    fence_char = None
    fence_size = 0
    for index, line in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n")):
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            run = fence[1]
            if fence_char is None:
                fence_char, fence_size = run[0], len(run)
            elif run[0] == fence_char and len(run) >= fence_size and not fence[2].strip():
                fence_char = None
            (buffer if current else outside).append(line)
            continue
        marker = MARKER.match(line) if fence_char is None else None
        if marker:
            closing, name = marker.groups()
            if not closing:
                if current or name in sections:
                    raise StateError("Nested or duplicate section marker: " + name)
                current, buffer = name, []
                start = index + 1
            else:
                if current != name:
                    raise StateError("Mismatched section marker: " + name)
                sections[name] = canonical("\n".join(buffer))
                if spans is not None:
                    spans[name] = (start, index)
                current, buffer = None, []
        else:
            (buffer if current else outside).append(line)
    if current or fence_char:
        raise StateError("Unclosed section or code fence")
    heading = canonical("\n".join(outside))
    if len(heading.splitlines()) != 1 or not heading.startswith("# "):
        raise StateError("Outside section markers only the article H1 title is allowed")
    return heading[2:], sections


def replace_section(text: str, section_id: str, content: str) -> str:
    spans = {}
    title, before = extract_sections(text, spans=spans)
    if section_id not in spans:
        raise StateError("Unknown section: " + section_id)
    start, end = spans[section_id]
    parts = re.split(r"(\r\n|\r|\n)", text)
    content = canonical(content)
    newline = parts[2 * start - 1]
    replacement = content.replace("\n", newline) + newline if content else ""
    result = "".join(parts[:2 * start]) + replacement + "".join(parts[2 * end:])
    updated = {**before, section_id: content}
    if extract_sections(result) != (title, updated):
        raise StateError("Replacement changes the article structure")
    return result


def validate_section_headings(sections, units):
    parent = None
    for section in sections:
        name = section["section_id"]
        content = units.get(name, "")
        if name == "lead":
            if "parent_section_id" in section:
                raise StateError("The article lead cannot have a parent section")
            if section["status"] == "pending" and content:
                raise StateError("Pending section already contains body text: " + name)
            continue
        if expected_parent := section.get("parent_section_id"):
            if expected_parent != parent:
                raise StateError("Subsection must follow its parent chapter: " + name)
            heading = "### " + section["title"]
        else:
            parent = name
            heading = "## " + section["title"]
        if content and content.split("\n", 1)[0] != heading:
            raise StateError(f"Section H{len(heading.split()[0])} differs from its stable ID/title mapping: " + name)
        if section["status"] == "pending" and content not in {"", heading}:
            raise StateError("Pending section already contains body text: " + name)


def assemble(text: str) -> tuple[str, dict]:
    title, units = extract_sections(text)
    lines, spans = ["# " + title, ""], {}
    for name, content in units.items():
        start = len(lines) + 1
        lines.extend(content.splitlines())
        spans[name] = {"start_line": start, "end_line": len(lines), "content_sha256": text_digest(content)}
        lines.append("")
    return "\n".join(lines).rstrip() + "\n", spans


class HTMLReferences(HTMLParser):
    def __init__(self, include_linked_media=False):
        super().__init__()
        self.references = []
        self.include_linked_media = include_linked_media
        self.media_tags = {"img", "video", "source"}
        if include_linked_media:
            self.media_tags.update({"audio", "track"})

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in self.media_tags and values.get("src"):
            self.references.append((values["src"], tag == "img"))
        if self.include_linked_media and tag == "video" and values.get("poster"):
            self.references.append((values["poster"], True))
        if tag == "a" and values.get("href"):
            self.references.append((values["href"], False))
        if values.get("srcset") and (tag == "img" or (self.include_linked_media and tag == "source")):
            raise StateError("Normalize HTML srcset before media checking/cleanup")


def references(text: str, *, include_linked_media=False) -> list[tuple[str, bool]]:
    result = []
    for token in MarkdownIt("commonmark", {"html": True}).parse(text):
        if token.type == "html_block":
            parser = HTMLReferences(include_linked_media)
            parser.feed(token.content)
            result.extend(parser.references)
        for child in token.children or []:
            if child.type == "image":
                result.append((child.attrGet("src"), True))
            elif child.type == "link_open":
                result.append((child.attrGet("href"), False))
            elif child.type == "html_inline":
                parser = HTMLReferences(include_linked_media)
                parser.feed(child.content)
                result.extend(parser.references)
    return result


def svg_references(text: str, label: str) -> list[str]:
    try:
        xml = ET.fromstring(text)
    except ET.ParseError as exc:
        raise StateError(f"Invalid SVG: {label}") from exc
    if xml.tag not in {"svg", "{http://www.w3.org/2000/svg}svg"}:
        raise StateError(f"Invalid SVG root: {label}")
    targets = [value for element in xml.iter() for key, value in element.attrib.items()
               if key == "href" or key.endswith("}href")]
    for groups in re.findall(r'''url\(\s*(?:"([^"]*)"|'([^']*)'|([^)\s'\"]+))\s*\)''', text):
        targets.append(next((target for target in groups if target), ""))
    return targets


def file_source(path: Path, overrides=None) -> Path:
    source = overrides.get(path, path) if overrides is not None else path
    if source is None or not source.is_file():
        raise StateError(f"Missing file: {path}")
    return source


def local_reference(root: Path, document: Path, target: str, *, allow_shared_sample=False, file_overrides=None) -> Path | None:
    if not target or target.startswith("#"):
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme in {"http", "https", "mailto"}:
            return None
        raise StateError("Unsupported reference scheme: " + target)
    name = unquote(parsed.path)
    if allow_shared_sample and (document.parent / name).resolve().is_relative_to(SHARED_SAMPLES):
        return inside(SHARED_SAMPLES, document.parent, name, exists=True)
    path = inside(root, document.parent, name)
    file_source(path, file_overrides)
    return path


def file_proof(root: Path, file: dict, file_overrides=None):
    path = inside(root, root / "article", file["file"])
    if digest(file_source(path, file_overrides).read_bytes()) != file["sha256"]:
        raise StateError("File digest differs: " + file["file"])
    return path


def proof(media: dict) -> dict:
    snapshot = {key: media.get(key) for key in ["id", "title", "revision", "file", "url", "sha256", "source_files"]}
    if "caption" in media:
        snapshot["caption"] = media["caption"].copy()
    return snapshot


def asset_link(file: str) -> str:
    return re.sub(r"^v[0-9]{3,}/(?=assets/)", "", file)


def is_article_asset(article: Path, path: Path) -> bool:
    return path.is_relative_to(article) and asset_link(path.relative_to(article).as_posix()).startswith("assets/")


def media_targets(media: dict) -> set[str]:
    targets = {media["url"]} if media.get("url") else set()
    if file := media.get("file"):
        targets.update((file, asset_link(file)))
    return targets


def display_media_number(media: dict) -> str:
    kind = "图" if media["id"].startswith("IMG-") else "视频"
    return f'{kind}{media["caption"]["number"]}'


def media_stem(media: dict, *, short=False, internal=False) -> str:
    prefix = media["id"] if internal else display_media_number(media)
    if short:
        return f'{prefix}_{media["caption"]["title"]}'
    return f'{prefix}_{media["title"]}_{media["revision"]}'


def confirmation_drift(units: dict[str, str], sections: list[dict]) -> list[dict]:
    changed = []
    for section in sections:
        name = section["section_id"]
        if section["status"] not in {"confirmed", "inherited"} or name not in units:
            continue
        updates = section.get("media_updates", [])
        baseline = section.get("confirmation") or section.get("inheritance") or {}
        expected = updates[-1]["after_sha256"] if updates else baseline.get("content_sha256")
        actual = text_digest(units[name])
        if expected and expected != actual:
            changed.append({"section_id": name, "confirmed_sha256": expected, "current_sha256": actual})
    return changed


def media_label(media: dict) -> str:
    if caption := media.get("caption"):
        return f'{display_media_number(media)}：{caption["title"]}'
    kind = "图" if media["id"].startswith("IMG-") else "视频"
    return f'{kind} {media["id"]}：{media["title"]}'


def numbered_placeholder(media: dict) -> str:
    kind = "图片" if media["id"].startswith("IMG-") else "视频"
    label = media_label(media)
    if description := media["caption"].get("description"):
        label += f"｜{description}"
    return f"【{kind}占位 {label}】"


def legacy_placeholder_pattern(media: dict) -> str:
    ident, title = re.escape(media["id"]), re.escape(media["title"])
    kind = "图片" if media["id"].startswith("IMG-") else "视频"
    return rf"【{kind}占位\s+{ident}(?:：{title}(?:；[^\n】]*)?|｜{title}｜[^\n】]+)】"


def neutral_media_markup(text: str, media: dict) -> str:
    ident, title = re.escape(media["id"]), re.escape(media["title"])
    text = re.sub(legacy_placeholder_pattern(media), "<MEDIA>", text)
    caption = media.get("caption")
    if caption:
        text = text.replace(numbered_placeholder(media), "<MEDIA>")
    targets = media_targets(media)
    for target in list(targets):
        targets.add(unquote(target))
        targets.update(t for t, _ in references(text) if unquote(t) == unquote(target))
    for target in sorted(targets, key=len, reverse=True):
        destination = rf"(?:<{re.escape(target)}>|{re.escape(target)})"
        image = rf"!\[{ident} {title}\]\(\s*{destination}\s*\)"
        captioned = image + rf"(?:[ \t]*\n)+[ \t]*图 {ident}：{title}"
        text = re.sub(captioned, "<MEDIA>", text)
        text = re.sub(rf"\[视频 {ident}：{title}\]\(\s*{destination}\s*\)", "<MEDIA>", text)
        if caption:
            label = re.escape(media_label(media))
            if media["id"].startswith("IMG-"):
                link = rf"!\[{label}\]\(\s*{destination}\s*\)"
                rendered = rf"{link}\n\n{label}"
            else:
                link = rf"\[观看视频\]\(\s*{destination}\s*\)"
                rendered = rf"\[{label}\]\(\s*{destination}\s*\)"
            caption_first = label
            if description := caption.get("description"):
                rendered += rf"(?:\n\n|｜){re.escape(description)}"
                caption_first += "｜" + re.escape(description)
                if not description.endswith("。"):
                    rendered += "。?"
            if not media["id"].startswith("IMG-"):
                text = re.sub(rf"\[{caption_first}\]\(\s*{destination}\s*\)", "<MEDIA>", text)
            text = re.sub(rf"{caption_first}\n\n{link}", "<MEDIA>", text)
            text = re.sub(rendered, "<MEDIA>", text)
    return canonical(text)


def valid_replacement(update: dict, replacement: dict, previous: dict):
    new = update["media"]
    before, after = replacement["before"], replacement["after"]
    if not previous and update["kind"] == "adopt" and new.get("caption"):
        kind = "图片" if new["id"].startswith("IMG-") else "视频"
        marker = re.escape(f"【{kind}占位 {media_label(new)}")
        if re.fullmatch(rf"{marker}(?:｜[^\n】]+)?】", before) and neutral_media_markup(after, new) == "<MEDIA>":
            return
    if not previous and new.get("caption") and re.fullmatch(legacy_placeholder_pattern(new), before):
        previous = new
    if not previous or previous["id"] != new["id"] or previous["title"] != new["title"]:
        raise StateError("Media update cannot invent or rename a confirmed media item")
    if update["kind"] == "caption":
        old_caption, new_caption = previous.get("caption"), new.get("caption")
        same_asset = {k: v for k, v in previous.items() if k != "caption"} == {
            k: v for k, v in new.items() if k != "caption"
        }
        if (same_asset and old_caption and new_caption and old_caption["number"] == new_caption["number"]
                and update["basis"]["kind"] == "user" and before != after
                and neutral_media_markup(before, previous) == "<MEDIA>"
                and neutral_media_markup(after, new) == "<MEDIA>"):
            return
        raise StateError("Caption edit must keep the adopted asset and its display number")
    old_targets = media_targets(previous)
    new_targets = media_targets(new)
    if any(unquote(before) == unquote(old) and unquote(after) == unquote(target)
           for old in old_targets for target in new_targets):
        return
    if update["kind"] == "adopt" and neutral_media_markup(before, previous) == "<MEDIA>" and neutral_media_markup(after, new) == "<MEDIA>":
        return
    if update["kind"] == "format" and new["id"].startswith("IMG-") and (caption := new.get("caption")):
        if description := caption.get("description"):
            legacy = f'【图片占位 {new["id"]}｜{new["title"]}｜{description}】'
            if caption["title"] == new["title"] and before == legacy and after == numbered_placeholder(new):
                return
    raise StateError("Media update changes ordinary prose; obtain section confirmation instead")


def effective_confirmation(section: dict, content: str, media: dict, root: Path, *,
                           source_limit=None, outline_version=None):
    confirmation = section["confirmation"]
    metadata = read_json(root / "article/metadata.json")
    if section["status"] == "inherited":
        inheritance = section.get("inheritance")
        if not inheritance or confirmation is not None:
            raise StateError("Inherited text must have lineage, not a fabricated confirmation")
        if source_limit is None or int(inheritance["article_version"][1:]) > source_limit:
            raise StateError("Inheritance must refer to an earlier real baseline, not this/future version")
        baseline = metadata["articles"][inheritance["article_version"]]
        original_outline = baseline["outline_version"]
        path = inside(root, root / "article", baseline["file"], exists=True)
        lines = path.read_text(encoding="utf-8").splitlines()
        if not 1 <= inheritance["start_line"] <= inheritance["end_line"] <= len(lines):
            raise StateError("Invalid inherited section span")
        original = "\n".join(lines[inheritance["start_line"] - 1:inheritance["end_line"]])
        if text_digest(original) != inheritance["content_sha256"]:
            raise StateError("Inherited baseline text differs")
        current = inheritance["content_sha256"]
        proofs = {m["id"]: proof(m) for m in baseline.get("media", [])}
    elif not confirmation:
        raise StateError("Confirmed section has no confirmation: " + section["section_id"])
    else:
        current = confirmation["content_sha256"]
        proofs = {p["id"]: p for p in confirmation["media"]}
        original_outline = confirmation["outline_version_at_confirmation"]
    if original_outline not in metadata["outlines"]:
        raise StateError("Confirmation refers to an unknown outline")
    if outline_version and original_outline != outline_version:
        review = section.get("outline_revalidation")
        if not review or review["outline_version"] != outline_version:
            raise StateError("Reused section needs an applicability check for the selected outline")
    replay = []
    for update in section["media_updates"]:
        if update["before_sha256"] != current:
            raise StateError("Broken media update chain: " + section["section_id"])
        if update["kind"] == "caption" and not update["replacements"]:
            raise StateError("Caption edit requires a visible caption replacement")
        previous = proofs.get(update["media"]["id"])
        for replacement in update["replacements"]:
            valid_replacement(update, replacement, previous)
        replay.append(update)
        current = update["after_sha256"]
        proofs[update["media"]["id"]] = update["media"]
        if update["kind"] == "adopt" and update["basis"]["kind"] != "user":
            raise StateError("New media adoption needs actual user evidence")
    if current != text_digest(content):
        raise StateError("Confirmed section text changed: " + section["section_id"])
    reconstructed = canonical(content)
    for update in reversed(replay):
        if text_digest(reconstructed) != update["after_sha256"]:
            raise StateError("Media update replay digest differs")
        previous_end = len(reconstructed) + 1
        for replacement in sorted(update["replacements"], key=lambda r: r["after_start"], reverse=True):
            start = replacement["after_start"]
            end = start + len(replacement["after"])
            if end > previous_end or reconstructed[start:end] != replacement["after"]:
                raise StateError("Media replacement offset/content is invalid or overlapping")
            reconstructed = reconstructed[:start] + replacement["before"] + reconstructed[end:]
            previous_end = start
        if text_digest(reconstructed) != update["before_sha256"]:
            raise StateError("Media update contains changes outside its verified media replacements")
    for item in media.values():
        if section["section_id"] not in item["section_ids"] or item["status"] == "retired":
            continue
        if item["status"] == "approved" and proofs.get(item["id"]) != proof(item):
            raise StateError("Confirmed section media changed without adoption/update: " + item["id"])


def validate_media(root: Path, items: list[dict], *, require_files=True, file_overrides=None):
    article = root / "article"
    ids, numbers = set(), set()
    for media in items:
        if media["id"] in ids:
            raise StateError("Duplicate media ID: " + media["id"])
        ids.add(media["id"])
        title = media["title"]
        if re.search(r'[<>:"/\\|?*\x00-\x1f]', title) or title.rstrip(" .") != title:
            raise StateError("Unsafe media title: " + title)
        if media["id"].startswith("IMG-") != (media["type"] == "image"):
            raise StateError("Media ID/type differ: " + media["id"])
        if caption := media.get("caption"):
            number = (media["type"], caption["number"])
            if number in numbers:
                raise StateError("Duplicate display number: " + media_label(media))
            numbers.add(number)
        if media["role"] == "body" and not media["section_ids"]:
            raise StateError("Body media needs at least one section")
        if media["status"] in {"planned", "retired"}:
            continue
        revision = media["revision"]
        if (not revision or not VERSION.fullmatch(revision) or int(revision[1:]) < 1
                or revision != f"v{int(revision[1:]):03d}"):
            raise StateError("Media revision is not canonical: " + media["id"])
        prefixes = {media_stem(media, internal=True)}
        if media.get("caption"):
            prefixes.add(media_stem(media))
        if media["file"]:
            path = inside(root, article, media["file"])
            if not is_article_asset(article, path):
                raise StateError("Adopted media must be inside the article's assets directory")
            if media["type"] == "image" and media["role"] == "body" and caption:
                display_stem = media_stem(media, short=True)
                if path.stem == display_stem:
                    prefixes = {display_stem}
            if path.stem not in prefixes:
                raise StateError("Media filename does not match ID/title/revision: " + path.name)
            if require_files:
                content = file_source(path, file_overrides).read_bytes()
                if not media["sha256"] or digest(content) != media["sha256"]:
                    raise StateError("Media digest differs: " + path.name)
                if media["type"] == "image" and media["role"] == "body" and (path.suffix != ".png" or not valid_png(content)):
                    raise StateError("Body image must be a real PNG: " + path.name)
        elif media["url"]:
            if media["type"] != "video" or not media["filename_verified"] or not media["verified_at"]:
                raise StateError("Online video needs verified naming and verification time: " + media["id"])
            if not media["canonical_name"] or Path(media["canonical_name"]).stem not in prefixes:
                raise StateError("Online video needs its verified canonical filename: " + media["id"])
        else:
            raise StateError("Ready media has no file or URL: " + media["id"])
        for source in media["source_files"]:
            path = file_proof(root, source, file_overrides) if require_files else inside(root, article, source["file"])
            if not is_article_asset(article, path):
                raise StateError("Editable source must be inside the article's assets directory")
            if path.suffix.lower() == ".svg" and path.stem not in prefixes:
                # Other SVGs can be dependencies, but the principal editable SVG uses the PNG stem.
                if not any(Path(s["file"]).stem in prefixes and Path(s["file"]).suffix.lower() == ".svg" for s in media["source_files"]):
                    raise StateError("SVG and PNG must share ID/title/revision: " + path.name)
        if require_files:
            registered = {inside(root, article, s["file"]) for s in media["source_files"]}
            if media["file"]:
                registered.add(inside(root, article, media["file"]))
            for source in media["source_files"]:
                svg = inside(root, article, source["file"])
                if svg.suffix.lower() != ".svg":
                    continue
                svg_text = file_source(svg, file_overrides).read_text(encoding="utf-8-sig")
                for target in svg_references(svg_text, str(svg)):
                    if target.startswith("#") or urlsplit(target).scheme in {"http", "https", "data"}:
                        continue
                    dependency = local_reference(root, svg, target, file_overrides=file_overrides)
                    if dependency and dependency not in registered:
                        raise StateError("SVG dependency is not registered as a retained source: " + target)
        if media["status"] == "approved" and not media["adoption"]:
            raise StateError("Approved media has no actual adoption evidence: " + media["id"])
        if media["status"] == "approved" and media["adoption"]["kind"] != "user":
            raise StateError("Media adoption cannot be inferred from task completion")


def pending_errors(progress: dict, *, final=False) -> list[str]:
    errors = []
    pending = {p["media_id"]: p for p in progress["pending_media"]}
    for media in progress["media"]:
        if media["status"] in {"approved", "retired"}:
            continue
        entry = pending.get(media["id"])
        if not entry or entry["disposition"] != "deferred" or not entry["basis"] or entry["basis"]["kind"] != "user":
            errors.append("Unresolved media choice: " + media["id"])
        elif final and not entry["allow_in_final"]:
            errors.append("Media not approved as a final placeholder: " + media["id"])
    return errors


def latest_operations(metadata: dict) -> dict:
    return {event["operation_id"]: event for event in metadata.get("asset_maintenance", [])}


def media_usage(root: Path, document: Path, text: str, items: list[dict], *, allow_ready=False, file_overrides=None) -> set[str]:
    used = set()
    for target, is_image in references(text):
        local = local_reference(root, document, target, file_overrides=file_overrides)
        matched = [m for m in items if (m["file"] and local == inside(root, root / "article", m["file"]))
                   or (m["url"] and unquote(target) == unquote(m["url"]))]
        if local and (is_image or local.suffix.lower() in IMAGE_EXTENSIONS) and not matched:
            raise StateError("Body image is not in media inventory: " + target)
        for media in matched:
            if media["status"] != "approved" and not (allow_ready and media["status"] == "ready"):
                raise StateError("Body contains media that was not adopted: " + media["id"])
            label = media_label(media)
            if label not in text:
                raise StateError("Visible caption/title differs from media filename: " + media["id"])
            used.add(media["id"])
    return used


def inspect(root: Path, *, progress_override=None, working_override=None, metadata_override=None,
            outline_overrides=None, file_overrides=None, archive_overrides=None,
            reviewable_drift=None) -> dict:
    errors, warnings = [], []
    article = root / "article"
    try:
        metadata = read_json(article / "metadata.json") if metadata_override is None else metadata_override
        def outline_bytes(path):
            return outline_overrides[path] if outline_overrides and path in outline_overrides else path.read_bytes()
        def archive_bytes(path):
            if archive_overrides and isinstance(archive_overrides.get(path), bytes):
                return archive_overrides[path]
            return file_source(path, archive_overrides).read_bytes()
        def archive_text(data):
            return data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        legacy = metadata.get("schema_version") in {1, 2}
        if not legacy:
            errors.extend(schema_errors(metadata, "metadata"))
        else:
            warnings.append("Legacy schema 1/2: read-only mapping check; upgrade working contracts before mutation.")
        if errors:
            return {"errors": errors, "warnings": warnings}
        outlines = metadata["outlines"]
        def validate_version(version, item, group, directory, prefix):
            number = int(version[1:])
            if number < 1 or version != f"v{number:03d}":
                raise StateError("Version number is not canonical: " + version)
            filename = f"{prefix}-{version}.md"
            folder = root / directory
            allowed = {folder / version / filename, folder / filename}
            if directory == "outline":
                allowed.add(article / version / filename)
            if inside(root, article, item["file"]) not in allowed:
                raise StateError("Version file does not match its directory/number: " + version)
            base = item.get("based_on")
            if base is not None and (base not in group or int(base[1:]) >= number):
                raise StateError("Version baseline must exist and precede this version: " + version)
        for version, item in outlines.items():
            outline_path = inside(root, article, item["file"], exists=True)
            if not legacy:
                validate_version(version, item, outlines, "outline", "outline")
                if next(iter(outline_bytes(outline_path).decode("utf-8").splitlines()), "") != "# " + item["title"]:
                    raise StateError("Outline title differs from its metadata: " + version)
            if not legacy and not item["confirmation"]:
                errors.append("Outline lacks actual confirmation: " + version)
            if not legacy and digest(outline_bytes(outline_path)) != item["content_sha256"]:
                errors.append("Archived outline bytes changed: " + version)
        for group, pointer in [("outlines", "latest_outline_version"), ("articles", "latest_article_version")]:
            versions = metadata[group]
            expected = max(versions, key=lambda v: int(v[1:])) if versions else None
            if metadata[pointer] != expected:
                errors.append("Latest pointer differs: " + pointer)
        media_revisions = {}
        def remember_revisions(items):
            for item in items:
                if not item["revision"] or item["status"] not in {"ready", "approved"}:
                    continue
                key = (item["id"], item["revision"])
                identity = (item["title"], item["type"], item["sha256"], item["url"])
                if key in media_revisions and media_revisions[key] != identity:
                    errors.append("Media revision was reused for different bytes/title: " + "/".join(key))
                media_revisions[key] = identity
        archived_sections = {}
        for version, record in metadata["articles"].items():
            file = inside(root, article, record["file"])
            archived = archive_bytes(file)
            text = archive_text(archived)
            if record["outline_version"] not in outlines:
                errors.append("Article refers to missing outline: " + version)
            else:
                outline_text = outline_bytes(inside(root, article, outlines[record["outline_version"]]["file"], exists=True)).decode("utf-8").replace("\r\n", "\n")
                if not outline_text.startswith("# " + record["title"] + "\n") or not text.startswith("# " + record["title"] + "\n"):
                    errors.append("Article/outline title differs: " + version)
            if record.get("record_schema_version") == 3:
                validate_version(version, record, metadata["articles"], "article", "article")
                remember_revisions(record["media"])
                if digest(archived) != record["content_sha256"]:
                    errors.append("Archived article bytes changed: " + version)
                validate_media(root, record["media"], file_overrides=file_overrides)
                text_lines = text.splitlines()
                media = {m["id"]: m for m in record["media"]}
                covered = []
                section_ids = []
                usage = {m["id"]: set() for m in record["media"]}
                for section in record["chapter_confirmations"]:
                    if section["status"] not in {"confirmed", "inherited"}:
                        raise StateError("Archived section is neither confirmed nor inherited")
                    span = section["span"]
                    if span["start_line"] > span["end_line"] or span["end_line"] > len(text_lines):
                        raise StateError("Invalid archived section span")
                    content = "\n".join(text_lines[span["start_line"] - 1:span["end_line"]])
                    if text_digest(content) != span["content_sha256"]:
                        raise StateError("Archived span digest differs")
                    effective_confirmation(section, content, media, root, source_limit=int(version[1:]) - 1,
                                           outline_version=record["outline_version"])
                    for ident in media_usage(root, file, content, record["media"], file_overrides=file_overrides):
                        usage[ident].add(section["section_id"])
                    covered.append(content)
                    section_ids.append(section["section_id"])
                expected = "# " + record["title"] + "\n\n" + "\n\n".join(covered) + "\n"
                if text != expected or len(set(section_ids)) != len(section_ids):
                    raise StateError("Archived section spans do not cover the body exactly")
                section_contents = dict(zip(section_ids, covered))
                archived_sections[version] = (file, record["title"], section_contents)
                if any("parent_section_id" in section for section in record["chapter_confirmations"]):
                    validate_section_headings(record["chapter_confirmations"], section_contents)
                for media_item in record["media"]:
                    if media_item["status"] == "approved" and usage[media_item["id"]] != set(media_item["section_ids"]):
                        raise StateError("Archived media section mapping differs: " + media_item["id"])
                errors.extend(pending_errors(record))
        progress_file = article / "progress.json"
        progress = progress_override if progress_override is not None else read_json(progress_file) if progress_file.exists() else None
        working = None
        if progress is not None and progress.get("schema_version") in {1, 2}:
            warnings.append("Legacy progress 1/2: read-only; supply contract 3 before mutation.")
            progress = None
        if progress is not None:
            errors.extend(schema_errors(progress, "progress"))
            if not errors:
                if progress["outline_version"] not in outlines:
                    raise StateError("Progress outline is not archived")
                if progress["based_on_article_version"] is not None and progress["based_on_article_version"] not in metadata["articles"]:
                    raise StateError("Progress has an unknown base article version")
                working_file = inside(root, article, progress["working_file"])
                archived = archived_sections.get(progress["archived_article_version"])
                if (working_override is None and not working_file.exists() and progress["phase"] == "finalized"
                        and not progress["is_active"] and archived is not None):
                    body_file, title, units = archived
                else:
                    body_file = working_file
                    working = working_override if working_override is not None else working_file.read_text(encoding="utf-8")
                    title, units = extract_sections(working)
                reviewable = {item["section_id"] for item in confirmation_drift(units, progress["sections"])
                              if reviewable_drift and reviewable_drift.get(item["section_id"]) == item["current_sha256"]}
                outline = outlines[progress["outline_version"]]
                if title != outline["title"]:
                    errors.append("Working title differs from chosen outline")
                ids = [s["section_id"] for s in progress["sections"]]
                if len(set(ids)) != len(ids) or list(units) != ids:
                    errors.append("Working section markers differ from progress order/IDs")
                if not ids or ids[0] != "lead":
                    errors.append("The first confirmation unit must be lead")
                validate_section_headings(progress["sections"], units)
                media = {m["id"]: m for m in progress["media"]}
                remember_revisions(progress["media"])
                validate_media(root, progress["media"], file_overrides=file_overrides)
                if any(not set(m["section_ids"]).issubset(ids) for m in media.values()):
                    errors.append("Media uses an unknown section")
                source_ids = {s["id"] for s in progress["sources"]}
                if len(source_ids) != len(progress["sources"]):
                    errors.append("Source IDs must be unique")
                pending_ids = [p["media_id"] for p in progress["pending_media"]]
                if len(set(pending_ids)) != len(pending_ids) or not set(pending_ids).issubset(media):
                    errors.append("Pending media IDs must be unique and registered")
                waiting = None
                usage = {m["id"]: set() for m in progress["media"]}
                for section in progress["sections"]:
                    name = section["section_id"]
                    reopened_at = section.get("reopened_at")
                    if reopened_at and section["status"] not in {"drafting", "awaiting_confirmation"}:
                        errors.append("Only an open draft can carry reopened_at: " + name)
                    if section.get("reopened_snapshot_sha256") and not reopened_at:
                        errors.append("Reopened snapshot lacks reopen evidence: " + name)
                    if section["status"] not in {"pending", "inherited"}:
                        if not section["source_refs"] or not set(section["source_refs"]).issubset(source_ids):
                            errors.append("Section needs readable document OR code source references: " + name)
                        if waiting is not None:
                            baseline = metadata["articles"].get(progress["based_on_article_version"], {})
                            original = next((s for s in baseline.get("chapter_confirmations", []) if s["section_id"] == name), None)
                            unchanged = original and original["span"]["content_sha256"] == text_digest(units.get(name, ""))
                            prior_reply = (section.get("confirmation") or {}).get("confirmed_at")
                            kept = (waiting.get("reopened_at") and prior_reply
                                    and datetime.fromisoformat(prior_reply) <= datetime.fromisoformat(waiting["reopened_at"]))
                            if section["status"] != "confirmed" or not (unchanged or kept):
                                errors.append("A later section was drafted before the earlier section was confirmed: " + name)
                    if section["status"] not in {"confirmed", "inherited"}:
                        if waiting is None:
                            waiting = section
                    elif name in units:
                        limit = int(progress["based_on_article_version"][1:]) if progress["based_on_article_version"] else None
                        if name not in reviewable:
                            effective_confirmation(section, units[name], media, root, source_limit=limit,
                                                   outline_version=progress["outline_version"])
                        # Images belong to this chapter's confirmation; videos may wait until assembly.
                        chapter_images = [m for m in progress["media"] if m["role"] == "body"
                                          and m["type"] == "image" and name in m["section_ids"]]
                        errors.extend(pending_errors({"media": chapter_images, "pending_media": progress["pending_media"]}))
                    for ident in media_usage(root, body_file, units.get(name, ""), progress["media"],
                                             allow_ready=section["status"] in {"drafting", "awaiting_confirmation"}, file_overrides=file_overrides):
                        usage[ident].add(name)
                for media_item in progress["media"]:
                    if media_item["status"] == "approved":
                        declared = set(media_item["section_ids"])
                        future = {s["section_id"] for s in progress["sections"] if s["status"] == "pending"}
                        if usage[media_item["id"]] - declared or declared - usage[media_item["id"]] - future:
                            errors.append("Media section mapping differs from actual uses: " + media_item["id"])
                for source in progress["sources"]:
                    if not source["path"] and not source["url"]:
                        errors.append("Source has no readable path or URL: " + source["id"])
                    if source["path"]:
                        source_path = Path(source["path"])
                        if not source_path.is_absolute():
                            source_path = root / source_path
                        if not source_path.exists():
                            errors.append("Source path is unavailable: " + source["id"])
                all_confirmed = all(s["status"] in {"confirmed", "inherited"} for s in progress["sections"])
                if progress["phase"] in {"waiting_media", "ready_to_archive", "archived", "finalized"} and not all_confirmed:
                    errors.append("Article phase requires all scoped sections confirmed")
                if progress["phase"] in {"ready_to_archive", "archived", "finalized"}:
                    errors.extend(pending_errors(progress, final=progress["phase"] == "finalized"))
                if progress["phase"] in {"archived", "finalized"}:
                    if progress["is_active"] or progress["archived_article_version"] not in metadata["articles"]:
                        errors.append("Archived progress must be inactive and name an archived article")
                    else:
                        record = metadata["articles"][progress["archived_article_version"]]
                        archived_path = inside(root, article, record["file"])
                        if working is not None and assemble(working)[0] != archive_text(archive_bytes(archived_path)):
                            errors.append("Inactive work does not match its archived article")
                        if progress["outline_version"] != record["outline_version"]:
                            errors.append("Inactive work uses a different outline than its archive")
                        def delivery(items):
                            return {m["id"]: (proof(m), m["role"], m["section_ids"], m["status"]) for m in items}
                        if record.get("record_schema_version") == 3 and delivery(progress["media"]) != delivery(record["media"]):
                            errors.append("Inactive media inventory differs from its archived snapshot")
                elif not progress["is_active"]:
                    errors.append("Unfinished authoring session must be active")
                if progress["phase"] == "finalized":
                    if progress["finalized_article_version"] != progress["archived_article_version"] or not progress["completion_basis"] or progress["completion_basis"]["kind"] not in {"user", "task_completion"}:
                        errors.append("Finalized state lacks version/basis")
                    if progress["finalized_article_version"] != metadata["latest_article_version"]:
                        errors.append("Finalized state must identify the latest archived article")
                elif progress["finalized_article_version"] is not None:
                    errors.append("Non-final state still carries a previous finalization marker")
                elif progress["completion_basis"] is not None:
                    errors.append("Non-final state still carries a previous completion basis")
                for candidate in progress["candidates"]:
                    path = file_proof(root, candidate, file_overrides)
                    if not path.is_relative_to(root / ".tmp"):
                        errors.append("Candidate inventory must refer to this article's .tmp")
        documents = [inside(root, article, i["file"], exists=True) for i in outlines.values()]
        archive_paths = [inside(root, article, i["file"]) for i in metadata["articles"].values()]
        texts = [(d, outline_bytes(d).decode("utf-8")) for d in documents]
        texts.extend((path, archive_text(archive_bytes(path))) for path in archive_paths)
        if working is not None:
            texts.append((working_file, working))
        for document, text in texts:
            is_outline = document in [inside(root, article, i["file"]) for i in outlines.values()]
            is_new_body = not is_outline and (document.name == "article-working.md" or any(i.get("record_schema_version") == 3 and inside(root, article, i["file"]) == document for i in metadata["articles"].values()))
            for target, image in references(text):
                local = local_reference(root, document, target, allow_shared_sample=is_outline and not image, file_overrides=file_overrides)
                if local and local.is_relative_to(root / ".tmp"):
                    errors.append("Deliverable refers to .tmp: " + target)
                if image and is_new_body and (local is None or local.suffix != ".png" or not valid_png(file_source(local, file_overrides).read_bytes())):
                    errors.append("New body references a non-local/non-PNG image: " + target)
            if is_new_body:
                inventory = progress["media"] if document.name == "article-working.md" and progress is not None else next((r.get("media", []) for r in metadata["articles"].values() if inside(root, article, r["file"]) == document), [])
                targets = {local_reference(root, document, target, file_overrides=file_overrides) for target, _ in references(text)}
                for media in inventory:
                    if media["role"] == "body" and media["status"] == "approved":
                        if media["file"] and inside(root, article, media["file"]) not in targets:
                            errors.append("Adopted body media is not referenced: " + media["id"])
                        if media_label(media) not in text:
                            errors.append("Visible caption/title differs from media filename: " + media["id"])
        if (article / "transaction.json").exists():
            warnings.append("Interrupted work transaction exists; use recover before further writes.")
        if any(e["status"] == "planned" for e in latest_operations(metadata).values()):
            warnings.append("Unfinished asset operation exists; recover before further mutations.")
    except (OSError, StateError, KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return {"errors": errors, "warnings": warnings}


def deletion_references(root, targets, metadata, progress, texts, *, excluded_documents=()):
    """Find files still used by a retained manuscript or its inventory."""
    article = root / "article"
    retained = {}
    documents = {path for folder in (article, root / "outline") for path in folder.rglob("*.md")}
    documents.update(inside(root, article, record["file"])
                     for group in ("articles", "outlines") for record in metadata[group].values())
    for document in sorted((documents | texts.keys()) - set(excluded_documents)):
        reject_links(document)
        text = texts[document] if document in texts else document.read_text(encoding="utf-8-sig")
        for link, _ in references(text, include_linked_media=True):
            parsed = urlsplit(link)
            if parsed.scheme == "file":
                name = url2pathname(f"//{parsed.netloc}{parsed.path}" if parsed.netloc else parsed.path)
            elif re.match(r"^[a-zA-Z]:[/\\]", link):
                name = unquote(link.split("#", 1)[0])
            elif not parsed.scheme and not parsed.netloc:
                name = unquote(parsed.path)
            else:
                continue
            if name and (target := (document.parent / name).resolve()) in targets:
                retained.setdefault(target, f"still referenced by {document}")
    for record in [progress, *metadata["articles"].values()]:
        for item in record.get("media", []):
            if item["status"] in {"approved", "ready"}:
                for file in [item, *item["source_files"]]:
                    if file["file"] and (path := inside(root, article, file["file"])) in targets:
                        retained.setdefault(path, f"still registered for {item['id']}")
        for source in record.get("sources", []):
            if source["path"] and (path := (root / source["path"]).resolve()) in targets:
                retained.setdefault(path, f"still registered as source {source['id']}")
    return retained


def check_deletion_references(root, targets, metadata, progress, texts):
    if retained := deletion_references(root, targets, metadata, progress, texts):
        path, reason = next(iter(retained.items()))
        raise StateError(f"Cannot delete {path}; {reason}")


def protected_files(root: Path, metadata: dict, progress: dict | None) -> set[Path]:
    """Actual references, selected publishing assets and necessary source dependencies."""
    article = root / "article"
    protected = set()
    outline_documents = [inside(root, article, item["file"], exists=True)
                         for item in metadata["outlines"].values()]
    documents = outline_documents + [inside(root, article, item["file"], exists=True)
                                     for item in metadata["articles"].values()]
    if progress is not None and progress["is_active"]:
        documents.append(inside(root, article, progress["working_file"], exists=True))
    for document in documents:
        for target, image in references(document.read_text(encoding="utf-8")):
            local = local_reference(root, document, target, allow_shared_sample=document in outline_documents and not image)
            if local and local.is_relative_to(root):
                protected.add(local)
    inventories = [r.get("media", []) for r in metadata["articles"].values()]
    if progress is not None:
        inventories.append(progress["media"])
    for items in inventories:
        for media in items:
            if media["status"] != "approved":
                continue
            main = inside(root, article, media["file"], exists=True) if media["file"] else None
            if main and (main in protected or media["role"] in {"cover", "publishing"}):
                protected.add(main)
                for source in media["source_files"]:
                    protected.add(file_proof(root, source))
    return protected
