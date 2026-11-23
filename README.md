# Mervive Code

Mervive Code is a lightweight Windows editor for people who write code with the Codex desktop app or Claude Code in Claude Desktop. Keep the conversation in your AI app. Open the same project folder in Mervive to read the implementation, find a line, or make an edit yourself.

**Already use VS Code?** Choose **File → Open Folder** in either editor and select the same directory. Both edit ordinary files on disk. You can move between them without importing or converting the project. If your agent works in a separate Git worktree, open that worktree's folder to see its changes.

## Try it on Windows

With 64-bit Python 3.12 and Tkinter installed, run these commands in PowerShell:

```powershell
git clone https://github.com/vettive8/mervive-code.git
cd mervive-code
python -m pip install Pillow Pygments
python viewer.pyw .
```

The final dot opens this repository. Replace it with a quoted path to open another project or an individual file.

## A typical edit with your AI app

1. Give Codex or Claude Code access to the local project folder and ask for a small change.
2. Open the file it changed in Mervive. If the file was already on screen, close its tab and reopen it to read the latest saved version. Use **Refresh Explorer** in the Explorer menu to see newly created files.
3. Use **Ctrl+F** to find the relevant code, make your edit, and save with **Ctrl+S**. **Ctrl+Z** undoes an edit. **Ctrl+Y** or **Ctrl+Shift+Z** redoes it.
4. Ask the agent to review the saved change or run the project's tests. If another app writes to the file while you have unsaved edits, Mervive warns you before overwriting it.

Mervive opens text files up to 1 MiB for editing when their encoding and line endings support a safe round trip. Larger files open as previews. The folder tree expands in place, so you can inspect a nested file and keep the rest of the project in view.

## Mervive Code, VS Code, or Antigravity?

| While working with a desktop coding agent | Mervive Code | VS Code | Antigravity IDE |
| --- | --- | --- | --- |
| Open an existing project and edit its files | Folder tree, syntax highlighting, find, save, undo and redo | Folder workspaces and a full code editor | Project explorer and a full code editor |
| Decide where to work with the AI | Keep the conversation in Codex or Claude Desktop | Use the separate desktop app or an editor chat integration | Use the separate desktop app or Antigravity's integrated agent |
| Run a command or test | Ask the desktop agent or use a separate terminal | Use the integrated terminal or the desktop agent | Use the integrated terminal or ask the agent |
| Best fit | You already have an AI app and want a small window for the code | You want breakpoints, extensions, or terminal tools alongside the code | You want the agent to work across the editor, terminal, and browser |

In one Windows session with the same Python file open, Mervive used **30.1 MiB of private resident RAM in one process**. Antigravity and its helpers used **994 MiB across 23 processes**. These are snapshots of those editor sessions. A separately running Codex or Claude desktop app has its own memory usage. VS Code was outside that measurement.

Read more about the other workflows in the [VS Code editor guide](https://code.visualstudio.com/docs/editing/getting-started/tips-and-tricks), [Antigravity IDE overview](https://www.antigravity.google/product/antigravity-ide), and [Claude Code desktop guide](https://code.claude.com/docs/en/desktop).

## Optional Windows launcher

To show **Mervive Code** in Task Manager, install Visual Studio C++ Build Tools with the x64 toolchain and Windows SDK, then run the following from the repository folder:

```powershell
.\windows\build.ps1
& ".\Mervive Code.exe" .
```

Build the launcher on the computer where you will use it. It loads that computer's Python installation and the adjacent `viewer.pyw`.
