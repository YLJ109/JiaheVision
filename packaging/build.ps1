$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
$buildPython = Join-Path $projectRoot '.buildenv/Scripts/python.exe'
$compiler = Join-Path $projectRoot '.tools/InnoSetup/ISCC.exe'
if (-not (Test-Path -LiteralPath $buildPython)) { throw '缺少独立纯 CPU 打包环境 .buildenv' }
if (-not (Test-Path -LiteralPath $compiler)) { throw '缺少项目内 Inno Setup 编译器 .tools/InnoSetup/ISCC.exe' }
$env:JIAHE_CPU_ONLY = '1'
$basePython = & $buildPython -c "import sys; print(sys.base_prefix)"
$env:PATH = @((Join-Path $projectRoot '.buildenv/Scripts'), $basePython,
    (Join-Path $env:SystemRoot 'System32'), $env:SystemRoot) -join ';'
& $buildPython packaging/prepare_cpu.py
if ($LASTEXITCODE -ne 0) { throw 'CPU environment preparation failed' }
& $buildPython -m PyInstaller --noconfirm --clean packaging/jiahe.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
$forbidden = Get-ChildItem -LiteralPath 'dist/JiaheVision' -Recurse -File | Where-Object { $_.Name -match '(?i)(cudnn|cublas|cudart|torch|tensorflow)' }
if ($forbidden) { throw ('Unexpected GPU/heavy dependency: ' + ($forbidden.Name -join ', ')) }
& $compiler packaging/installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
Get-Item -LiteralPath 'output/家和视觉-Setup.exe' | Select-Object FullName, Length
