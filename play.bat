@echo off
rem Siege Wing - start the local server and open the game in the default browser
cd /d "%~dp0"
start "" http://localhost:8765/
where py >nul 2>nul && (py -3 tools\serve.py 8765) || (python tools\serve.py 8765)
