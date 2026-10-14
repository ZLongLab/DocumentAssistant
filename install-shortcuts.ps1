param(
    [ValidatePattern('(?i)^(CTRL\+ALT|ALT\+CTRL)\+[A-Z0-9]$')]
    [string]$Hotkey = 'CTRL+ALT+D',
    [string]$DestinationFolder = ''
)
$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$pythonExecutable = Join-Path $projectDirectory '.venv\Scripts\pythonw.exe'
$consolePython = Join-Path $projectDirectory '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    throw '请先运行 setup.ps1 安装独立环境，再配置快捷方式。'
}
$launcher = Join-Path $projectDirectory 'start.ps1'
$target = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $launcher + '" -Windowed'
$description = 'DocumentAssistant | managed local launcher'
$runtimeDirectory = Join-Path (Split-Path $projectDirectory -Parent) 'DocumentAssistant-local'
if ($env:DOCUMENTASSISTANT_HOME) { $runtimeDirectory = $env:DOCUMENTASSISTANT_HOME }
$shell = New-Object -ComObject WScript.Shell
$icon = Join-Path $projectDirectory 'document_assistant\documentassistant.ico'
if (-not (Test-Path -LiteralPath $icon)) { throw '专属图标缺失，请重新下载完整项目。' }
$plans = @()
if ($DestinationFolder) {
    $plans += [pscustomobject]@{ Folder = [IO.Path]::GetFullPath($DestinationFolder); Hotkey = $Hotkey }
}
else {
    $plans += [pscustomobject]@{ Folder = [Environment]::GetFolderPath('Desktop'); Hotkey = $Hotkey }
    $plans += [pscustomobject]@{ Folder = [Environment]::GetFolderPath('Programs'); Hotkey = '' }
}
try {
    # Preflight every destination; preserve unrelated existing shortcuts.
    foreach ($plan in $plans) {
        if (-not $plan.Folder) { throw '无法找到当前用户的桌面或开始菜单位置。' }
        $path = Join-Path $plan.Folder 'DocumentAssistant.lnk'
        if (Test-Path -LiteralPath $path) {
            $existing = $shell.CreateShortcut($path)
            $owned = $existing.Description -eq $description
            [Runtime.InteropServices.Marshal]::FinalReleaseComObject($existing) | Out-Null
            if (-not $owned) { throw "存在同名快捷方式，已保留原文件：$path。请先重命名该快捷方式后重试。" }
        }
    }
    foreach ($plan in $plans) {
        New-Item -ItemType Directory -Path $plan.Folder -Force | Out-Null
        $path = Join-Path $plan.Folder 'DocumentAssistant.lnk'
        if (Test-Path -LiteralPath $path) {
            $backupDirectory = Join-Path $runtimeDirectory ('shortcut-backups\' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
            Copy-Item -LiteralPath $path -Destination (Join-Path $backupDirectory 'DocumentAssistant.lnk')
        }
        $shortcut = $shell.CreateShortcut($path)
        $shortcut.TargetPath = $target
        $shortcut.Arguments = $arguments
        $shortcut.WorkingDirectory = $projectDirectory
        $shortcut.Description = $description
        $shortcut.WindowStyle = 7
        $shortcut.Hotkey = $plan.Hotkey
        $shortcut.IconLocation = "$icon,0"
        $shortcut.Save()
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut) | Out-Null
        Push-Location $projectDirectory
        try {
            & $consolePython -m document_assistant.windows_identity shortcut $path
            if ($LASTEXITCODE -ne 0) { throw "快捷方式应用身份配置失败：$path" }
        }
        finally { Pop-Location }
        $saved = $shell.CreateShortcut($path)
        $actualHotkey = ($saved.Hotkey.ToUpperInvariant().Split('+') | Sort-Object) -join '+'
        $expectedHotkey = ($plan.Hotkey.ToUpperInvariant().Split('+') | Sort-Object) -join '+'
        if ($saved.TargetPath -ne $target -or $saved.Arguments -ne $arguments -or $saved.WorkingDirectory -ne $projectDirectory -or $actualHotkey -ne $expectedHotkey) {
            throw "快捷方式写入校验失败：$path"
        }
        [pscustomobject]@{ Shortcut = $path; Hotkey = $saved.Hotkey; Project = $projectDirectory }
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($saved) | Out-Null
    }
}
finally { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) | Out-Null }
