# Mervive Code

Mervive Code is a lightweight Windows editor for people who write code with the Codex desktop app or Claude Code in Claude Desktop. Keep the conversation in your AI app. Open the same project folder in Mervive to read the implementation, find a line, or make an edit yourself.

## Windows editor benchmark

| Editor | Launch to filename in title | Private RAM | CPU after launch | Processes |
| --- | ---: | ---: | ---: | ---: |
| Mervive Code | 2.8 s | 31.2 MiB | 0.03% | 1 |
| VS Code 1.141.0 | 7.7 s | 940.4 MiB | 22.73% | 11–18 |
| Antigravity IDE 2.8.0 | 13.5 s | 852.6 MiB | 6.83% | 9 |

**How we measured.** Each editor opened the same 36 KiB Python file on a Windows 10 laptop with an Intel Core i7-7700HQ (8 logical processors) and 7.9 GiB of usable RAM. We ran one editor under test at a time, twice per editor, reversing the order for the second round. The table shows the two-run means and the observed process counts.

Launch time ends when the window title first contains the filename. After an eight-second settling period, we sampled the editor and its child processes over a ten-second idle interval. RAM is the average private working set at the two endpoints. CPU is the share of total machine capacity used by processes present at both endpoints.

VS Code and Antigravity used separate benchmark profiles with user extensions disabled. Each reused its profile on the second launch. An existing Antigravity session stayed open throughout. Each measurement counts only the editor process tree launched for that test. Running a separate AI desktop app adds its own resource usage. Startup activity can continue during the idle interval, and results vary with project size and extensions.

<details>
<summary>Individual runs</summary>

| Run | Editor | Launch | Private RAM | CPU after launch |
| ---: | --- | ---: | ---: | ---: |
| 1 | Mervive Code | 3.6 s | 31.4 MiB | 0.05% |
| 1 | VS Code | 11.2 s | 976.0 MiB | 20.93% |
| 1 | Antigravity IDE | 19.0 s | 770.9 MiB | 4.46% |
| 2 | Antigravity IDE | 8.0 s | 934.4 MiB | 9.20% |
| 2 | VS Code | 4.3 s | 904.8 MiB | 24.53% |
| 2 | Mervive Code | 1.9 s | 31.1 MiB | 0.00% |

</details>

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

1. Open the same project folder you use in VS Code (or the agent’s worktree) in Mervive. Give Codex or Claude Code access to that folder and ask for a small change.
2. Press **F5** anywhere in Mervive to refresh the folder tree and reload the open file from disk. Expanded folders stay open. If you have unsaved edits, F5 refreshes the tree and keeps your draft. A brief status message confirms the refresh. Launch Mervive without a file or folder argument to reopen the last folder you closed.
3. Use **Ctrl+F** to find the relevant code, make your edit, and save with **Ctrl+S**. **Ctrl+Z** undoes an edit. **Ctrl+Y** or **Ctrl+Shift+Z** redoes it.
4. Ask the agent to review the saved change or run the project's tests. If another app writes to the file while you have unsaved edits, Mervive warns you before overwriting it.

Mervive opens text files up to 1 MiB for editing when their encoding and line endings support a safe round trip. Larger files open as previews. The folder tree expands in place, so you can inspect a nested file and keep the rest of the project in view.

## Optional Windows launcher

To show **Mervive Code** in Task Manager, install Visual Studio C++ Build Tools with the x64 toolchain and Windows SDK, then run the following from the repository folder:

```powershell
.\windows\build.ps1
& ".\Mervive Code.exe" .
```

Build the launcher on the computer where you will use it. It loads that computer's Python installation and the adjacent `viewer.pyw`.
