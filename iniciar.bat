@echo off
setlocal
cd /d "%~dp0"
set "SIPAC_PYTHON="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "SIPAC_PYTHON=py -3"
if defined SIPAC_PYTHON goto preparar
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "SIPAC_PYTHON=python"
if defined SIPAC_PYTHON goto preparar
echo Instale Python 3.10 ou superior, com o Python Launcher ou o Python no PATH.
pause
exit /b 1
:preparar
if exist .venv\Scripts\python.exe goto conferir
%SIPAC_PYTHON% -m venv .venv
if errorlevel 1 goto erro
:conferir
.venv\Scripts\python.exe -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto versao
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto erro
.venv\Scripts\python.exe app.py %*
set "SIPAC_RESULT=%ERRORLEVEL%"
if not "%SIPAC_RESULT%"=="0" pause
exit /b %SIPAC_RESULT%
:versao
echo O ambiente .venv usa um Python antigo. Renomeie .venv e execute novamente com Python 3.10 ou superior.
pause
exit /b 1
:erro
echo Nao foi possivel preparar o ambiente. Confira a mensagem acima e o acesso a internet.
pause
exit /b 1
