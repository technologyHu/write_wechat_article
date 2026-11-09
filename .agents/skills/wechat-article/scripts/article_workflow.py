"""Article checks are read-only by default; every mutation needs an explicit command and --apply."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from article_state import (IMAGE_EXTENSIONS, StateError, assemble, checked_root, digest,
                           extract_sections, inside, inspect, latest_operations,
                           protected_files, read_json, reject_links, schema_errors,
                           text_digest)


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value):
    reject_links(path.absolute())
    temporary = path.with_name(path.name + ".write-" + uuid.uuid4().hex)
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


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
    assets = root / "article/assets"
    if assets.exists():
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
        target = inside(root, root, f".tmp/images/{batch}/{source.relative_to(root / 'article/assets').as_posix()}")
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
    owned = {}
    for event in latest_operations(metadata).values():
        if event["status"] == "completed" and event["action"] == "move":
            target = inside(root, root, event["target"])
            if target.is_relative_to(temp):
                owned[target] = event["sha256"]
    for candidate in progress["candidates"]:
        owned[inside(root, root / "article", candidate["file"])] = candidate["sha256"]
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
    working = candidate_working.read_text(encoding="utf-8")
    progress = read_json(candidate_progress)
    assert_valid(root, progress_override=progress, working_override=working)
    current_file = root / "article/progress.json"
    if current_file.exists():
        current = read_json(current_file)
        if current.get("is_active") and current.get("session_id") != progress["session_id"]:
            raise StateError("Another authoring session owns the active working files")
    if not apply:
        return {"read_only": True, "session_id": progress["session_id"], "phase": progress["phase"]}
    journal_file = root / "article/transaction.json"
    if journal_file.exists():
        raise StateError("Recover the existing work transaction first")
    transaction = uuid.uuid4().hex
    entries = []
    for name, data in [("article-working.md", working.encode("utf-8")),
                       ("progress.json", (json.dumps(progress, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))]:
        target = inside(root, root / "article", name)
        pending = inside(root, root / "article", "." + name + ".pending-" + transaction)
        with pending.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        entries.append({"target": target.relative_to(root).as_posix(), "pending": pending.relative_to(root).as_posix(),
                        "before_sha256": digest(target.read_bytes()) if target.exists() else None,
                        "after_sha256": digest(data)})
    journal = {"schema_version": 1, "transaction_id": transaction, "files": entries}
    atomic_json(journal_file, journal)
    return recover(root, apply=True)


def recover(root, *, apply=False):
    journal_file = root / "article/transaction.json"
    report = {"read_only": not apply, "work_files": [], "asset_operations": []}
    replacements, journal = [], None
    prospective = {}
    if journal_file.exists():
        journal = read_json(journal_file)
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
    expected = {"article/article-working.md", "article/progress.json"}
    entries = journal.get("files")
    if not isinstance(entries, list) or len(entries) != 2 or any(not isinstance(e, dict) for e in entries):
        return False
    if {e.get("target") for e in entries if isinstance(e.get("target"), str)} != expected:
        return False
    token = journal.get("transaction_id", "")
    if not isinstance(token, str) or len(token) != 32 or any(c not in "0123456789abcdef" for c in token):
        return False
    def is_digest(value):
        return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    return all(e.get("pending") == "article/." + Path(e["target"]).name + ".pending-" + token
               and (e.get("before_sha256") is None or is_digest(e["before_sha256"]))
               and "before_sha256" in e and is_digest(e.get("after_sha256")) for e in entries)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "sections", "assemble", "plan-cleanup", "stage-unused", "clean-temp", "save-work", "recover"])
    parser.add_argument("article_dir")
    parser.add_argument("--apply", action="store_true", help="Execute this explicitly selected mutation; not a new user approval gate")
    parser.add_argument("--working", type=Path)
    parser.add_argument("--progress", type=Path)
    args = parser.parse_args(argv)
    try:
        root = checked_root(args.article_dir)
        if args.command == "check":
            result = inspect(root)
        elif args.command in {"sections", "assemble"}:
            text = (root / "article/article-working.md").read_text(encoding="utf-8")
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
        else:
            result = recover(root, apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get("errors") else 0
    except (StateError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
