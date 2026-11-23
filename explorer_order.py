"""Portable Explorer ordering. Folder keys and entry names are relative to the project."""
import json
import os
from pathlib import Path
import tempfile

FILENAME = ".mervive-order.json"


def read_order(root):
    try:
        data = json.loads((root / FILENAME).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {"view": "Alphabetical", "folders": {}}
    if not isinstance(data, dict) or data.get("view") not in ("Order", "Alphabetical"):
        raise ValueError(f"Invalid view in {FILENAME}")
    folders = data.get("folders")
    if not isinstance(folders, dict) or not all(
        isinstance(names, list) and all(isinstance(name, str) for name in names)
        for names in folders.values()
    ):
        raise ValueError(f"Invalid folder order in {FILENAME}")
    return data


def write_order(root, previous, updated):
    target = root / FILENAME
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=root, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(updated, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        if read_order(root) != previous:
            raise ValueError("Order changed on disk. Press F5 before rearranging again.")
        os.replace(temporary, target)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
