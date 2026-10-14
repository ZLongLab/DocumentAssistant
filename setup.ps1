param([string]$Python = '', [string]$Hotkey = 'CTRL+ALT+D', [switch]$NoShortcuts)
$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$runtimeDirectory = Join-Path (Split-Path $projectDirectory -Parent) 'DocumentAssistant-local'
$cacheDirectory = Join-Path $runtimeDirectory 'cache'
$temporaryDirectory = Join-Path $runtimeDirectory 'tmp'
New-Item -ItemType Directory -Path $cacheDirectory,$temporaryDirectory -Force | Out-Null
$env:PIP_CACHE_DIR = $cacheDirectory
$env:TEMP = $temporaryDirectory
$env:TMP = $temporaryDirectory
$env:PYTHONUTF8 = '1'
if (-not $Python) {
    $existingPython = Join-Path $projectDirectory '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $existingPython) { $Python = $existingPython }
    else {
        $pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($pythonLauncher) {
            try {
                $found = & $pythonLauncher.Source -3 -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0) { $Python = [string]$found }
            }
            catch { $Python = '' }
        }
        if (-not $Python) {
            $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
            if ($pythonCommand) { $Python = $pythonCommand.Source }
        }
    }
}
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) { throw '未找到 Python。请安装 Python 3.11+，或使用 -Python 指定解释器完整路径。' }
& $Python -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ required'"
if ($LASTEXITCODE -ne 0) { throw 'Python 版本检查失败。' }
$environmentDirectory = Join-Path $projectDirectory '.venv'
if (-not (Test-Path -LiteralPath $environmentDirectory)) {
    & $Python -m venv $environmentDirectory
    if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败。' }
}
$pythonExecutable = Join-Path $environmentDirectory 'Scripts\python.exe'
$requirements = Join-Path $projectDirectory 'requirements-lock.txt'
if (-not (Test-Path -LiteralPath $requirements)) { $requirements = Join-Path $projectDirectory 'requirements.txt' }
& $pythonExecutable -m pip install --cache-dir $cacheDirectory -r $requirements
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败。' }
if (-not $NoShortcuts) { & (Join-Path $projectDirectory 'install-shortcuts.ps1') -Hotkey $Hotkey }
Write-Host '安装完成，双击 Start-DocumentAssistant.cmd 启动。'
if (-not $NoShortcuts) { Write-Host "桌面与开始菜单快捷方式已创建，启动热键：$Hotkey" }
