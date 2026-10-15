@echo off
chcp 65001 >nul
title PDF to Markdown
cd /d "%~dp0"
set "ENV="
if exist "env_path.txt" set /p ENV=<"env_path.txt"
if defined ENV if not exist "%ENV%\python.exe" set "ENV="
if not defined ENV for %%B in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%USERPROFILE%\miniforge3" "%LOCALAPPDATA%\anaconda3" "%LOCALAPPDATA%\miniconda3" "%LOCALAPPDATA%\miniforge3" "%ProgramData%\anaconda3" "%ProgramData%\miniconda3" "%ProgramData%\miniforge3" "C:\anaconda3" "C:\miniconda3") do for %%E in (pdf2md nougat) do if not defined ENV if exist "%%~B\envs\%%E\python.exe" set "ENV=%%~B\envs\%%E"
if not defined ENV goto noenv
set "PATH=%ENV%;%ENV%\Library\bin;%ENV%\Scripts;%PATH%"
set "PYTHONUTF8=1"
"%ENV%\python.exe" server.py
pause
exit /b

:noenv
echo.
echo 找不到執行環境。第一次使用請先點兩下「首次安裝.bat」。
echo.
pause