@echo off
rem Masaustu uygulamasini derler: build_exe.bat [--onefile]
chcp 65001 >nul
py "%~dp0build_exe.py" %*
if errorlevel 1 pause
