@echo off
chcp 65001 >nul
title PDF to Markdown - Setup
cd /d "%~dp0"
set "BASE="
if defined CONDA_EXE for %%C in ("%CONDA_EXE%") do set "BASE=%%~dpC.."
if defined BASE if not exist "%BASE%\python.exe" set "BASE="
if not defined BASE for %%B in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%USERPROFILE%\miniforge3" "%LOCALAPPDATA%\anaconda3" "%LOCALAPPDATA%\miniconda3" "%LOCALAPPDATA%\miniforge3" "%ProgramData%\anaconda3" "%ProgramData%\miniconda3" "%ProgramData%\miniforge3" "C:\anaconda3" "C:\miniconda3") do if not defined BASE if exist "%%~B\python.exe" set "BASE=%%~B"
if not defined BASE goto noconda
"%BASE%\python.exe" install.py
pause
exit /b

:noconda
echo.
echo 找不到 Anaconda。請先安裝 Anaconda 或 Miniconda（安裝時選 Just Me），
echo 再重新點兩下「首次安裝.bat」。
echo 下載網址：https://www.anaconda.com/download
echo.
pause