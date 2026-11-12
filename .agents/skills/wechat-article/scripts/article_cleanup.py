"""Remove obsolete drafting files after a verified release export."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from zipfile import is_zipfile

from article_revision import atomic_json, file_digest, working_outline
from article_state import StateError, deletion_references, inside, inspect, latest_operations, reject_links
from article_temp import temporary_receipts


def temp_inventory(root, metadata, progress):
    temp = inside(root, root, ".tmp")
    owned = {}
    for event in latest_operations(metadata).values():
        if event["status"] == "completed" and event["action"] == "move":
            target = inside(root, root, event["target"])
            if target.is_relative_to(temp):
                owned[target] = event["sha256"]
    for candidate in progress["candidates"]:
        owned[inside(root, root / "article", candidate["file"])] = candidate["sha256"]
    return owned


def scratch_tree(root, folder, kept):
    files, directories = [], []
    if not folder.exists():
        return files, directories

    def fail(error):
        raise error

    for base, children, names in os.walk(folder, followlinks=False, onerror=fail):
        parent = inside(root, root, Path(base).relative_to(root).as_posix())
        if not parent.is_relative_to(folder):
            raise StateError(f"Cleanup path escapes its directory: {parent}")
        directories.append(parent)
        for name in [*children, *names]:
            path = parent / name
            try:
                reject_links(path)
            except StateError as exc:
                kept[path] = str(exc)
                if name in children:
                    children.remove(name)
                continue
            if name in names and path.is_file():
                files.append(path)
    return files, directories


def cleanup_plan(root, version, package, metadata, progress, *, archive_text=None):
    article = root / "article"
    record = metadata["articles"][version]
    body = inside(root, article, record["file"], exists=archive_text is None)
    working = inside(root, article, progress["working_file"])
    if working.name != "article-working.md" or working.parent != body.parent:
        raise StateError("The working draft is outside the finalized version's directory")
    outline = inside(root, article, metadata["outlines"][record["outline_version"]]["file"], exists=True)
    work_files = {working, inside(root, working.parent, "outline-working.md")}
    if not outline.is_relative_to(article) and record["outline_version"] == metadata["latest_outline_version"]:
        work_files.add(working_outline(root, outline))
    draft_dir = inside(root, working.parent, ".drafts")
    temp_dir = inside(root, root, ".tmp")
    kept = {}
    draft_files, draft_directories = scratch_tree(root, draft_dir, kept)
    temp_files, temp_directories = scratch_tree(root, temp_dir, kept)
    registered = temp_inventory(root, metadata, progress)
    receipts = temporary_receipts(root)
    receipt_paths = {receipt for receipt, _ in receipts.values()}
    candidates = {}
    protected = {body, outline, package.resolve()}
    for path in sorted((work_files | set(draft_files) | set(temp_files)) - receipt_paths):
        if not path.is_file():
            continue
        if path in protected or path.suffix.lower() == ".zip":
            kept[path] = "retained artifact"
            continue
        receipt = receipts.get(path)
        if path.is_relative_to(temp_dir) and path not in registered and receipt is None:
            kept[path] = "unregistered temporary file"
            continue
        if receipt is not None and int(receipt[1]["version"][1:]) > int(version[1:]):
            kept[path] = f"registered for later version {receipt[1]['version']}"
            continue
        sha = file_digest(path)
        if sha is None:
            continue
        expected = receipt[1]["sha256"] if receipt else registered.get(path)
        mtime = path.stat().st_mtime_ns
        if (expected is not None and sha != expected) or (receipt and mtime != receipt[1]["mtime_ns"]):
            kept[path] = "temporary file differs from its recorded digest"
        else:
            reason = ("unused registered temporary output" if path.is_relative_to(temp_dir)
                      else "working draft or draft snapshot of this version")
            if receipt:
                reason += f" ({receipt[1]['origin']}, {receipt[1]['version']})"
            candidates[path] = {"sha256": sha, "reason": reason, "mtime_ns": mtime}

    texts = {body: archive_text} if archive_text is not None else {}
    while candidates:
        referenced = deletion_references(root, candidates, metadata, progress, texts, excluded_documents=candidates)
        if not referenced:
            break
        kept.update(referenced)
        for path in referenced:
            del candidates[path]

    receipt_targets = {}
    for target, (path, entry) in receipts.items():
        if int(entry["version"][1:]) <= int(version[1:]) and (target in candidates or not target.exists()):
            sha = file_digest(path)
            if sha is None:
                continue
            candidates[path] = {"sha256": sha, "reason": "registration of an obsolete temporary output",
                                "mtime_ns": path.stat().st_mtime_ns}
            receipt_targets[path] = target
        else:
            kept[path] = "registration of a retained temporary output"
    if receipt_targets:
        referenced = deletion_references(root, receipt_targets, metadata, progress, texts, excluded_documents=candidates)
        kept.update(referenced)
        for path in referenced:
            del candidates[path]
            del receipt_targets[path]
    return candidates, kept, receipt_targets, [*draft_directories, *temp_directories]


def cleanup_preview(root, version, exported, metadata, progress, *, archive_text=None):
    candidates, kept, _, _ = cleanup_plan(root, version, Path(exported["zip"]), metadata, progress,
                                          archive_text=archive_text)
    return {"read_only": True, "after_export": True,
            "planned_deletions": [{"path": path.relative_to(root).as_posix(), "sha256": entry["sha256"], "reason": entry["reason"]}
                                  for path, entry in candidates.items()],
            "kept": [{"path": path.relative_to(root).as_posix(), "reason": reason} for path, reason in sorted(kept.items())]}


def cleanup_after_export(root, version, exported, *, at, basis):
    if exported["read_only"] or not exported["release"] or exported["version"] != version:
        raise StateError("Cleanup requires a verified formal export of this version")
    package = Path(exported["zip"]).absolute()
    reject_links(package)
    package = package.resolve()
    checksum = file_digest(package)
    if checksum is None or not is_zipfile(package):
        raise StateError(f"Verified ZIP is missing or unreadable: {package}")

    article = root / "article"
    metadata_path, progress_path = article / "metadata.json", article / "progress.json"
    originals = {path: path.read_bytes() for path in (metadata_path, progress_path)}
    metadata, progress = (json.loads(originals[path]) for path in (metadata_path, progress_path))
    if (progress["is_active"] or progress["phase"] != "finalized"
            or progress["finalized_article_version"] != version or metadata["latest_article_version"] != version):
        raise StateError(f"Cleanup requires the current finalized version: {version}")
    report = inspect(root, metadata_override=metadata, progress_override=progress)
    if issues := report["errors"] + report["warnings"]:
        raise StateError("; ".join(issues))

    candidates, kept, receipt_targets, directories = cleanup_plan(root, version, package, metadata, progress)
    batch = "finalize-cleanup-" + uuid.uuid4().hex
    events = {path: {"operation_id": uuid.uuid4().hex, "batch_id": batch, "action": "delete", "status": "planned",
                     "article_version": version, "at": at, "source": path.relative_to(root).as_posix(),
                     "target": None, "sha256": entry["sha256"], "reason": basis} for path, entry in candidates.items()}
    if any(path.read_bytes() != original for path, original in originals.items()) or file_digest(package) != checksum:
        raise StateError("Article state or verified ZIP changed before cleanup")
    deleted, failed, outcomes = [], [], []
    if events:
        metadata["asset_maintenance"].extend(events.values())
        atomic_json(metadata_path, metadata)
        for path, event in events.items():
            try:
                if path in receipt_targets and receipt_targets[path].exists():
                    raise StateError("Temporary output still exists")
                checked = inside(root, root, event["source"], exists=True)
                if (checked != path or file_digest(checked) != event["sha256"]
                        or checked.stat().st_mtime_ns != candidates[path]["mtime_ns"]):
                    raise StateError("File changed before deletion")
                checked.unlink()
            except (OSError, StateError) as exc:
                failed.append({"path": event["source"], "reason": str(exc)})
                outcomes.append({**event, "status": "failed"})
            else:
                deleted.append(event["source"])
                outcomes.append({**event, "status": "completed"})
        deleted_set = set(deleted)
        progress["candidates"] = [entry for entry in progress["candidates"]
                                  if inside(root, article, entry["file"]).relative_to(root).as_posix() not in deleted_set]
        atomic_json(progress_path, progress)
        metadata["asset_maintenance"].extend(outcomes)
        atomic_json(metadata_path, metadata)

    draft_dir = inside(root, article, progress["working_file"]).parent / ".drafts"
    temp_dir = inside(root, root, ".tmp")
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        checked = inside(root, root, directory.relative_to(root).as_posix())
        if checked != directory or not (checked.is_relative_to(draft_dir) or checked.is_relative_to(temp_dir)):
            raise StateError(f"Cleanup directory changed: {directory}")
        if checked.is_dir() and not any(checked.iterdir()):
            checked.rmdir()
    report = inspect(root)
    if issues := report["errors"] + report["warnings"]:
        raise StateError("; ".join(issues))
    if file_digest(package) != checksum:
        raise StateError("Verified ZIP changed during cleanup")
    return {"deleted": deleted, "kept": [{"path": path.relative_to(root).as_posix(), "reason": reason}
                                         for path, reason in sorted(kept.items())], "failed": failed}
