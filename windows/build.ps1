$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot)
try {
    $build = New-Item -ItemType Directory -Force (Join-Path $env:TEMP 'mervive-code-launcher')
    python -c 'import sys,json,pathlib; p=pathlib.Path(sys.base_prefix); dll=p/("python%d%d.dll"%sys.version_info[:2]); assert dll.exists(); print("#define PYTHON_DLL L"+json.dumps(str(dll))); print("#define PYTHON_EXE L"+json.dumps(str(p/"pythonw.exe")))' | Set-Content "$build/runtime.h" -Encoding ascii
    if ($LASTEXITCODE) { throw 'Python runtime detection failed' }
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    $vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (!$vs) { throw 'Visual Studio C++ Build Tools are required' }
    $batch = @(
        "@call `"$vs\VC\Auxiliary\Build\vcvars64.bat`" >nul || exit /b 1"
        "rc /nologo /fo `"$build/app.res`" windows/app.rc || exit /b 1"
        "cl /nologo /O1 /utf-8 /I`"$build`" windows/main.c `"$build/app.res`" /Fo`"$build/main.obj`" /Fe`"Mervive Code.exe`" /link /subsystem:windows shell32.lib user32.lib"
    )
    $batch | Set-Content "$build/build.cmd" -Encoding ascii
    & "$build/build.cmd"
    if ($LASTEXITCODE) { throw 'Launcher build failed' }
} finally { Pop-Location }
