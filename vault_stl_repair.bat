@echo off
rem VAULT STL repair - repairs the STL meshes of a whole library with the Windows 3D model repair service
rem (the one Bambu Studio uses for "Repair model") and writes a repaired copy of the library.
rem   vault_stl_repair.bat "D:\VAULT" "D:\VAULT_repaired" [--workers 2] [--all] [--only text]
rem An interrupted run (Ctrl+C) can be started again - finished files are skipped.
chcp 65001 >nul
setlocal EnableExtensions

if "%~2"=="" (
  echo Usage: vault_stl_repair.bat "D:\VAULT" "D:\VAULT_repaired" [--workers 2] [--all] [--only text]
  echo        first folder = your VAULT STL library, second = new folder for the repaired copy
  pause
  exit /b 1
)

set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>&1 && set "PY=python"
if not defined PY (
  echo Python 3 not found. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^).
  pause
  exit /b 1
)

%PY% "%~dp0vault_stl_repair.py" %*
set "CODE=%ERRORLEVEL%"
echo.
if "%CODE%"=="0" (echo Finished without errors.) else (echo Finished with code %CODE% - see the messages above.)
pause
exit /b %CODE%
