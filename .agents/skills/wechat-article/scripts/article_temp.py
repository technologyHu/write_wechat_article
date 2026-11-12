"""Record the ownership and fingerprint of temporary article outputs."""
from __future__ import annotations

import re
from pathlib import Path

from article_revision import atomic_json, file_digest
from article_state import VERSION, StateError, digest, inside, read_json, reject_links


def temporary_version(root):
    article = root / "article"
    progress_file = article / "progress.json"
    if progress_file.is_file():
        progress = read_json(progress_file)
        if progress.get("is_active"):
            directory = Path(progress["working_file"]).parent.name
            return directory if VERSION.fullmatch(directory) else progress["outline_version"]
    metadata = article / "metadata.json"
    return (read_json(metadata).get("latest_outline_version") if metadata.is_file() else None) or "v001"


def receipt_name(relative):
    return digest(relative.encode("utf-8")) + ".json"


def valid_version(version):
    return (isinstance(version, str) and VERSION.fullmatch(version)
            and int(version[1:]) > 0 and version == f"v{int(version[1:]):03d}")


def register_temporary(root, paths, *, origin, version=None, apply=False):
    version = version or temporary_version(root)
    if not valid_version(version) or not origin.strip():
        raise StateError("Temporary registration needs a version such as v001 and an origin")
    temp = inside(root, root, ".tmp")
    inventory = inside(root, temp, ".inventory")
    records = {}
    for supplied in paths:
        supplied = supplied.absolute()
        reject_links(supplied)
        path = supplied.resolve()
        if not path.is_file() or not path.is_relative_to(temp) or path.is_relative_to(inventory):
            raise StateError(f"Expected an existing temporary output inside {temp}: {path}")
        name = path.relative_to(root).as_posix()
        before = path.stat()
        checksum = file_digest(path)
        after = path.stat()
        if checksum is None or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise StateError(f"Temporary output changed while being registered: {path}")
        records[name] = {"file": name, "version": version, "origin": origin, "sha256": checksum,
                         "mtime_ns": after.st_mtime_ns}
    if apply:
        inventory.mkdir(exist_ok=True)
        for name, record in records.items():
            atomic_json(inside(root, inventory, receipt_name(name)), record)
    return {"read_only": not apply, "files": list(records.values())}


def record_generated(paths, origin, *, version=None):
    """Register tool outputs only when they are placed in a topic's .tmp."""
    paths = [path.absolute() for path in paths]
    temp = next((parent for parent in paths[0].parents
                 if parent.name == ".tmp" and (parent.parent / "article").is_dir()), None)
    if temp is not None:
        register_temporary(temp.parent.resolve(), paths, origin=origin, version=version, apply=True)


def temporary_receipts(root):
    temp = inside(root, root, ".tmp")
    inventory = inside(root, temp, ".inventory")
    records = {}
    for receipt in sorted(inventory.glob("*.json")):
        if not re.fullmatch(r"[0-9a-f]{64}\.json", receipt.name):
            continue
        reject_links(receipt)
        entry = read_json(receipt)
        if (set(entry) != {"file", "version", "origin", "sha256", "mtime_ns"}
                or not valid_version(entry["version"]) or not entry["origin"].strip()
                or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) or type(entry["mtime_ns"]) is not int):
            raise StateError(f"Invalid temporary registration: {receipt}")
        target = inside(root, root, entry["file"])
        if (not target.is_relative_to(temp) or target.is_relative_to(inventory)
                or receipt.name != receipt_name(target.relative_to(root).as_posix())):
            raise StateError(f"Temporary registration points outside its scope: {receipt}")
        records[target] = (receipt, entry)
    return records
