@echo off
cd /d "%~dp0"
copy /y ".env" "ritual_detective\.env" >nul 2>&1
".venv\Scripts\adk.exe" web --port 8000 --allow_origins "*"
