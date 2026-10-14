@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-shortcuts.ps1"
if errorlevel 1 (
    echo Shortcut setup failed. See the message above.
) else (
    echo Desktop shortcut ready. Hotkey: Ctrl+Alt+D
)
pause
