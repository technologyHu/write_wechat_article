"""Preview and commit a scoped revision of the active article and its outline."""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from copy import deepcopy
from difflib import unified_diff
from hashlib import file_digest as hash_stream
from pathlib import Path
from urllib.parse import quote

from markdown_it import MarkdownIt

from article_editorial import preferences
from article_state import (StateError, check_deletion_references, display_media_number, extract_sections, file_proof, inside,
                           inspect, is_article_asset, media_label, media_stem, media_targets, numbered_placeholder,
                           proof, read_json, reject_links, replace_section, text_digest, digest)


def exact(text, before, after, label):
    if not isinstance(before, str) or not isinstance(after, str) or not before or text.count(before) != 1:
        raise StateError(f"Expected one exact original passage in {label}")
    return text.replace(before, after, 1)


def selected(plan):
    mode = plan.get("mode")
    if mode not in {"direct", "review"} or not plan.get("basis", "").strip():
        raise StateError("Revision requires mode direct/review and the user's original instruction in basis")
    if plan.keys() - {"mode", "basis", "body", "outline", "media", "title"}:
        raise StateError("Unknown revision plan field")
    accepted, choices = {}, []
    for kind in ("body", "outline", "media", "title"):
        accepted[kind] = []
        for index, edit in enumerate(plan.get(kind, []), 1):
            decision = edit.get("decision", "accepted" if mode == "direct" else "pending")
            if decision not in {"accepted", "keep", "pending"}:
                raise StateError(f"Unknown decision in {kind} item {index}")
            if mode == "review" and decision == "accepted" and not edit.get("reply", "").strip():
                raise StateError(f"Record the user's actual reply for {kind} item {index}")
            choice = {"kind": kind, "item": index, "decision": decision,
                      "scope": edit.get("section", edit.get("id"))}
            if decision == "pending":
                choice["proposal"] = {key: value for key, value in edit.items() if key not in {"decision", "reply"}}
            choices.append(choice)
            if decision == "accepted":
                accepted[kind].append(edit)
    return accepted, choices


def media_block(item, target, layout, separator="｜"):
    label = media_label(item)
    description = item["caption"].get("description")
    caption = f"{label}{separator}{description}" if description else label
    if item["status"] == "planned":
        return numbered_placeholder(item)
    if item["type"] == "image":
        embed = f"![{label}]({target})"
        return f"{embed}\n\n{caption}" if layout == "below" else f"{caption}\n\n{embed}"
    if layout == "linked":
        return f"[{caption}]({target})"
    if layout == "link_after":
        return f"{caption}\n\n[观看视频]({target})"
    link = f"[{label}]({target})"
    return f"{link}\n\n{description}" if description else link


def find_media_block(item, text, relative_target):
    if item["status"] == "planned":
        candidate = numbered_placeholder(item)
        if text.count(candidate) == 1:
            return candidate
    else:
        targets = media_targets(item)
        if relative_target:
            targets.add(relative_target)
        variants = targets | {quote(target, safe="/:@?&=#%+") for target in targets}
        layouts = ("above", "below") if item["type"] == "image" else ("linked", "separate", "link_after")
        blocks = {media_block(item, dest, layout, separator) for value in variants for dest in (value, f"<{value}>")
                  for layout in layouts for separator in ("｜", "\n\n")}
        matches = [(match.start(), block) for block in blocks for match in re.finditer(
            r"^" + re.escape(block) + r"(?=\n\n|$)", text, flags=re.M)]
        if len(matches) == 1:
            return matches[0][1]
    raise StateError(f'Expected one registered media block for {item["id"]}; check its current caption and link')


def body_target(article, working, item):
    if item.get("file"):
        path = inside(article, article, item["file"])
        return Path(os.path.relpath(path, working.parent)).as_posix()
    return item.get("url")


def media_edits(root, working, progress, edits, settings, basis, at):
    article = root / "article"
    items = {item["id"]: item for item in progress["media"]}
    blocks, outline_blocks, numbers, assets, events, removed = {}, {}, {}, {}, [], set()
    ids = set()
    for edit in edits:
        ident = edit["id"]
        if ident in ids or ident not in items:
            raise StateError(f"Select one operation per existing media ID: {ident}")
        ids.add(ident)
        item = items[ident]
        if item["role"] != "body" or item["status"] not in {"approved", "planned"} or not item.get("caption"):
            raise StateError(f"Revision media must be a numbered body image or video: {ident}")
        if edit.keys() - {"id", "number", "title", "description", "remove", "delete_files", "format", "decision", "reply"}:
            raise StateError(f"Unknown media edit field for {ident}")
        old = deepcopy(item)
        old_target = body_target(article, working, old)
        if edit.get("remove"):
            if any(key in edit for key in ("number", "title", "description", "format")):
                raise StateError(f"Remove and edit are separate media operations: {ident}")
            item["status"] = "retired"
            item.pop("caption")
            removed.add(display_media_number(old))
            progress["pending_media"] = [entry for entry in progress["pending_media"] if entry["media_id"] != ident]
        else:
            if edit.get("delete_files"):
                raise StateError(f"delete_files requires remove: {ident}")
            for key in ("number", "title", "description"):
                if key in edit:
                    item["caption"][key] = edit[key]
            caption = item["caption"]
            if not isinstance(caption["number"], int) or isinstance(caption["number"], bool) or caption["number"] < 1:
                raise StateError(f"Media number must be positive: {ident}")
            if not caption["title"].strip() or (settings["description_required"] and not caption.get("description", "").strip()):
                raise StateError(f"Media needs a title and the configured description: {ident}")
            if caption["number"] != old["caption"]["number"]:
                numbers[display_media_number(old)] = display_media_number(item)
        before_label = media_label(old)
        old_prefix = Path(old["file"]).stem if old.get("file") else None
        short_name = old["type"] == "image" and old_prefix == media_stem(old, short=True)
        rename = not edit.get("remove") and (item["caption"]["number"] != old["caption"]["number"]
                 or (short_name and item["caption"]["title"] != old["caption"]["title"]))
        for record in ([item] if item.get("file") else []) + item["source_files"]:
            if not (edit.get("delete_files") or rename):
                continue
            source = file_proof(root, record)
            if not is_article_asset(article, source):
                raise StateError(f"Not an article asset: {source}")
            if edit.get("delete_files"):
                target = None
            elif source.stem == old_prefix:
                name = media_stem(item, short=short_name) + source.suffix
                target = inside(article, source.parent, name)
                if source == target:
                    continue
                record["file"] = target.relative_to(article).as_posix()
            else:
                continue
            if source in assets:
                raise StateError(f"One asset cannot be edited twice: {source}")
            assets[source] = target
            events.append({"operation_id": uuid.uuid4().hex, "batch_id": "", "action": "move" if target else "delete",
                           "article_version": "", "status": "completed", "at": at,
                           "source": source.relative_to(root).as_posix(),
                           "target": target.relative_to(root).as_posix() if target else None,
                           "sha256": record["sha256"], "reason": basis})
        if edit.get("delete_files"):
            item.update(file=None, sha256=None, source_files=[])
        if item["status"] == "retired":
            new_block = ""
            new_marker = ""
        else:
            target = body_target(article, working, item)
            layout = settings["image_caption" if item["type"] == "image" else "video_caption"]
            new_block = media_block(item, f"<{target}>", layout)
            new_marker = f'{numbered_placeholder(item)} <!-- media-id: {ident} -->'
        outline_blocks[ident] = (before_label, display_media_number(old), new_marker)
        for name in old["section_ids"]:
            blocks.setdefault(name, []).append((old, old_target, new_block))

    files = {source: None for source in assets}
    for source, target in assets.items():
        if target is None:
            continue
        if files.get(target) is not None or (target.exists() and target not in assets):
            raise StateError(f"Media filename already exists: {target}")
        files[target] = source
    active_numbers = {display_media_number(item) for item in items.values()
                      if item["status"] != "retired" and item.get("caption")}
    return blocks, outline_blocks, numbers, files, events, removed - active_numbers


def number_pattern(label):
    return rf"(?<![A-Za-z0-9_/]){re.escape(label)}(?![\d_])"


def rewrite_media(text, replacements, numbers):
    # Replace each original block once. Other reader references follow its new number.
    if not replacements and not numbers:
        return text
    pieces = sorted(replacements, key=len, reverse=True)
    parts = [re.escape(piece) for piece in pieces]
    if numbers:
        parts.extend([r"(?P<tick>`+)[^\n]*?(?P=tick)", r"\]\(<[^>\n]+>\)|\]\([^()\n]*\)|https?://[^\s)>]+"])
        parts.extend(number_pattern(label) for label in numbers)
    pattern = re.compile("|".join(parts))

    def replacement(match):
        return replacements.get(match[0], numbers.get(match[0], match[0]))

    lines = text.splitlines(keepends=True)
    output, last = [], 0
    for token in MarkdownIt("commonmark", {"html": True}).parse(text):
        if token.type in {"fence", "code_block"} and token.map:
            start, end = token.map
            output.extend((pattern.sub(replacement, "".join(lines[last:start])), "".join(lines[start:end])))
            last = end
    output.append(pattern.sub(replacement, "".join(lines[last:])))
    return "".join(output)


def check_removed_numbers(text, removed, name):
    if not removed:
        return
    for token in MarkdownIt("commonmark", {"html": True}).parse(text):
        if token.type != "inline":
            continue
        visible = "".join(child.content for child in token.children if child.type in {"text", "image"})
        for label in sorted(removed):
            if re.search(number_pattern(label), visible):
                raise StateError(f"Removed media {label} is still mentioned in {name}; include the wording change in the plan")


def working_outline(root, bound):
    parent = bound.parent if bound.is_relative_to(root / "article") else root / "outline"
    return inside(root, parent, "outline-working.md")


def match_outline_media(text, markers, path):
    pattern = r"^【(?:图片|视频)占位 (?P<label>[^｜\n】]+)(?:｜[^\n】]*)?】(?:[ \t]+<!-- media-id: (?P<id>(?:IMG|VID)-\d+) -->)?$"
    candidates = list(re.finditer(pattern, text, re.M))
    replacements, results = {}, []
    for ident, (label, number, replacement) in markers.items():
        matches = [match for match in candidates if match["id"] == ident]
        if not matches:
            matches = [match for match in candidates if not match["id"] and match["label"].split("：", 1)[0] == number]
        if len(matches) > 1:
            raise StateError(f"Ambiguous outline marker for {ident} in {path}")
        result = {"path": path, "media_id": ident, "expected": label}
        if matches:
            match = matches[0]
            result.update(found=match["label"], status="matched" if match["label"] == label else "different_title")
            replacements[match[0]] = replacement
        else:
            result["status"] = "missing"
        results.append(result)
    return replacements, results


def changes_for_plan(root, plan, edits, at, token):
    article = root / "article"
    metadata_path, progress_path = article / "metadata.json", article / "progress.json"
    meta, progress = read_json(metadata_path), read_json(progress_path)
    if meta.get("schema_version") != 3 or progress.get("schema_version") != 3 or not progress["is_active"]:
        raise StateError("Revisions need a contract-3 active work draft")
    version = progress["outline_version"]
    outline_record = meta["outlines"][version]
    working = inside(article, article, progress["working_file"], exists=True)
    outline = inside(root, article, outline_record["file"], exists=True)
    mirror = working_outline(root, outline)
    outlines = [outline] + ([mirror] if mirror.is_file() else [])
    current = {path: path.read_bytes() for path in [working, progress_path, metadata_path, *outlines]}
    original_meta, original_progress = json.loads(current[metadata_path]), json.loads(current[progress_path])
    if meta != original_meta or progress != original_progress:
        raise StateError("Article state changed; reload the revision plan")
    original = current[working].decode("utf-8")
    old_title, units = extract_sections(original)
    edited = dict(units)
    if len(edits["title"]) > 1:
        raise StateError("Provide at most one title edit")
    title = old_title
    if edits["title"]:
        edit = edits["title"][0]
        if edit["before"] != old_title or not edit["after"].strip() or "\n" in edit["after"] or "\r" in edit["after"]:
            raise StateError("Title edit needs the exact old title and a new one-line title")
        title = edit["after"]
    for edit in edits["body"]:
        name = edit["section"]
        if name not in edited:
            raise StateError(f"Unknown section: {name}")
        edited[name] = exact(edited[name], edit["before"], edit["after"], name)

    settings = preferences(root, meta["scenario"])["media"]
    blocks, markers, numbers, files, events, removed = media_edits(root, working, progress, edits["media"], settings, plan["basis"], at)
    for name, before in edited.items():
        replacements = {find_media_block(item, before, target): after for item, target, after in blocks.get(name, [])}
        edited[name] = rewrite_media(before, replacements, numbers).strip("\n")
        check_removed_numbers(edited[name], removed, name)

    outline_updates, outline_media = {}, []
    for path in outlines:
        original_outline = current[path].decode("utf-8")
        newline = "\r\n" if "\r\n" in original_outline else "\n"
        text = original_outline.replace("\r\n", "\n")
        if title != old_title:
            text = exact(text, f"# {old_title}\n", f"# {title}\n", path.name)
        for edit in edits["outline"]:
            text = exact(text, edit["before"], edit["after"], path.name)
        replacements, matches = match_outline_media(text, markers, path.relative_to(root).as_posix())
        outline_media.extend(matches)
        updated = rewrite_media(text, replacements, numbers)
        check_removed_numbers(updated, removed, path.name)
        if updated != original_outline.replace("\r\n", "\n"):
            outline_updates[path] = updated.replace("\n", newline).encode("utf-8")

    body = original if title == old_title else exact(original, f"# {old_title}", f"# {title}", working.name)
    touched = []
    replies = [edit["reply"] for entries in edits.values() for edit in entries if edit.get("reply")]
    basis = "\n".join([plan["basis"], *dict.fromkeys(replies)])
    for section in progress["sections"]:
        name = section["section_id"]
        if units[name] == edited[name] and name not in blocks:
            continue
        if section["status"] in {"pending", "inherited"}:
            raise StateError(f"Open {name} as an active draft before revising it")
        touched.append(name)
        body = replace_section(body, name, edited[name])
        if name != "lead":
            heading = "### " if section.get("parent_section_id") else "## "
            first = edited[name].split("\n", 1)[0]
            if first.startswith(heading):
                section["title"] = first[len(heading):]
        section["draft_ref"] += "（局部修订）"
        if section["status"] == "confirmed":
            confirmation = section["confirmation"]
            confirmation.update(draft_ref=section["draft_ref"], confirmed_at=at,
                                content_sha256=text_digest(edited[name]),
                                user_message=f'{confirmation["user_message"]}\n{basis}',
                                media=[proof(item) for item in progress["media"] if item["status"] == "approved"
                                       and name in item["section_ids"]])
            section["media_updates"] = []
    if body == original and not outline_updates and not edits["media"]:
        return {}, touched, current, {}, outline_media

    if outline in outline_updates:
        if any(record["outline_version"] == version for record in meta["articles"].values()):
            raise StateError("Active outline is shared by an archived body; use an authorized new outline version")
        outline_record.update(title=title, content_sha256=digest(outline_updates[outline]))
        outline_record["change_summary"] += " 同步本轮局部修订。"
    body_version = working.parent.name
    if not re.fullmatch(r"v[0-9]{3,}", body_version):
        body_version = version
    for event in events:
        event.update(batch_id=token, article_version=body_version)
    meta["asset_maintenance"].extend(events)
    snapshot = working.parent / ".drafts" / f"revision-{token}.json"
    snapshot_data = {"at": at, "basis": basis, "title": old_title, "working_file": progress["working_file"],
                     "sections": [{"section_id": name, "text": units[name], "section_record": deepcopy(section)}
                                  for section in original_progress["sections"] if (name := section["section_id"]) in touched],
                     "outlines": {path.relative_to(root).as_posix(): current[path].decode("utf-8") for path in outline_updates},
                     "assets": events}
    meta.setdefault("repairs", []).append({"at": at, "reason": "应用已指定范围的局部修订", "user_message": basis,
                                            "outline_version": version, "prior_outline_sha256": digest(current[outline]),
                                            "prior_work_snapshot": snapshot.relative_to(article).as_posix()})
    changes = {**files, **outline_updates, working: body.encode("utf-8"), metadata_path: json_bytes(meta),
               progress_path: json_bytes(progress), snapshot: json_bytes(snapshot_data)}
    checked = inspect(root, working_override=body, progress_override=progress, metadata_override=meta,
                      outline_overrides=outline_updates, file_overrides=files)
    if checked["errors"] or checked["warnings"]:
        raise StateError("Revision candidate is inconsistent: " + "; ".join(checked["errors"] + checked["warnings"]))
    old_assets = {root / event["source"]: event["sha256"] for event in events}
    return changes, touched, current, {path: old_assets.get(path) for path in files}, outline_media


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_json(path, value):
    reject_links(path.absolute())
    temporary = path.with_name(path.name + ".write-" + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            stream.write(json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def file_digest(path):
    if not path.is_file():
        return None
    with path.open("rb") as stream:
        return hash_stream(stream, "sha256").hexdigest()


def recover_revision(root, journal, *, apply=False):
    article = root / "article"
    token = journal.get("transaction_id", "")
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise StateError("Invalid revision transaction ID")
    metadata_path, progress_path = article / "metadata.json", article / "progress.json"
    working = inside(article, article, journal["working_file"])
    if not re.fullmatch(r"(?:v[0-9]{3,}/)?article-working\.md", journal["working_file"]):
        raise StateError("Invalid revision working path")
    allowed = {metadata_path, progress_path, working, working.parent / ".drafts" / f"revision-{token}.json"}
    outline_pattern = (r"outline/(?:outline-working|(?:v[0-9]{3,}/)?outline-v[0-9]{3,})\.md"
                       r"|article/v[0-9]{3,}/outline-(?:v[0-9]{3,}|working)\.md")
    archive_name = journal.get("archive_file")
    if archive_name and not re.fullmatch(r"article/(?:v[0-9]{3,}/)?article-v[0-9]{3,}\.md", archive_name):
        raise StateError("Invalid archive transaction path")
    files, outlines, archives, effective, operations = {}, {}, {}, {}, []
    for entry in journal["files"]:
        name = entry["target"]
        target = inside(root, root, name)
        asset = is_article_asset(article, target)
        outline = bool(re.fullmatch(outline_pattern, name))
        if target in effective or (target not in allowed and not asset and not outline and name != archive_name):
            raise StateError(f"Invalid or duplicate revision target: {name}")
        before, after = entry["before_sha256"], entry["after_sha256"]
        if name == archive_name and before is not None:
            raise StateError("Archive transaction cannot overwrite an existing version")
        if after is None and not asset:
            raise StateError(f"Revision cannot remove a manuscript or state file: {name}")
        if any(value is not None and not re.fullmatch(r"[0-9a-f]{64}", value) for value in (before, after)):
            raise StateError(f"Invalid revision digest: {name}")
        pending = target.with_name(f".{target.name}.pending-{token}") if after is not None else None
        if pending is not None:
            reject_links(pending)
            if pending.exists() and file_digest(pending) != after:
                raise StateError(f"Revision staged file changed: {name}")
        if target.exists() and not target.is_file():
            raise StateError(f"Revision target is not a file: {name}")
        current = file_digest(target)
        if current == after:
            source = target if after is not None else None
        elif current == before and (pending is None or pending.is_file()):
            source = pending
            operations.append((target, source, before, after))
        else:
            raise StateError(f"Revision file changed outside the transaction: {name}")
        effective[target] = source
        if asset:
            files[target] = source
        if outline:
            outlines[target] = source.read_bytes()
        if name == archive_name:
            archives[target] = source
    if not {metadata_path, progress_path, working}.issubset(effective):
        raise StateError("Incomplete revision transaction")
    meta = read_json(effective[metadata_path])
    progress = read_json(effective[progress_path])
    if progress["working_file"] != journal["working_file"]:
        raise StateError("Revision transaction disagrees with the working file")
    bound = inside(root, article, meta["outlines"][progress["outline_version"]]["file"])
    if outlines.keys() - {bound, working_outline(root, bound)}:
        raise StateError("Revision can only change the bound outline and its working copy")
    if archive_name:
        record = meta["articles"].get(progress["archived_article_version"], {})
        if not archives or progress["is_active"] or "article/" + record.get("file", "") != archive_name:
            raise StateError("Archive transaction disagrees with the version record")
    working_text = effective[working].read_text(encoding="utf-8")
    report = inspect(root, metadata_override=meta, progress_override=progress, working_override=working_text,
                     outline_overrides=outlines, file_overrides=files, archive_overrides=archives,
                     reviewable_drift=journal.get("reviewable_drift"))
    if report["errors"]:
        raise StateError("Revision recovery candidate is inconsistent: " + "; ".join(report["errors"]))
    retained = None
    if media_id := journal.get("media_deletion_id"):
        item = next((item for item in progress["media"] if item["id"] == media_id
                     and item["status"] == "approved" and item["file"]), None)
        deletions = {path for path, source in files.items() if source is None}
        if not item or not deletions:
            raise StateError("Media deletion transaction needs a retained asset and a deletion")
        retained = inside(root, article, item["file"])
        if retained in deletions:
            raise StateError("Media deletion transaction would remove its retained asset")
        texts = {working: working_text, **{path: data.decode("utf-8") for path, data in outlines.items()}}
        check_deletion_references(root, deletions, meta, progress, texts)
    if apply:
        for target, source, before, after in operations:
            reject_links(target)
            if file_digest(target) != before or (source is not None and file_digest(source) != after):
                raise StateError(f"Revision file changed before commit: {target}")
            if source is None:
                if retained is not None:
                    reject_links(retained)
                    if file_digest(retained) != item["sha256"]:
                        raise StateError(f"Retained media did not pass verification: {retained}")
                target.unlink()
            else:
                os.replace(source, target)
        for target in effective:
            target.with_name(f".{target.name}.pending-{token}").unlink(missing_ok=True)
        (article / "transaction.json").unlink()
    return {"read_only": not apply, "work_files": [entry["target"] for entry in journal["files"]]}


def revise(root, plan, *, at, apply=False):
    article = root / "article"
    journal_path = article / "transaction.json"
    reject_links(journal_path)
    checked = inspect(root)
    if checked["errors"] or checked["warnings"]:
        issues = checked["errors"] + checked["warnings"]
        if any(issue.startswith("Confirmed section text changed:") for issue in issues):
            issues.append("Use reconcile to review the current section before revising.")
        raise StateError("Check article state before revising: " + "; ".join(issues))
    edits, choices = selected(plan)
    pending = [choice for choice in choices if choice["decision"] == "pending"]
    if apply and pending:
        raise StateError("Resolve the pending review items before applying this plan")
    token = uuid.uuid4().hex
    changes, sections, original, old_assets, outline_media = changes_for_plan(root, plan, edits, at, token)
    result = {"read_only": not apply, "sections": sections, "decisions": choices, "outline_media": outline_media,
              "files": [{"path": path.relative_to(root).as_posix(),
                         "action": "remove" if content is None else "write"} for path, content in changes.items()
                        if not path.name.startswith("revision-")],
              "diff": "".join(line for path, content in changes.items() if path.suffix == ".md"
                              for line in unified_diff(original[path].decode("utf-8").splitlines(keepends=True),
                                                       content.decode("utf-8").splitlines(keepends=True),
                                                       fromfile=path.relative_to(root).as_posix(),
                                                       tofile=path.relative_to(root).as_posix()))}
    if not apply or not changes:
        return result
    commit_revision_files(root, changes, original, old_assets, token)
    result["snapshot"] = next(path.relative_to(root).as_posix() for path in changes if path.name == f"revision-{token}.json")
    return result


def commit_revision_files(root, changes, original, old_assets, token, *, archive=None, reviewable_drift=None,
                          media_deletion_id=None):
    article = root / "article"
    journal_path = article / "transaction.json"
    reject_links(journal_path)
    if any(path.read_bytes() != content for path, content in original.items()):
        raise StateError("Draft, outline or state changed during preview; reload the revision plan")
    journal = {"schema_version": 2, "transaction_id": token,
               "working_file": read_json(article / "progress.json")["working_file"], "files": []}
    if archive is not None:
        journal["archive_file"] = archive.relative_to(root).as_posix()
    if reviewable_drift:
        journal["reviewable_drift"] = reviewable_drift
    if media_deletion_id:
        journal["media_deletion_id"] = media_deletion_id
    staged = []
    journal_pending = article / f".transaction.pending-{token}"
    published = False
    try:
        for target, content in changes.items():
            reject_links(target)
            after = None
            if content is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
                pending_file = target.with_name(f".{target.name}.pending-{token}")
                reject_links(pending_file)
                with pending_file.open("xb") as stream:
                    staged.append(pending_file)
                    if isinstance(content, Path):
                        with content.open("rb") as asset:
                            shutil.copyfileobj(asset, stream)
                    else:
                        stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                after = file_digest(pending_file)
            before = digest(original[target]) if target in original else old_assets.get(target)
            if file_digest(target) != before:
                raise StateError(f"Revision target changed while staging: {target}")
            journal["files"].append({"target": target.relative_to(root).as_posix(),
                                     "before_sha256": before, "after_sha256": after})
        recover_revision(root, journal)
        with journal_pending.open("xb") as stream:
            stream.write(json_bytes(journal))
            stream.flush()
            os.fsync(stream.fileno())
        # Publish a complete journal without replacing another transaction.
        os.link(journal_pending, journal_path)
        published = True
    finally:
        journal_pending.unlink(missing_ok=True)
        if not published:
            for path in staged:
                path.unlink(missing_ok=True)
    recover_revision(root, journal, apply=True)
