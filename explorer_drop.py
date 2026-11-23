"""Transfer local Windows Explorer drops into a project without replacing existing items."""
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


def move_item(source, target):
    try:
        source.rename(target)
        return
    except OSError as exc:
        if getattr(exc, "winerror", None) != 17:  # ERROR_NOT_SAME_DEVICE
            raise

    # Let the Windows shell handle cross-volume moves, including folder metadata
    # and recovery from partial transfers. Leave collision confirmation enabled.
    import pythoncom
    from win32com.shell import shell, shellcon
    pythoncom.CoInitialize()
    try:
        operation = pythoncom.CoCreateInstance(shell.CLSID_FileOperation, None,
            pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IFileOperation)
        operation.SetOperationFlags(shellcon.FOFX_EARLYFAILURE | shellcon.FOF_NOERRORUI)
        item = shell.SHCreateItemFromParsingName(str(source), None, shell.IID_IShellItem)
        parent = shell.SHCreateItemFromParsingName(str(target.parent), None, shell.IID_IShellItem)
        operation.MoveItem(item, parent, target.name, None)
        operation.PerformOperations()
        if operation.GetAnyOperationsAborted() or os.path.lexists(source):
            raise OSError("Windows did not finish moving this item")
    except pythoncom.com_error as exc:
        raise OSError(str(exc)) from exc
    finally:
        pythoncom.CoUninitialize()


def transfer_dropped_items(project, folder, sources, action):
    transferred, skipped = [], []
    if action not in ("copy", "move"):
        raise ValueError("Unknown drop action")
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
                raise ValueError("A folder cannot be dropped inside itself")
            if action == "move":
                move_item(source, target)
                transferred.append((source, target))
                continue
            with TemporaryDirectory(prefix=".mervive-copy-", dir=folder) as temporary:
                staged = Path(temporary) / source.name
                if source.is_dir():
                    shutil.copytree(source, staged, ignore=check_directory_links, symlinks=True)
                else:
                    shutil.copy2(source, staged)
                # Windows rename fails if another process created the target during the copy.
                staged.rename(target)
            transferred.append((source, target))
        except (OSError, ValueError, RuntimeError) as exc:
            skipped.append(f"{source.name}: {exc}")
    return transferred, skipped
