param(
    [string]$Project = (Split-Path $PSScriptRoot)
)
$ErrorActionPreference='Stop'
$dir = Join-Path $env:TEMP ("mervive-benchmark-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $dir | Out-Null
Write-Output "Benchmark files and results: $dir"
$sample=Join-Path $dir 'editor-bench.py'
# Rebuild the historical CRLF fixture from its Git blob.
$oldEncoding = [Console]::OutputEncoding
try {
    [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
    $lines = git -C $PSScriptRoot show 14454a6:viewer.pyw
} finally { [Console]::OutputEncoding = $oldEncoding }
if ($LASTEXITCODE) { throw "The original benchmark revision is required" }
[IO.File]::WriteAllText($sample, (($lines -join "`r`n") + "`r`n"), [Text.UTF8Encoding]::new($false))
if ((Get-FileHash $sample).Hash -ne '9034E96AAA4EB2E333993C61E0E696D628670BB127D856E1C1C282D11E5EACFA') {
    throw "Benchmark file does not match the original"
}
$exe = Join-Path $Project 'Mervive Code.exe'
function Get-EditorSnapshot($rootId) {
    $all = Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId
    $ids = @($rootId)
    do {
        $next = @($all | Where-Object { $_.ParentProcessId -in $ids -and $_.ProcessId -notin $ids } |
            ForEach-Object ProcessId)
        $ids += $next
    } while ($next.Count)
    $processes = @(Get-Process -Id $ids -ErrorAction SilentlyContinue)
    $counters = Get-CimInstance Win32_PerfFormattedData_PerfProc_Process -Property IDProcess,WorkingSetPrivate
    $resident = ($counters | Where-Object IDProcess -in $processes.Id | Measure-Object WorkingSetPrivate -Sum).Sum
    [pscustomobject]@{
        Ids = $processes.Id
        CPU = @($processes | Select-Object Id,CPU)
        RAM = $resident / 1MB
        Time = [Diagnostics.Stopwatch]::GetTimestamp()
    }
}

foreach ($round in 1,2) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $oldData = $env:LOCALAPPDATA
    try {
        $env:LOCALAPPDATA = Join-Path $dir 'MerviveProfile'
        $proc = Start-Process -FilePath $exe -ArgumentList ('"' + $sample + '"') -PassThru
    } finally {
        $env:LOCALAPPDATA = $oldData
    }
    try {
        do {
            $proc.Refresh()
            if ($proc.HasExited) { throw 'Mervive exited before opening the fixture' }
            if ($proc.MainWindowTitle -like '*editor-bench.py*') { break }
            Start-Sleep -Milliseconds 100
        } while ($timer.Elapsed.TotalSeconds -lt 100)
        if ($proc.MainWindowTitle -notlike '*editor-bench.py*') { throw 'Timed out waiting for the fixture' }

        $launch = $timer.Elapsed.TotalSeconds
        Start-Sleep -Seconds 8
        $a = Get-EditorSnapshot $proc.Id
        Start-Sleep -Seconds 10
        $b = Get-EditorSnapshot $proc.Id
        $delta = 0
        foreach ($end in $b.CPU) {
            $before = $a.CPU | Where-Object Id -eq $end.Id
            if ($before) { $delta += $end.CPU - $before.CPU }
        }
        $seconds = ($b.Time - $a.Time) / [Diagnostics.Stopwatch]::Frequency
        [pscustomobject]@{
            Editor = 'Mervive'
            Round = $round
            Launch = $launch
            RAM = ($a.RAM + $b.RAM) / 2
            CPU = 100 * $delta / ($seconds * [Environment]::ProcessorCount)
            Count = @($b.Ids).Count
            Common = @($a.Ids | Where-Object { $_ -in $b.Ids }).Count
            StartCount = @($a.Ids).Count
        } | Export-Csv "$dir/results.csv" -Append -NoTypeInformation
        Write-Output "Mervive round $round completed"
    } finally {
        if (!$proc.HasExited) {
            $null = $proc.CloseMainWindow()
            if (!$proc.WaitForExit(12000)) { throw 'Benchmark window did not exit' }
        }
    }
}
