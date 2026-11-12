"""Adopt a local asset by its visible number in the active manuscript."""
from __future__ import annotations

import re
import uuid
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote

from article_editorial import preferences
from article_lifecycle import read_work, validate_candidate
from article_revision import (body_target, commit_revision_files, exact, file_digest, find_media_block,
                              json_bytes, media_block, rewrite_media, working_outline)
from article_state import (StateError, check_deletion_references, confirmation_drift, digest, display_media_number, extract_sections,
                           inside, is_article_asset, legacy_placeholder_pattern, local_reference, media_stem,
                           numbered_placeholder, proof, read_json, references, reject_links, replace_section, text_digest)


def next_revision(root, assets, item, progress, metadata):
    ident = item["id"]
    inventory = [item]
    for record in metadata["articles"].values():
        inventory.extend(record.get("media", []))
    for section in progress["sections"]:
        inventory.extend((section.get("confirmation") or {}).get("media", []))
        inventory.extend(update["media"] for update in section["media_updates"])
    revisions = [int(record["revision"][1:]) for record in inventory
                 if record["id"] == ident and record.get("revision")]
    prefixes = [re.escape(media_stem({**item, "revision": ""}, internal=internal)) for internal in (True, False)]
    pattern = re.compile(rf"(?:{'|'.join(prefixes)})v([0-9]{{3,}})", re.I)
    for folder in [assets, root / ".tmp"]:
        for path in folder.rglob("*"):
            if match := pattern.fullmatch(path.stem):
                revisions.append(int(match[1]))
    return f"v{max(revisions, default=0) + 1:03d}"


def retarget_links(root, document, text, previous, target):
    old_file = inside(root, root / "article", previous["file"]) if previous.get("file") else None
    replacements = {}
    for link, image in references(text):
        local = local_reference(root, document, link, allow_shared_sample=not image)
        if (old_file is not None and local == old_file) or (previous.get("url") and link == previous["url"]):
            decoded = unquote(link)
            for spelling in {link, decoded, decoded.replace(" ", "%20")}:
                replacements[f"(<{spelling}>)"] = f"(<{target}>)"
                replacements[f"({spelling})"] = f"(<{target}>)"
    return rewrite_media(text, replacements, {})


def old_block(item, unit, target):
    if item["status"] in {"planned", "ready"}:
        pattern = f"{re.escape(numbered_placeholder(item))}|{legacy_placeholder_pattern(item)}"
        placeholders = re.findall(pattern, unit)
        if len(placeholders) > 1:
            raise StateError(f"Ambiguous media placeholder: {item['id']}")
        if placeholders:
            return placeholders[0], True
    return find_media_block(item, unit, target), False


def check_external_source(source, root):
    for folder in source.parents:
        if folder == root:
            return
        metadata = folder / "article/metadata.json"
        if metadata.is_file():
            progress = metadata.with_name("progress.json")
            check_deletion_references(folder, {source}, read_json(metadata),
                                      read_json(progress) if progress.is_file() else {}, {})
            return


def adopt_media(root, number, source, *, basis, at, svg=None, apply=False, delete_previous=False, delete_source=False):
    if not basis or not basis.strip():
        raise StateError("adopt-media needs the user's actual instruction in --basis")
    working, original, metadata, progress = read_work(root)
    article = root / "article"
    matches = [item for item in progress["media"] if item["role"] == "body" and item.get("caption")
               and item["status"] in {"planned", "ready", "approved"} and display_media_number(item) == number]
    if len(matches) != 1:
        raise StateError(f"Select one registered body media number, for example 图1 or 视频6: {number}")
    item = matches[0]
    previous = deepcopy(item)
    raw = original[working].decode("utf-8")
    _, units = extract_sections(raw)
    unrelated = {entry["section_id"]: entry["current_sha256"] for entry in confirmation_drift(units, progress["sections"])
                 if entry["section_id"] not in item["section_ids"]}
    validate_candidate(root, reviewable_drift=unrelated)

    source = source.absolute()
    reject_links(source)
    source = source.resolve()
    suffix = source.suffix.lower()
    supported = {".png"} if item["type"] == "image" else {".mp4", ".mov", ".webm", ".m4v", ".avi"}
    if not source.is_file() or source.stat().st_size == 0 or suffix not in supported:
        raise StateError(f"Expected a nonempty local {item['type']} file ({', '.join(sorted(supported))}): {source}")
    checksum = file_digest(source)
    same_asset = item["file"] and checksum == item["sha256"]
    if svg is not None:
        svg = svg.absolute()
        reject_links(svg)
        if item["type"] != "image" or svg.suffix.lower() != ".svg" or not svg.is_file():
            raise StateError("--svg needs a local SVG paired with a PNG image")
        svg = svg.resolve()
        svg_checksum = file_digest(svg)
        old_pair = Path(item["file"]).with_suffix(".svg").as_posix() if item["file"] else None
        same_asset = same_asset and any(record["file"] == old_pair and record["sha256"] == svg_checksum
                                        for record in item["source_files"])
    result = {"read_only": not apply, "media_id": item["id"], "number": number, "sections": item["section_ids"]}

    def finish(raw, files, outline_updates, *, changed):
        retained = inside(root, article, item["file"])
        deletions = {}
        if delete_previous and changed and previous.get("file"):
            old = inside(root, article, previous["file"], exists=True)
            if old != retained:
                deletions[old] = previous["sha256"]
        if delete_source:
            if source == retained:
                raise StateError(f"Cannot delete the source; it is the retained media file: {source}")
            deletions[source] = checksum

        if deletions:
            texts = {working: raw, **{path: data.decode("utf-8") for path, data in outline_updates.items()}}
            check_deletion_references(root, deletions, metadata, progress, texts)
            if source in deletions:
                check_external_source(source, root)

        managed = {path: sha for path, sha in deletions.items() if is_article_asset(article, path)}
        deferred = deletions.keys() - managed.keys()
        token = uuid.uuid4().hex
        if managed:
            version = working.parent.name if working.parent != article else progress["outline_version"]
            metadata["asset_maintenance"].extend({
                "operation_id": uuid.uuid4().hex, "batch_id": token, "action": "delete", "status": "completed",
                "article_version": version, "at": at, "source": path.relative_to(root).as_posix(),
                "target": None, "sha256": sha, "reason": basis,
            } for path, sha in managed.items())
        prior_candidates = progress["candidates"]
        progress["candidates"] = [entry for entry in prior_candidates if inside(root, article, entry["file"]) not in deletions]
        removals = dict.fromkeys(managed)
        validate_candidate(root, metadata_override=metadata, progress_override=progress, working_override=raw,
                           outline_overrides=outline_updates, file_overrides={**files, **removals}, reviewable_drift=unrelated)
        if apply:
            if changed or managed or prior_candidates != progress["candidates"]:
                changes = {**files, **outline_updates, working: raw.encode("utf-8"),
                           article / "metadata.json": json_bytes(metadata), article / "progress.json": json_bytes(progress),
                           **removals}
                commit_revision_files(root, changes, original, managed, token, reviewable_drift=unrelated,
                                      media_deletion_id=item["id"] if managed else None)
            for path in deferred:
                try:
                    current_meta = read_json(article / "metadata.json")
                    current_progress = read_json(article / "progress.json")
                    check_deletion_references(root, {path}, current_meta, current_progress, {})
                    check_external_source(path, root)
                    reject_links(retained)
                    reject_links(path)
                    if file_digest(retained) != checksum or file_digest(path) != deletions[path]:
                        raise StateError("Retained media or source changed before deletion")
                    path.unlink()
                except (OSError, StateError) as exc:
                    raise StateError(f"Media was adopted but the original remains at {path}: {exc}") from exc
        paths = [str(path) for path in deletions]
        return {**result, "file": item["file"], "revision": item["revision"], "changed": changed,
                "source_files": item["source_files"],
                "planned_deletions": paths, "deleted": paths if apply else []}

    if same_asset and item["status"] == "approved":
        return finish(raw, {}, {}, changed=False)

    files = {}
    if not same_asset:
        directory = inside(article, working.parent, "assets/images" if item["type"] == "image" else "assets/videos")
        item["revision"] = next_revision(root, directory.parent, item, progress, metadata)
        destination = inside(article, directory, media_stem(item) + suffix)
        if destination.exists():
            raise StateError(f"Media destination already exists: {destination}")
        files[destination] = source
        item.update(file=destination.relative_to(article).as_posix(), source_files=[], sha256=checksum,
                    url=None, filename_verified=False, verified_at=None, canonical_name=None)
        if svg is not None:
            editable = inside(article, directory, destination.with_suffix(".svg").name)
            if editable.exists():
                raise StateError(f"Editable SVG destination already exists: {editable}")
            files[editable] = svg
            item["source_files"].append({"file": editable.relative_to(article).as_posix(), "sha256": svg_checksum})
    evidence = {"kind": "user", "message": basis, "at": at}
    item.update(status="approved", adoption=evidence)
    if previous["status"] == "planned" and (description := item["caption"].get("description")):
        item["caption"]["description"] = description.removeprefix("待提供。").removeprefix("待完成。").removeprefix("计划演示")
    progress["pending_media"] = [entry for entry in progress["pending_media"] if entry["media_id"] != item["id"]]

    settings = preferences(root, metadata["scenario"])["media"]
    layout = settings["image_caption" if item["type"] == "image" else "video_caption"]
    target = body_target(article, working, item)
    by_id = {section["section_id"]: section for section in progress["sections"]}
    for name in item["section_ids"]:
        before = units[name]
        old, placeholder = old_block(previous, before, body_target(article, working, previous))
        new = (media_block(item, f"<{target}>", layout) if placeholder
               else retarget_links(root, working, old, previous, target))
        if new == old and not same_asset:
            raise StateError(f"Media link was not found in {name}: {number}")
        after = exact(before, old, new, name)
        raw = replace_section(raw, name, after)
        section = by_id[name]
        if section["status"] in {"confirmed", "inherited"}:
            section["media_updates"].append({
                "kind": "adopt", "before_sha256": text_digest(before), "after_sha256": text_digest(after),
                "media": proof(item), "basis": evidence,
                "replacements": [{"before": old, "after": new, "after_start": before.index(old)}],
            })

    version = progress["outline_version"]
    outline_record = metadata["outlines"][version]
    bound = inside(root, article, outline_record["file"], exists=True)
    mirror = working_outline(root, bound)
    shared = any(record["outline_version"] == version for record in metadata["articles"].values())
    outline_updates = {}
    for path in [bound, mirror]:
        if not path.is_file() or (path == bound and shared) or previous["status"] == "planned":
            continue
        original[path] = path.read_bytes()
        if path == bound and digest(original[path]) != outline_record["content_sha256"]:
            raise StateError(f"Bound outline changed during media adoption: {path}")
        revised = retarget_links(root, path, original[path].decode("utf-8"), previous, body_target(article, path, item))
        if revised.encode("utf-8") != original[path]:
            outline_updates[path] = revised.encode("utf-8")
    if bound in outline_updates:
        outline_record["content_sha256"] = digest(outline_updates[bound])
        outline_record["change_summary"] += " 同步采用的媒体链接。"

    return finish(raw, files, outline_updates, changed=True)
