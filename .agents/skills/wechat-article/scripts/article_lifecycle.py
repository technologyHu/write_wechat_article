"""Review externally edited chapters and archive an authorized manuscript version."""
from __future__ import annotations

import json
import uuid
from copy import deepcopy
from difflib import unified_diff

from article_cleanup import cleanup_after_export, cleanup_preview
from article_export import export_article, export_selection
from article_revision import commit_revision_files, json_bytes
from article_state import (VERSION, StateError, assemble, confirmation_drift, digest,
                           extract_sections, inside, inspect, pending_errors, proof, read_json,
                           reject_links, text_digest)


def read_work(root):
    article = root / "article"
    metadata_path = inside(article, article, "metadata.json", exists=True)
    progress_path = inside(article, article, "progress.json", exists=True)
    original = {path: path.read_bytes() for path in (metadata_path, progress_path)}
    meta, progress = (json.loads(original[path]) for path in (metadata_path, progress_path))
    if meta.get("schema_version") != 3 or progress.get("schema_version") != 3 or not progress["is_active"]:
        raise StateError("This operation requires an active manuscript under contract 3.")
    working = inside(article, article, progress["working_file"], exists=True)
    original[working] = working.read_bytes()
    return working, original, meta, progress


def validate_candidate(root, **overrides):
    report = inspect(root, **overrides)
    if issues := report["errors"] + report["warnings"]:
        raise StateError("; ".join(issues))


def confirmed_text(root, working, meta, section, expected):
    name = section["section_id"]
    if inherited := section.get("inheritance"):
        record = meta["articles"].get(inherited["article_version"], {})
        if file := record.get("file"):
            path = inside(root, root / "article", file, exists=True)
            lines = path.read_text(encoding="utf-8").splitlines()
            text = "\n".join(lines[inherited["start_line"] - 1:inherited["end_line"]])
            if text_digest(text) == expected:
                return text
    drafts = inside(root, working.parent, ".drafts")
    for path in sorted(drafts.glob("*.json"), reverse=True):
        reject_links(path)
        try:
            snapshot = read_json(path)
        except StateError:
            continue
        if snapshot.get("working_file") != working.relative_to(root / "article").as_posix():
            continue
        for item in snapshot.get("sections", [snapshot]):
            if item.get("section_id") == name and isinstance(item.get("text"), str) and text_digest(item["text"]) == expected:
                return item["text"]
    return None


def confirmation_details(root, working, meta, section, current, change):
    detail = {**change, "current_text": current}
    expected = change.get("confirmed_sha256")
    previous = confirmed_text(root, working, meta, section, expected) if expected else None
    detail["baseline_available"] = previous is not None
    if previous is not None:
        detail["diff"] = "\n".join(unified_diff(previous.splitlines(), current.splitlines(),
                                               fromfile="confirmed", tofile="current", lineterm=""))
    return detail


def reconcile(root, *, section_id=None, expected_sha256=None, basis=None, at, apply=False):
    working, original, meta, progress = read_work(root)
    raw = original[working].decode("utf-8")
    _, units = extract_sections(raw)
    by_id = {section["section_id"]: section for section in progress["sections"]}
    changed = confirmation_drift(units, progress["sections"])
    selected = [item for item in changed if section_id is None or item["section_id"] == section_id]
    if section_id is not None and section_id not in by_id:
        raise StateError(f"Unknown section: {section_id}")
    selected = [confirmation_details(root, working, meta, by_id[item["section_id"]], units[item["section_id"]], item)
                for item in selected]
    result = {"read_only": not apply, "file": str(working), "changed_sections": selected}
    if not apply:
        return result
    if not section_id or not expected_sha256 or not basis or not basis.strip():
        raise StateError("Apply reconciliation with --section, the reviewed --expect-sha256 and the user's reply in --basis.")
    if len(selected) != 1 or selected[0]["current_sha256"] != expected_sha256:
        raise StateError("Current text differs from the reviewed section; preview it again.")
    section = by_id[section_id]
    prior = deepcopy(section)
    section["draft_ref"] += "（采用手动修订）"
    approve_section(section, progress, expected_sha256, basis, at)
    remaining = {item["section_id"]: item["current_sha256"] for item in changed if item["section_id"] != section_id}
    validate_candidate(root, progress_override=progress, working_override=raw, reviewable_drift=remaining)
    article = root / "article"
    token = uuid.uuid4().hex
    snapshot = inside(root, working.parent, f".drafts/revision-{token}.json")
    changes = {**original, article / "progress.json": json_bytes(progress), snapshot: json_bytes({
        "at": at, "basis": basis, "working_file": progress["working_file"],
        "sections": [{"section_id": section_id, "text": units[section_id], "section_record": prior}],
    })}
    commit_revision_files(root, changes, original, {}, token, reviewable_drift=remaining)
    return {**result, "snapshot": str(snapshot), "remaining_sections": sorted(remaining)}


def approve_section(section, progress, checksum, basis, at):
    name = section["section_id"]
    section.update(status="confirmed", inheritance=None, media_updates=[], confirmation={
        "draft_ref": section["draft_ref"], "confirmed_at": at, "user_message": basis,
        "outline_version_at_confirmation": progress["outline_version"], "content_sha256": checksum,
        "media": [proof(item) for item in progress["media"] if item["status"] == "approved" and name in item["section_ids"]],
    })
    for field in ("outline_revalidation", "reopened_at", "reopened_snapshot_sha256"):
        section.pop(field, None)


def archive_article(root, version, *, at, basis=None, apply=False, finalize=False, output_dir=None,
                    show_cleanup=False):
    if not VERSION.fullmatch(version) or version != f"v{int(version[1:]):03d}" or int(version[1:]) < 1:
        raise StateError("Use a specific article version such as v001.")
    working, original, meta, progress = read_work(root)
    article = root / "article"
    raw = original[working].decode("utf-8")
    if working.parent not in {article, article / version}:
        raise StateError(f"Active draft is in {working.parent.name}, not {version}.")
    if latest := meta["latest_article_version"]:
        if int(version[1:]) <= int(latest[1:]):
            raise StateError(f"Archive version must be later than {latest}.")
    path = inside(article, working.parent, f"article-{version}.md")
    if path.exists() or version in meta["articles"]:
        raise StateError(f"Archive version already exists: {version}")
    title, units = extract_sections(raw)
    drift = confirmation_drift(units, progress["sections"])
    previous_sections, review_sections = [], []
    if finalize:
        changed = {entry["section_id"]: entry for entry in drift}
        for section in progress["sections"]:
            name = section["section_id"]
            if name in changed or section["status"] == "awaiting_confirmation":
                if not apply:
                    change = changed.get(name, {"section_id": name, "current_sha256": text_digest(units[name])})
                    review_sections.append(confirmation_details(root, working, meta, section, units[name], change))
                previous_sections.append({"section_id": name, "text": units[name], "section_record": deepcopy(section)})
                section["draft_ref"] += "（确认完稿）"
                approve_section(section, progress, text_digest(units[name]), basis, at)
        drift = confirmation_drift(units, progress["sections"])
    waiting = [item["section_id"] for item in progress["sections"] if item["status"] not in {"confirmed", "inherited"}]
    issues = pending_errors(progress, final=finalize)
    if waiting:
        issues.append("Awaiting confirmation: " + ", ".join(waiting))
    if drift:
        issues.append("Changed after confirmation; use reconcile: " + ", ".join(item["section_id"] for item in drift))
    if issues:
        raise StateError("; ".join(issues))
    validate_candidate(root, metadata_override=meta, progress_override=progress, working_override=raw)
    body, spans = assemble(raw)
    content = body.encode("utf-8")
    record = {"record_schema_version": 3, "file": path.relative_to(article).as_posix(),
              "outline_version": progress["outline_version"], "title": title,
              "based_on": progress["based_on_article_version"], "created_at": at,
              "change_summary": basis or "按已记录的章节确认归档正文。", "content_sha256": digest(content),
              "chapter_confirmations": [{**item, "span": spans[item["section_id"]]} for item in progress["sections"]],
              "sources": progress["sources"], "media": progress["media"], "pending_media": progress["pending_media"]}
    meta["articles"][version] = record
    meta["latest_article_version"] = version
    progress.update(phase="archived", is_active=False, archived_article_version=version,
                    finalized_article_version=None, completion_basis=None)
    if finalize:
        progress.update(phase="finalized", finalized_article_version=version,
                        completion_basis={"kind": "user", "message": basis, "at": at})
    validate_candidate(root, metadata_override=meta, progress_override=progress, working_override=raw,
                       archive_overrides={path: content})
    result = {"read_only": not apply, "version": version, "outline_version": record["outline_version"],
              "body": str(path), "sections": list(spans), "pending_media": record["pending_media"]}
    if finalize:
        result.update(phase="finalized", confirmed_sections=[entry["section_id"] for entry in previous_sections],
                      export=export_selection(root, version, (path, content, "archived", record, {}),
                                              output_dir=output_dir, release=True))
        if not apply:
            result.update(review_sections=review_sections, content_sha256=record["content_sha256"])
        if show_cleanup:
            result["cleanup"] = cleanup_preview(root, version, result["export"], meta, progress, archive_text=body)
            if previous_sections:
                result["cleanup"]["includes_snapshot_created_during_finalization"] = True
    if apply:
        changes = {**original, path: content, article / "metadata.json": json_bytes(meta),
                   article / "progress.json": json_bytes(progress)}
        token = uuid.uuid4().hex
        if previous_sections:
            snapshot = inside(root, working.parent, f".drafts/revision-{token}.json")
            changes[snapshot] = json_bytes({"at": at, "basis": basis, "working_file": progress["working_file"],
                                            "sections": previous_sections})
        commit_revision_files(root, changes, original, {}, token, archive=path)
    return result


def finalize_article(root, version, *, at, basis, output_dir=None, apply=False, cleanup=False):
    if not basis or not basis.strip():
        raise StateError("finalize needs the user's approval of the current version in --basis")
    article = root / "article"
    metadata_path, progress_path = article / "metadata.json", article / "progress.json"
    metadata = read_json(metadata_path)
    if version not in metadata["articles"]:
        result = archive_article(root, version, at=at, basis=basis, apply=apply, finalize=True, output_dir=output_dir,
                                 show_cleanup=cleanup and not apply)
    else:
        original = {path: path.read_bytes() for path in (metadata_path, progress_path)}
        progress = json.loads(original[progress_path])
        if (progress["is_active"] or progress["phase"] not in {"archived", "finalized"}
                or progress["archived_article_version"] != version or metadata["latest_article_version"] != version):
            raise StateError(f"Can only finalize the current archived version: {version}")
        validate_candidate(root)
        export = export_article(root, version, output_dir=output_dir, release=True)
        result = {"read_only": not apply, "version": version, "phase": "finalized", "confirmed_sections": [],
                  "body": str(article / export["body"]), "export": export}
        if cleanup and not apply:
            result["cleanup"] = cleanup_preview(root, version, export, metadata, progress)
        if apply and progress["phase"] == "archived":
            working = inside(root, article, progress["working_file"], exists=True)
            original[working] = working.read_bytes()
            progress.update(phase="finalized", finalized_article_version=version,
                            completion_basis={"kind": "user", "message": basis, "at": at})
            validate_candidate(root, progress_override=progress)
            changes = {**original, progress_path: json_bytes(progress)}
            commit_revision_files(root, changes, original, {}, uuid.uuid4().hex)
    if apply:
        try:
            result["export"] = export_article(root, version, output_dir=output_dir, apply=True, release=True)
        except (StateError, OSError) as exc:
            raise StateError(f"Version {version} is finalized. Retry finalize to publish the ZIP: {exc}") from exc
    if cleanup and apply:
        try:
            result["cleanup"] = cleanup_after_export(root, version, result["export"], at=at, basis=basis)
        except (StateError, OSError) as exc:
            raise StateError(f"Version {version} was exported, but cleanup stopped: {exc}") from exc
        if failed := result["cleanup"]["failed"]:
            result["errors"] = [f"Cleanup failed for {entry['path']}: {entry['reason']}" for entry in failed]
    return result
