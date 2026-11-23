"""Copy local Windows Explorer drops into a project without replacing existing items."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import shutil


def check_directory_links(directory, names):
    for name in names:
        path = Path(directory, name)
        if path.is_symlink() or os.path.isjunction(path):
            raise ValueError(f"Linked item inside folder: {path.name}")
    return ()


def copy_dropped_items(project, folder, sources):
    copied, skipped = [], []
    for source in sources:
        try:
            if not folder.resolve(strict=True).is_relative_to(project.resolve(strict=True)):
                raise ValueError("Destination is outside the project")
            if not source.is_absolute() or not source.name or source.is_symlink() or os.path.isjunction(source):
                raise ValueError("Choose a regular file or folder")
            target = folder / source.name
            if os.path.lexists(target):
                raise ValueError("An item with this name already exists")
            if source.is_dir() and folder.resolve().is_relative_to(source.resolve()):
                raise ValueError("A folder cannot be copied inside itself")
            with TemporaryDirectory(prefix=".mervive-copy-", dir=folder) as temporary:
                staged = Path(temporary) / source.name
                if source.is_dir():
                    shutil.copytree(source, staged, ignore=check_directory_links, symlinks=True)
                else:
                    shutil.copy2(source, staged)
                # Windows rename fails if another process created the target during the copy.
                staged.rename(target)
            copied.append(target)
        except (OSError, ValueError, RuntimeError) as exc:
            skipped.append(f"{source.name}: {exc}")
    return copied, skipped
