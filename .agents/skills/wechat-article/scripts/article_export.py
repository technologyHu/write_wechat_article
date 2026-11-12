"""Package one article and the local assets reachable from its Markdown."""
from __future__ import annotations

import os
import posixpath
import tempfile
from hashlib import file_digest
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from article_editorial import visible_placeholders
from article_state import (VERSION, StateError, assemble, confirmation_drift, digest, display_media_number,
                           effective_confirmation, inside, is_article_asset, pending_errors,
                           read_json, references, reject_links, schema_errors, svg_references, text_digest)


def select_body(article: Path, version: str) -> tuple[Path, bytes, str, dict, dict]:
    if not VERSION.fullmatch(version) or int(version[1:]) < 1 or version != f"v{int(version[1:]):03d}":
        raise StateError("Use a specific article version such as v001.")
    metadata = read_json(inside(article, article, "metadata.json", exists=True))
    record = metadata["articles"].get(version)
    if record is not None:
        body = inside(article, article, record["file"], exists=True)
        if body.name != f"article-{version}.md" or body.parent not in {article, article / version}:
            raise StateError(f"Registered body path does not match {version}: {body}")
        content = body.read_bytes()
        expected = record.get("content_sha256")
        if (expected is not None or record.get("record_schema_version") == 3) and digest(content) != expected:
            raise StateError(f"Archived body digest differs: {body}")
        return body, content, "archived", record, {}

    progress_path = inside(article, article, "progress.json")
    if progress_path.is_file():
        progress = read_json(progress_path)
        if progress.get("is_active") and progress.get("working_file") == f"{version}/article-working.md":
            body = inside(article, article, progress["working_file"], exists=True)
            markdown, spans = assemble(body.read_text(encoding="utf-8"))
            return body, markdown.encode("utf-8"), "working_draft", progress, spans
    raise StateError(f"No archived body or explicitly versioned active draft for {version}.")


def resolve_asset(article: Path, document: Path, target: str) -> Path | None:
    url = urlsplit(target)
    if url.scheme in {"http", "https", "mailto", "data"} or (not url.scheme and url.netloc):
        return None
    path = unquote(url.path)
    if url.scheme or path.startswith("/") or "\\" in path or ":" in path:
        raise StateError(f"Use a portable relative asset link in {document.name}: {target}")
    if not path:
        return None
    try:
        asset = inside(article, document.parent, path, exists=True)
    except StateError as exc:
        raise StateError(f"Invalid asset link in {document.name}: {target}. {exc}") from exc
    member = posixpath.normpath(posixpath.join(document.parent.relative_to(article).as_posix(), path))
    if member != asset.relative_to(article).as_posix():
        raise StateError(f"Asset link must match the exact filename in {document.name}: {target}")
    return asset


def asset_closure(article: Path, body: Path, markdown: bytes) -> dict[Path, bytes | None]:
    files = {body: markdown}
    pending = [(body, target) for target, _ in references(markdown.decode("utf-8-sig"), include_linked_media=True)]
    while pending:
        document, target = pending.pop()
        asset = resolve_asset(article, document, target)
        if asset is None or asset in files:
            continue
        if not is_article_asset(article, asset):
            raise StateError(f"Local link in {document.name} must reference an article asset: {target}")
        files[asset] = None
        if asset.suffix.lower() == ".svg":
            content = asset.read_bytes()
            files[asset] = content
            pending.extend((asset, ref) for ref in svg_references(content.decode("utf-8-sig"), str(asset)))
    return files


def release_errors(root, version, content, source_type, record, placeholders):
    if source_type != "archived" or record.get("record_schema_version") != 3:
        return ["Release export requires an archived body with chapter confirmations."]
    if errors := schema_errors(record, "article"):
        return errors
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = content.splitlines()
    covered = []
    media = {item["id"]: item for item in record["media"]}
    for section in record["chapter_confirmations"]:
        span = section["span"]
        start, end = span["start_line"], span["end_line"]
        text = "\n".join(lines[start - 1:end])
        if (section["status"] not in {"confirmed", "inherited"} or not 1 <= start <= end <= len(lines)
                or text_digest(text) != span["content_sha256"]):
            return [f'Unresolved or changed chapter in release export: {section["section_id"]}']
        effective_confirmation(section, text, media, root, source_limit=int(version[1:]) - 1,
                               outline_version=record["outline_version"])
        covered.append(text)
    if content.rstrip("\n") != f'# {record["title"]}\n\n' + "\n\n".join(covered):
        return ["Confirmed chapters do not cover the release body."]
    errors = pending_errors(record, final=True)
    by_label = {display_media_number(item): item["id"] for item in record["media"] if item.get("caption")}
    allowed = {item["media_id"] for item in record["pending_media"] if item["allow_in_final"]}
    errors.extend(f'Placeholder not approved for release at line {item["line"]}: {item["id"]}'
                  for item in placeholders if by_label.get(item["id"], item["id"]) not in allowed)
    return errors


def export_article(root: Path, version: str, *, output_dir: Path | None = None, apply=False, release=False) -> dict:
    selection = select_body(root / "article", version)
    return export_selection(root, version, selection, output_dir=output_dir, apply=apply, release=release)


def export_selection(root: Path, version: str, selection, *, output_dir=None, apply=False, release=False) -> dict:
    article = root / "article"
    body, content, source_type, record, spans = selection
    text = content.decode("utf-8-sig")
    placeholders = visible_placeholders(text)
    chapters = record.get("sections" if source_type == "working_draft" else "chapter_confirmations", [])
    unresolved = [section["section_id"] for section in chapters if section["status"] not in {"confirmed", "inherited"}]
    lines = text.splitlines()
    units = {name: "\n".join(lines[span["start_line"] - 1:span["end_line"]]) for name, span in spans.items()}
    changed = confirmation_drift(units, chapters)
    if release and (errors := release_errors(root, version, text, source_type, record, placeholders)):
        raise StateError("; ".join(errors))
    files = asset_closure(article, body, content)
    members = {path.relative_to(article).as_posix(): path for path in files}
    body_name = body.relative_to(article).as_posix()
    directory = (output_dir if output_dir is not None else root / "exports").absolute()
    output = directory / f"{root.name}{version}.zip"
    reject_links(output)
    if not directory.is_dir() and (output_dir is not None or directory.exists()):
        raise StateError(f"Export path is not a directory: {directory}")
    if output.exists() and not output.is_file():
        raise StateError(f"Export target is not a file: {output}")
    result = {"read_only": not apply, "version": version, "source_type": source_type,
              "body": body_name, "assets": sorted(members.keys() - {body_name}),
              "zip": str(output), "release": release, "unresolved_sections": unresolved, "changed_sections": changed,
              "placeholders": placeholders, "pending_media": record.get("pending_media", [])}
    if not apply:
        return result

    expected_digests = {asset["file"]: asset["sha256"] for item in record.get("media", [])
                        for asset in [item, *item.get("source_files", [])] if asset.get("file") and asset.get("sha256")}
    expected_digests[body_name] = digest(content)
    if output_dir is None:
        directory.mkdir(exist_ok=True)
    reject_links(output)
    fd, pending = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=directory)
    os.close(fd)
    try:
        with ZipFile(pending, "w", compression=ZIP_DEFLATED) as package:
            for name, path in sorted(members.items()):
                if files[path] is None:
                    package.write(inside(article, article, name, exists=True), name)
                else:
                    package.writestr(name, files[path])
        with ZipFile(pending) as package:
            if set(package.namelist()) != set(members):
                raise StateError("ZIP verification failed: unexpected members")
            for name in members:
                with package.open(name) as stream:
                    actual = file_digest(stream, "sha256").hexdigest()
                if name in expected_digests and actual != expected_digests[name]:
                    raise StateError(f"ZIP asset does not match the selected version: {name}")
        reject_links(output)
        os.replace(pending, output)
    except BadZipFile as exc:
        raise StateError(f"ZIP verification failed: {exc}") from exc
    finally:
        Path(pending).unlink(missing_ok=True)
    return result
