# Mervive Code

Mervive Code is a lightweight Windows editor for context engineering with Codex or Claude Desktop. Open a project folder, edit Markdown outlines and TXT transcripts, read PDF references, and keep source code beside them. Your AI app and VS Code can work with the same files on disk.

For example, keep a lesson outline, transcript and PDF worksheet together. Arrange them in reading order, ask your AI app to update the outline, then press **F5** to read the changes. The PDF reader loads nearby pages as you scroll.

**Drag to move · Ctrl + drop to copy.** Drag a file or folder onto the middle of a destination folder in Mervive, either from its own Explorer or from Windows File Explorer. Drop on the project heading to move an item back to the root. Hold **Ctrl while dropping** to keep the original. Dropping onto a file uses its containing folder. Existing names are skipped.

[Resources · v1 source lines, RAM, CPU and editor benchmarks](RESOURCES.md)

## Try it on Windows

With 64-bit Python 3.12 and Tkinter installed, run these commands in PowerShell:

```powershell
git clone https://github.com/vettive8/mervive-code.git
cd mervive-code
python -m pip install Pillow Pygments pypdfium2 tkinterdnd2 "Send2Trash[nativeLib]"
python viewer.pyw .
```

The final dot opens this repository. Replace it with a quoted path to open another project or an individual file.

## A typical edit with your AI app

1. Open the same project folder you use in VS Code (or the agent’s worktree) in Mervive. Give Codex or Claude Code access to that folder and ask for a small change.
2. Press **F5** anywhere in Mervive to refresh the folder tree and reload the open file from disk. Expanded folders stay open. If you have unsaved edits, F5 refreshes the tree and keeps your draft. A brief status message confirms the refresh. Launch Mervive without a file or folder argument to reopen the last folder you closed.
3. Use **Ctrl+F** to find the relevant code, make your edit, and save with **Ctrl+S**. **Ctrl+Z** undoes an edit. **Ctrl+Y** or **Ctrl+Shift+Z** redoes it.
4. Ask the agent to review the saved change or run the project's tests. If another app writes to the file while you have unsaved edits, Mervive warns you before overwriting it.

Scroll continuously through PDFs in the editor. The scrollbar spans the whole document, and Mervive renders pages near your reading position. TXT and Markdown open in the text editor.

Mervive opens text files up to 1 MiB for editing when their encoding and line endings support a safe round trip. Larger files open as previews. The folder tree expands in place, so you can inspect a nested file and keep the rest of the project in view.

Click an Explorer row and press **Delete** to move the selected file or folder to the Windows Recycle Bin. Right-click a row to open or expand it, copy its path, or delete it.

## Explorer views

Choose **Order** or **Alphabetical** from the Explorer's **…** menu. In Order, drop at the upper or lower edge of a sibling row to reorder at the blue line. The middle of a folder row accepts a move into that folder in either view. Files and folders can be mixed. Newly discovered entries appear at the end.

The project keeps its view and sequences in `.mervive-order.json`. Each key in `folders` is a relative directory path (`.` for the project root). Its value lists the child names in reading order. An agent can edit this file and you can press **F5** to apply the changes. Switching to Alphabetical preserves your saved order.

## Optional Windows launcher

To show **Mervive Code** in Task Manager, install Visual Studio C++ Build Tools with the x64 toolchain and Windows SDK, then run the following from the repository folder:

```powershell
.\windows\build.ps1
& ".\Mervive Code.exe" .
```

Build the launcher on the computer where you will use it. It loads that computer's Python installation and the adjacent `viewer.pyw`.
