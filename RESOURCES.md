# Resources

[Back to Mervive Code](README.md)

## Mervive milestones

Two fresh Mervive launches per checkpoint on the same laptop. Each opened the original 36,918-byte Python fixture. RAM is private working set. CPU is a percentage of the whole machine during the post-launch idle interval. The original editor comparisons below serve as fixed reference measurements.

| Version | App source lines | Launch | Private RAM | CPU after launch | Processes |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Original editor](https://github.com/vettive8/mervive-code/tree/14454a6) | 832 | 2.8 s | 31.2 MiB | 0.03% | 1 |
| [v1 · text and PDF editor](https://github.com/vettive8/mervive-code/tree/v1) | 1,626 | 2.19 s | 34.1 MiB | 0.04% | 1 |
| [Internal folder moves](https://github.com/vettive8/mervive-code/tree/16e1ae6a875935b087969eecc86979d145c9eb94) | 1,702 | 2.42 s | 34.2 MiB | 0.02% | 1 |

App source lines include comments and blank lines in shipped Python, Windows launcher, resource and build files. The benchmark tools are counted separately. Small differences between two-run means can reflect background activity. An existing Mervive window remained open outside the measured process trees.

## PDF reading

Each build opened the same generated 24-page text PDF twice, in separate Python processes running the real Mervive reader. Each used Reading size and a 618 × 530 pixel PDF viewport. After eight seconds to settle, the driver recorded ten seconds idle, ten seconds scrolling and ten seconds idle again. Each scroll run sent 100 wheel events and reached page 7.

| Reader state | v1 RAM | v1 CPU | Internal moves RAM | Internal moves CPU |
| --- | ---: | ---: | ---: | ---: |
| Open and idle | 42.3 MiB | 0.13% | 41.7 MiB | 0.13% |
| Scrolling | 46.8 MiB | 1.54% | 46.5 MiB | 1.59% |
| After scrolling | 44.9 MiB | 0.14% | 44.9 MiB | 0.10% |

PDF RAM is the mean of one private resident-page sample per second, averaged across the two runs. CPU includes the in-process test driver and rendering. Image-heavy or scanned PDFs can use more memory. Tagged v1 logged a Windows title-bar paint callback warning during setup. Both scrolling runs completed. The internal-moves build corrects the handle type.

## Repeat at the next milestone

Run feature tests for routine changes. Repeat the Mervive benchmarks when shipped source roughly doubles from a milestone, or when a performance check is requested. After the roughly 1,600-line milestone, the next checkpoint is about 3,200 lines. Use the recorded VS Code and Antigravity runs for comparison.

Build the Windows launcher and run these commands at the repository root. Run one editor under test at a time. The text script runs Mervive twice and prints its results directory. Each PDF invocation runs once and prints JSON. Record the application commit, line count and both sets of results.

```powershell
.\benchmarks\text.ps1
python benchmarks/pdf.py
python benchmarks/pdf.py
```

[Recorded runs](benchmarks/milestones.json) · [Text workload](benchmarks/text.ps1) · [PDF workload](benchmarks/pdf.py)

## Original Windows editor comparison

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
