# Resources

[Back to Mervive Code](README.md)

## Version checkpoints

| Checkpoint | Source lines | Launch | Private RAM | CPU after launch | Processes |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Original editor benchmark](https://github.com/vettive8/mervive-code/tree/14454a6) | 832 | 2.8 s | 31.2 MiB | 0.03% | 1 |
| [v1 · text, PDF and folder editor](https://github.com/vettive8/mervive-code/tree/v1) | 1,626 | Unmeasured | Unmeasured | Unmeasured | Unmeasured |

Source lines include blank lines and comments in tracked Python, C, PowerShell and Windows resource scripts. The v1 total comprises 1,549 Python lines and 77 Windows launcher, build and resource lines. Source size and runtime memory are separate measurements.

## Comparing v1 and v2

When v2 is ready, run the tagged v1 and the v2 candidate on the same PC, one editor at a time. For the text workload, open the same 36 KiB Python file from the original benchmark in both builds. Follow the timing and process-counting procedure below. Record the commit, source lines, launch time, private RAM, CPU and process count for each version, then report the difference.

For the PDF workload, use the same PDF, window size and zoom in both builds. Record its page count and measure private RAM and CPU after opening, during the same scroll sequence, and after scrolling stops. Keep these results in their own table so PDF rendering costs are visible.

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
