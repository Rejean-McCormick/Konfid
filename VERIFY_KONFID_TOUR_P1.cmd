@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 goto PYTHON
py -3 "%~dp0tools\tandem_konfid_tour\install.py" verify
exit /b %errorlevel%
:PYTHON
where python >nul 2>&1
if errorlevel 1 goto NOPYTHON
python "%~dp0tools\tandem_konfid_tour\install.py" verify
exit /b %errorlevel%
:NOPYTHON
echo [BLOQUE] Python 3.12+ introuvable (py -3 / python).
exit /b 2
