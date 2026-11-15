@echo off
rem Set up the ESP-IDF v6.1 build environment installed under F:\Espressif,
rem then run whatever command follows. Run from cmd.exe or PowerShell (not Git Bash).
rem
rem   firmware\idf-env.cmd python firmware\build_firmware.py
rem   firmware\idf-env.cmd python firmware\build_firmware.py --no-flash
rem
rem Why this exists: the Espressif installer (eim 0.21.1) crashed while writing its
rem own activation script for a version named "release/v6.1", so we ask ESP-IDF's
rem idf_tools.py for the environment directly.
setlocal
set "MSYSTEM="
set "IDF_PATH=F:\Espressif\release\v6.1\esp-idf"
set "IDF_TOOLS_PATH=F:\Espressif"
set "IDF_PYTHON_ENV_PATH=F:\Espressif\tools\python\release\v6.1\venv"
if not exist "%IDF_PYTHON_ENV_PATH%\Scripts\python.exe" (
  echo ESP-IDF python environment not found at %IDF_PYTHON_ENV_PATH%
  exit /b 1
)
rem Python must read/write UTF-8 (Chinese text in Kconfig and our config fragment).
set "PYTHONUTF8=1"
rem idf.py looks for the constraints file one level above where the installer put it.
if not exist "%IDF_TOOLS_PATH%\espidf.constraints.v6.1.txt" if exist "%IDF_TOOLS_PATH%\tools\espidf.constraints.v6.1.txt" copy /y "%IDF_TOOLS_PATH%\tools\espidf.constraints.v6.1.txt" "%IDF_TOOLS_PATH%\espidf.constraints.v6.1.txt" >nul
set "PATH=%IDF_PYTHON_ENV_PATH%\Scripts;%PATH%"
for /f "usebackq tokens=1,* delims==" %%A in (`python "%IDF_PATH%\tools\idf_tools.py" export --format key-value`) do call set "%%A=%%B"
%*
exit /b %errorlevel%
