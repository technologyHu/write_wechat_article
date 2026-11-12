"""Article checks are read-only by default; every mutation needs an explicit command and --apply."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from article_cleanup import temp_inventory
from article_editorial import mobile_preview, preferences, review_markdown
from article_export import export_article, select_body
from article_lifecycle import archive_article, finalize_article, reconcile
from article_media import adopt_media
from article_media_review import review_media
from article_revision import atomic_json, recover_revision, revise
from article_state import (IMAGE_EXTENSIONS, StateError, assemble, canonical, checked_root, deletion_references, digest,
                           extract_sections, inside, inspect, latest_operations, media_label,
                           media_targets, numbered_placeholder, proof, protected_files, read_json,
                           reject_links, replace_section, schema_errors, text_digest)
from article_temp import record_generated, register_temporary, temporary_receipts


def now():
    return datetime.now(timezone.utc).isoformat()


def load_state(root):
    metadata = read_json(root / "article/metadata.json")
    if metadata.get("schema_version") != 3:
        raise StateError("Mutations require contract 3; do not manufacture legacy approvals.")
    progress = read_json(root / "article/progress.json")
    return metadata, progress


def assert_valid(root, **kwargs):
    report = inspect(root, **kwargs)
    if report["errors"]:
        raise StateError("; ".join(report["errors"]))
    if report["warnings"]:
        raise StateError("Recover unfinished operations before mutation: " + "; ".join(report["warnings"]))


def asset_event(root, event, status):
    metadata = read_json(root / "article/metadata.json")
    metadata["asset_maintenance"].append({**event, "status": status, "at": now()})
    atomic_json(root / "article/metadata.json", metadata)


def plan_cleanup(root):
    assert_valid(root)
    metadata, progress = load_state(root)
    if progress["phase"] not in {"archived", "finalized"} or progress["is_active"]:
        raise StateError("Stage images only after this cycle has been archived and is inactive.")
    protected = protected_files(root, metadata, progress)
    moves = []
    article = root / "article"
    for assets in (article / "assets", article / progress["archived_article_version"] / "assets"):
        reject_links(assets)
        for path in sorted(assets.rglob("*")):
            reject_links(path)
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS and path.resolve() not in protected:
                moves.append({"source": path.relative_to(root).as_posix(), "sha256": digest(path.read_bytes())})
    return {"article_version": progress["archived_article_version"], "moves": moves,
            "protected": sorted(p.relative_to(root).as_posix() for p in protected)}


def stage_unused(root, *, apply=False):
    plan = plan_cleanup(root)
    if not apply:
        return {"read_only": True, **plan}
    batch = "stage-" + uuid.uuid4().hex
    results = []
    for item in plan["moves"]:
        source = inside(root, root, item["source"], exists=True)
        relative = source.relative_to(root / "article")
        if relative.parts[0] == "assets":
            relative = relative.relative_to("assets")
        target = inside(root, root, f".tmp/images/{batch}/{relative.as_posix()}")
        if target.exists() or digest(source.read_bytes()) != item["sha256"]:
            raise StateError("Image changed or staging target already exists")
        event = {"operation_id": uuid.uuid4().hex, "batch_id": batch, "action": "move",
                 "article_version": plan["article_version"], "source": item["source"],
                 "target": target.relative_to(root).as_posix(), "sha256": item["sha256"],
                 "reason": "Not used by retained bodies, active work, confirmed outlines or selected publishing assets"}
        asset_event(root, event, "planned")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            reject_links(target)
            source.replace(target)
        except OSError:
            asset_event(root, event, "failed")
            raise
        asset_event(root, event, "completed")
        results.append(event["target"])
    assert_valid(root)
    return {"read_only": False, "moved": results, "article_version": plan["article_version"]}


def clean_temp(root, *, apply=False):
    assert_valid(root)
    metadata, progress = load_state(root)
    if progress["phase"] != "finalized" or progress["is_active"] or not progress["completion_basis"]:
        raise StateError("Temporary cleanup requires explicit finalized state and completion basis.")
    if progress["finalized_article_version"] != metadata["latest_article_version"]:
        raise StateError("Finalization marker is not for the latest archived article")
    protected = protected_files(root, metadata, progress)
    temp = inside(root, root, ".tmp")
    if not temp.exists():
        return {"read_only": not apply, "deleted": [], "candidates": []}
    owned = temp_inventory(root, metadata, progress)
    receipts = temporary_receipts(root)
    receipt_paths = set()
    for target, (receipt, entry) in receipts.items():
        if int(entry["version"][1:]) > int(progress["finalized_article_version"][1:]):
            continue
        if target.exists():
            if target.stat().st_mtime_ns != entry["mtime_ns"]:
                raise StateError("Temporary file changed; nothing deleted: " + str(target))
            owned[target] = entry["sha256"]
        owned[receipt] = digest(receipt.read_bytes())
        receipt_paths.add(receipt)
    files = []
    for path in sorted(temp.rglob("*")):
        reject_links(path)
        if not path.is_file():
            continue
        if path.resolve() in protected or path not in owned:
            raise StateError("Unknown/protected file in .tmp; nothing deleted: " + str(path))
        if digest(path.read_bytes()) != owned[path]:
            raise StateError("Temporary file changed; nothing deleted: " + str(path))
        files.append(path)
    if referenced := deletion_references(root, files, metadata, progress, {}):
        raise StateError("Temporary file still used; nothing deleted: " + str(next(iter(referenced))))
    files.sort(key=lambda path: path in receipt_paths)
    if not apply:
        return {"read_only": True, "candidates": [p.relative_to(root).as_posix() for p in files]}
    deleted = []
    batch = "delete-" + uuid.uuid4().hex
    for path in files:
        # Recheck immediately before each filesystem mutation.
        checked = inside(root, root, path.relative_to(root).as_posix(), exists=True)
        if digest(checked.read_bytes()) != owned[path]:
            raise StateError("Temporary file changed during cleanup")
        event = {"operation_id": uuid.uuid4().hex, "batch_id": batch, "action": "delete",
                 "article_version": progress["finalized_article_version"],
                 "source": path.relative_to(root).as_posix(), "target": None,
                 "sha256": owned[path], "reason": progress["completion_basis"]["message"]}
        asset_event(root, event, "planned")
        try:
            checked.unlink()
        except OSError:
            asset_event(root, event, "failed")
            raise
        asset_event(root, event, "completed")
        deleted.append(event["source"])
    # Inventory entries describe still-existing candidates; past paths remain in the maintenance log.
    progress["candidates"] = [c for c in progress["candidates"]
                              if inside(root, root / "article", c["file"]).exists()]
    atomic_json(root / "article/progress.json", progress)
    for directory in sorted((p for p in temp.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        reject_links(directory)
        directory.rmdir()
    temp.rmdir()
    return {"read_only": False, "deleted": deleted}


def save_work(root, candidate_working: Path, candidate_progress: Path, *, apply=False):
    return commit_work(root, candidate_working.read_text(encoding="utf-8"),
                       read_json(candidate_progress), apply=apply)


def commit_work(root, working, progress, *, apply=False, expected=None):
    assert_valid(root, progress_override=progress, working_override=working)
    current_file = root / "article/progress.json"
    if current_file.exists():
        current = read_json(current_file)
        if current.get("is_active"):
            if current.get("session_id") != progress["session_id"]:
                raise StateError("Another authoring session owns the active working files")
            if current["working_file"] != progress["working_file"]:
                raise StateError("An active session cannot change its working file path")
            previous = {section["section_id"]: section for section in current["sections"]}
            for section in progress["sections"]:
                if not section.get("reopened_at"):
                    continue
                old = previous.get(section["section_id"], {})
                changed = any(old.get(key) != section.get(key) for key in ("reopened_at", "reopened_snapshot_sha256"))
                if changed and old.get("status") not in {"confirmed", "inherited"}:
                    raise StateError("Only a previously approved section can be reopened: " + section["section_id"])
    if not apply:
        return {"read_only": True, "session_id": progress["session_id"], "phase": progress["phase"]}
    journal_file = root / "article/transaction.json"
    if journal_file.exists():
        raise StateError("Recover the existing work transaction first")
    transaction = uuid.uuid4().hex
    entries = []
    files = [(progress["working_file"], working.encode("utf-8")),
             ("progress.json", (json.dumps(progress, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))]
    targets = [inside(root, root / "article", name) for name, _ in files]
    old_digests = [digest(target.read_bytes()) if target.exists() else None for target in targets]
    if expected is not None and old_digests != expected:
        raise StateError("Working files changed during the edit; reload the current draft")
    for (_, data), target, before in zip(files, targets, old_digests):
        pending = target.with_name("." + target.name + ".pending-" + transaction)
        reject_links(pending)
        with pending.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        entries.append({"target": target.relative_to(root).as_posix(), "pending": pending.relative_to(root).as_posix(),
                        "before_sha256": before,
                        "after_sha256": digest(data)})
    journal = {"schema_version": 1, "transaction_id": transaction, "files": entries}
    atomic_json(journal_file, journal)
    return recover(root, apply=True)


def active_work(root):
    assert_valid(root)
    progress_bytes = (root / "article/progress.json").read_bytes()
    progress = json.loads(progress_bytes)
    if not progress["is_active"]:
        raise StateError("Open an authorized working revision before editing an archived article")
    path = inside(root, root / "article", progress["working_file"], exists=True)
    body = path.read_bytes()
    return path, body.decode("utf-8"), progress, [digest(body), digest(progress_bytes)]


def snapshot_digest(snapshot):
    return digest(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def edit_section(root, section_id, expected_sha256, draft_ref, *, text=None, old_text=None,
                 restore_from=None, apply=False):
    path, working, progress, expected = active_work(root)
    _, units = extract_sections(working)
    section = next((item for item in progress["sections"] if item["section_id"] == section_id), None)
    if section is None or not draft_ref or draft_ref == section["draft_ref"]:
        raise StateError("Choose an existing section and a new draft reference")
    before = units[section_id]
    if text_digest(before) != expected_sha256:
        raise StateError("Section changed since it was displayed; reload before editing")
    if (text is None) == (restore_from is None) or (restore_from is not None and old_text is not None):
        raise StateError("Provide replacement text or a saved draft to restore")
    restored = None
    if restore_from is not None:
        restored = read_json(restore_from)
        if (restored["session_id"] != progress["session_id"] or restored["section_id"] != section_id
                or restored["working_file"] != progress["working_file"]
                or text_digest(restored["text"]) != restored["content_sha256"]):
            raise StateError("Snapshot does not match this working section")
        text = restored["text"]
    if old_text is not None:
        if not old_text or before.count(old_text) != 1:
            raise StateError("The original phrase must occur exactly once in the target section")
        text = before.replace(old_text, text, 1)
    after = canonical(text)
    if before == after:
        raise StateError("Section text did not change")
    snapshot = {"session_id": progress["session_id"], "working_file": progress["working_file"],
                "section_id": section_id, "draft_ref": section["draft_ref"], "text": before,
                "content_sha256": text_digest(before), "section_record": section.copy()}
    restore_confirmation = restored is not None and snapshot_digest(restored) == section.get("reopened_snapshot_sha256")
    if restore_confirmation:
        section.clear()
        section.update(restored["section_record"])
        if all(item["status"] in {"confirmed", "inherited"} for item in progress["sections"]):
            progress["phase"] = "waiting_media"
    else:
        if section["status"] in {"confirmed", "inherited"}:
            section["reopened_at"] = now()
            section["reopened_snapshot_sha256"] = snapshot_digest(snapshot)
        section.update(status="awaiting_confirmation", draft_ref=draft_ref, confirmation=None,
                       inheritance=None, media_updates=[])
        section.pop("outline_revalidation", None)
        progress["phase"] = "waiting_section"
    candidate = replace_section(working, section_id, after)
    result = commit_work(root, candidate, progress)
    if apply:
        snapshot_path = inside(root, path.parent, f".drafts/{section_id}-{uuid.uuid4().hex}.json")
        snapshot_path.parent.mkdir(exist_ok=True)
        atomic_json(snapshot_path, snapshot)
        result = commit_work(root, candidate, progress, apply=True, expected=expected)
        result["snapshot"] = str(snapshot_path)
    return {**result, "section_id": section_id, "before_sha256": snapshot["content_sha256"],
            "after_sha256": text_digest(after), "text": after, "restored_confirmation": restore_confirmation}


def edit_caption(root, media_id, basis, *, title=None, description=None, remove_description=False, apply=False):
    _, working, progress, expected = active_work(root)
    item = next((item for item in progress["media"] if item["id"] == media_id), None)
    if not item or not item.get("caption") or item["status"] not in {"approved", "planned"} or not item["section_ids"]:
        raise StateError("Select a numbered body image or video with an active caption")
    if not basis.strip() or (description is not None and remove_description):
        raise StateError("Provide the user instruction and one description operation")
    previous = proof(item)
    if title is not None:
        item["caption"]["title"] = title
    if description is not None:
        item["caption"]["description"] = description
    if remove_description:
        item["caption"].pop("description", None)
    if proof(item) == previous:
        raise StateError("Caption did not change")

    def block(label, target, desc, separator="\n\n", *, layout="legacy"):
        if layout == "linked_caption":
            caption = f"{label}｜{desc}" if desc else label
            return f"[{caption}]({target})"
        if layout == "link_after":
            caption = f"{label}｜{desc}" if desc else label
            link = f"![{label}]({target})" if item["type"] == "image" else f"[观看视频]({target})"
            return f"{caption}\n\n{link}"
        prefix = f"![{label}]({target})\n\n{label}" if item["type"] == "image" else f"[{label}]({target})"
        return f"{prefix}{separator}{desc}" if desc else prefix

    _, units = extract_sections(working)
    for section in progress["sections"]:
        name = section["section_id"]
        if name not in item["section_ids"]:
            continue
        if section["status"] not in {"drafting", "awaiting_confirmation", "confirmed", "inherited"}:
            raise StateError("Media caption is not present in a written section: " + name)
        before = units[name]
        if item["status"] == "planned":
            old, new = numbered_placeholder(previous), numbered_placeholder(item)
        else:
            targets = {formatted for target in media_targets(item) for formatted in (target, f"<{target}>")}
            old_description = previous["caption"].get("description")
            matches = []
            label = media_label(previous)
            for target in targets:
                markup = re.escape(block(label, target, None))
                if old_description:
                    markup += r"(?P<separator>\n\n|｜)" + re.escape(old_description)
                    if not old_description.endswith("。"):
                        markup += "。?"
                patterns = {"legacy": markup,
                            "link_after": re.escape(block(label, target, old_description, layout="link_after"))}
                if item["type"] == "video" and old_description:
                    patterns["linked_caption"] = re.escape(block(label, target, old_description, layout="linked_caption"))
                for layout, pattern in patterns.items():
                    matches.extend((target, match, layout) for match in re.finditer(pattern + r"(?=\n\n|$)", before))
            if len(matches) != 1:
                raise StateError("Expected one registered caption block in " + name)
            target, match, layout = matches[0]
            old = match.group()
            separator = match.groupdict().get("separator", "\n\n")
            new = block(media_label(item), target, item["caption"].get("description"), separator, layout=layout)
        if before.count(old) != 1:
            raise StateError("Expected one registered caption block in " + name)
        start = before.index(old)
        after = before.replace(old, new, 1)
        working = replace_section(working, name, after)
        if section["status"] in {"confirmed", "inherited"}:
            section["media_updates"].append({
                "kind": "caption", "before_sha256": text_digest(before), "after_sha256": text_digest(after),
                "media": proof(item), "basis": {"kind": "user", "message": basis, "at": now()},
                "replacements": [{"before": old, "after": new, "after_start": start}],
            })
    result = commit_work(root, working, progress, apply=apply, expected=expected)
    return {**result, "media_id": media_id, "caption": item["caption"], "sections": item["section_ids"]}


def recover(root, *, apply=False):
    journal_file = root / "article/transaction.json"
    report = {"read_only": not apply, "work_files": [], "asset_operations": []}
    replacements, journal = [], None
    prospective = {}
    if journal_file.exists():
        journal = read_json(journal_file)
        if journal.get("schema_version") == 2:
            return recover_revision(root, journal, apply=apply)
        if journal.get("schema_version") != 1 or not recheck_journal(journal):
            raise StateError("Invalid work transaction journal")
        for entry in journal["files"]:
            target = inside(root, root, entry["target"])
            pending = inside(root, root, entry["pending"])
            current = digest(target.read_bytes()) if target.exists() else None
            if current == entry["after_sha256"]:
                data = target.read_bytes()
                if pending.exists() and digest(pending.read_bytes()) != entry["after_sha256"]:
                    raise StateError("Conflicting pending work file")
            elif current == entry["before_sha256"] and pending.is_file() and digest(pending.read_bytes()) == entry["after_sha256"]:
                data = pending.read_bytes()
                replacements.append((pending, target))
            else:
                raise StateError("Work file changed outside transaction; recover without overwriting it")
            prospective[target.name] = data
            report["work_files"].append(entry["target"])
    metadata = read_json(root / "article/metadata.json")
    contract_errors = schema_errors(metadata, "metadata")
    if contract_errors:
        raise StateError("; ".join(contract_errors))
    outcomes = []
    for event in latest_operations(metadata).values():
        if event["status"] != "planned":
            continue
        source = inside(root, root, event["source"])
        target = inside(root, root, event["target"]) if event["target"] else None
        if event["action"] in {"move", "restore"}:
            if source.exists() and digest(source.read_bytes()) == event["sha256"] and target and not target.exists():
                outcome = "failed"
            elif not source.exists() and target and target.is_file() and digest(target.read_bytes()) == event["sha256"]:
                outcome = "completed"
            else:
                raise StateError("Ambiguous interrupted move; no overwrite: " + event["source"])
        elif event["action"] == "delete":
            if not source.exists():
                outcome = "completed"
            elif digest(source.read_bytes()) == event["sha256"]:
                outcome = "failed"
            else:
                raise StateError("Interrupted deletion target changed")
        else:
            raise StateError("Unknown asset operation")
        outcomes.append((event, outcome))
        report["asset_operations"].append({"operation_id": event["operation_id"], "outcome": outcome})
    progress_path = root / "article/progress.json"
    progress = json.loads(prospective["progress.json"].decode("utf-8")) if "progress.json" in prospective else read_json(progress_path) if progress_path.exists() else None
    working = prospective.get("article-working.md")
    working = working.decode("utf-8") if working is not None else None
    inventory_changed = False
    if progress is not None:
        progress_errors = schema_errors(progress, "progress")
        if progress_errors:
            raise StateError("; ".join(progress_errors))
        if journal and "article/" + progress["working_file"] not in report["work_files"]:
            raise StateError("Work transaction does not match the declared working file")
        deleted = {inside(root, root, e["source"]): e["sha256"] for e in latest_operations(metadata).values()
                   if e["action"] == "delete" and e["status"] == "completed"}
        deleted.update({inside(root, root, e["source"]): e["sha256"] for e, outcome in outcomes
                        if e["action"] == "delete" and outcome == "completed"})
        retained = []
        for candidate in progress["candidates"]:
            path = inside(root, root / "article", candidate["file"])
            if not path.exists() and deleted.get(path) == candidate["sha256"]:
                inventory_changed = True
            else:
                retained.append(candidate)
        progress["candidates"] = retained
    # Validate the prospective pair and all recovery outcomes before mutating either file.
    validation = inspect(root, progress_override=progress, working_override=working)
    if validation["errors"]:
        raise StateError("Recovery candidate is inconsistent: " + "; ".join(validation["errors"]))
    if apply:
        for pending, target in replacements:
            pending.replace(target)
        if journal:
            for entry in journal["files"]:
                pending = inside(root, root, entry["pending"])
                if pending.exists():
                    pending.unlink()
            journal_file.unlink()
        for event, outcome in outcomes:
            payload = {k: v for k, v in event.items() if k not in {"status", "at"}}
            asset_event(root, payload, outcome)
        if inventory_changed:
            atomic_json(progress_path, progress)
    return report


def recheck_journal(journal):
    entries = journal.get("files")
    if not isinstance(entries, list) or len(entries) != 2 or any(not isinstance(e, dict) for e in entries):
        return False
    targets = {e["target"] for e in entries if isinstance(e.get("target"), str)}
    if len(targets) != 2 or "article/progress.json" not in targets:
        return False
    working, = targets - {"article/progress.json"}
    if not re.fullmatch(r"article/(?:v[0-9]{3,}/)?article-working\.md", working):
        return False
    token = journal.get("transaction_id", "")
    if not isinstance(token, str) or len(token) != 32 or any(c not in "0123456789abcdef" for c in token):
        return False
    def is_digest(value):
        return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    for entry in entries:
        target = Path(entry["target"])
        expected_pending = target.with_name("." + target.name + ".pending-" + token)
        if (entry.get("pending") != expected_pending.as_posix()
                or "before_sha256" not in entry
                or (entry["before_sha256"] is not None and not is_digest(entry["before_sha256"]))
                or not is_digest(entry.get("after_sha256"))):
            return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "sections", "assemble", "archive", "finalize", "export",
                                           "adopt-media", "register-temp", "revise", "reconcile", "review-format",
                                           "review-media", "preview-mobile",
                                           "preferences", "plan-cleanup", "stage-unused", "clean-temp", "save-work",
                                           "recover", "edit-section", "edit-caption"])
    parser.add_argument("article_dir")
    parser.add_argument("--apply", action="store_true", help="Execute this explicitly selected mutation; not a new user approval gate")
    parser.add_argument("--working", type=Path)
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--section")
    parser.add_argument("--expect-sha256")
    parser.add_argument("--draft-ref")
    parser.add_argument("--text", type=Path)
    parser.add_argument("--old-text", type=Path)
    parser.add_argument("--restore-from", type=Path)
    parser.add_argument("--media-id")
    parser.add_argument("--media-number", help="Displayed media number, such as 图1 or 视频6")
    parser.add_argument("--source", type=Path, help="Local file to adopt or use as a replacement")
    parser.add_argument("--svg", type=Path, help="Editable SVG to adopt alongside the PNG")
    parser.add_argument("--temp-file", type=Path, action="append", help="Temporary output to register; repeat for multiple files")
    parser.add_argument("--origin", help="Tool or workflow that produced a temporary output")
    parser.add_argument("--delete-previous", action="store_true", help="Delete the superseded local media file if unreferenced")
    parser.add_argument("--delete-source", action="store_true", help="Delete the input file after verifying the adopted copy")
    parser.add_argument("--basis")
    parser.add_argument("--title")
    parser.add_argument("--description")
    parser.add_argument("--remove-description", action="store_true")
    parser.add_argument("--version", help="Explicit body version, such as v001")
    parser.add_argument("--output-dir", type=Path, help="Existing ZIP output directory; defaults to exports/ in the article topic directory")
    parser.add_argument("--cleanup", action="store_true", help="After finalize exports a verified ZIP, remove obsolete temporary files and drafts")
    parser.add_argument("--plan", type=Path, help="JSON revision plan")
    parser.add_argument("--release", action="store_true", help="Require an archived body ready for release export")
    parser.add_argument("--output", type=Path, help="HTML output path for preview-mobile")
    args = parser.parse_args(argv)
    try:
        root = checked_root(args.article_dir)
        if args.command == "check":
            result = inspect(root)
        elif args.command == "export":
            if not args.version:
                raise StateError("export needs --version (for example, v001)")
            result = export_article(root, args.version, output_dir=args.output_dir, apply=args.apply, release=args.release)
        elif args.command == "archive":
            if not args.version:
                raise StateError("archive needs --version (for example, v001)")
            result = archive_article(root, args.version, at=now(), basis=args.basis, apply=args.apply)
        elif args.command == "finalize":
            if not args.version:
                raise StateError("finalize needs --version (for example, v001)")
            result = finalize_article(root, args.version, at=now(), basis=args.basis,
                                      output_dir=args.output_dir, apply=args.apply, cleanup=args.cleanup)
        elif args.command == "adopt-media":
            if not args.media_number or not args.source:
                raise StateError("adopt-media needs --media-number and --source")
            result = adopt_media(root, args.media_number, args.source, basis=args.basis, at=now(), svg=args.svg, apply=args.apply,
                                 delete_previous=args.delete_previous, delete_source=args.delete_source)
        elif args.command == "register-temp":
            if not args.temp_file or not args.origin:
                raise StateError("register-temp needs --temp-file and --origin")
            result = register_temporary(root, args.temp_file, origin=args.origin, version=args.version, apply=args.apply)
        elif args.command == "review-media":
            if not args.media_number:
                raise StateError("review-media needs --media-number")
            result = review_media(root, args.media_number, version=args.version)
        elif args.command == "reconcile":
            result = reconcile(root, section_id=args.section, expected_sha256=args.expect_sha256,
                               basis=args.basis, at=now(), apply=args.apply)
        elif args.command == "revise":
            if not args.plan:
                raise StateError("revise needs --plan with a JSON revision plan")
            result = revise(root, read_json(args.plan), at=now(), apply=args.apply)
        elif args.command == "preview-mobile":
            if not args.output:
                raise StateError("preview-mobile needs --output with an .html path")
            article = root / "article"
            if args.version:
                path, content, _, _, _ = select_body(article, args.version)
                markdown = content.decode("utf-8-sig")
            else:
                working = read_json(article / "progress.json")["working_file"]
                path = inside(article, article, working, exists=True)
                markdown, _ = assemble(path.read_text(encoding="utf-8"))
            result = mobile_preview(path, markdown, args.output, apply=args.apply)
            if args.apply:
                record_generated([args.output], "preview-mobile", version=args.version)
        elif args.command in {"review-format", "preferences"}:
            article = root / "article"
            settings = preferences(root, read_json(article / "metadata.json")["scenario"])
            if args.command == "preferences":
                result = settings
            else:
                spans = None
                if args.version:
                    path, _, kind, record, _ = select_body(article, args.version)
                    if kind == "archived":
                        spans = {section["section_id"]: (section["span"]["start_line"] - 1, section["span"]["end_line"])
                                 for section in record.get("chapter_confirmations", [])}
                else:
                    progress = read_json(article / "progress.json")
                    path = inside(root, article, progress["working_file"], exists=True)
                result = {"read_only": True, "file": str(path), "issues": review_markdown(path.read_text(encoding="utf-8-sig"),
                                                                                         settings, spans=spans)}
        elif args.command in {"sections", "assemble"}:
            article = root / "article"
            progress = article / "progress.json"
            working = read_json(progress)["working_file"] if progress.exists() else "article-working.md"
            text = inside(root, article, working, exists=True).read_text(encoding="utf-8")
            if args.command == "sections":
                _, units = extract_sections(text)
                result = {name: {"content_sha256": text_digest(content)} for name, content in units.items()}
            else:
                body, spans = assemble(text)
                result = {"markdown": body, "spans": spans}
        elif args.command == "plan-cleanup":
            result = {"read_only": True, **plan_cleanup(root)}
        elif args.command == "stage-unused":
            result = stage_unused(root, apply=args.apply)
        elif args.command == "clean-temp":
            result = clean_temp(root, apply=args.apply)
        elif args.command == "save-work":
            if not args.working or not args.progress:
                raise StateError("save-work needs --working and --progress candidate files")
            result = save_work(root, args.working, args.progress, apply=args.apply)
        elif args.command == "edit-section":
            if not (args.section and args.expect_sha256 and args.draft_ref):
                raise StateError("edit-section needs --section, --expect-sha256 and --draft-ref")
            result = edit_section(root, args.section, args.expect_sha256, args.draft_ref,
                                  text=args.text.read_text(encoding="utf-8-sig") if args.text else None,
                                  old_text=args.old_text.read_text(encoding="utf-8-sig") if args.old_text else None,
                                  restore_from=args.restore_from, apply=args.apply)
        elif args.command == "edit-caption":
            if not (args.media_id and args.basis):
                raise StateError("edit-caption needs --media-id and the actual user instruction in --basis")
            result = edit_caption(root, args.media_id, args.basis, title=args.title,
                                  description=args.description, remove_description=args.remove_description,
                                  apply=args.apply)
        else:
            result = recover(root, apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get("errors") else 0
    except (StateError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
