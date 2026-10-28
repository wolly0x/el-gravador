@echo off
rem =====================================================================
rem  El Gravador 18 Pro Max - inicializador para Windows 10/11
rem
rem  Uso normal:      duplo clique neste arquivo
rem  Interface Tk:    executar.bat --tk
rem  Abrir projeto:   executar.bat --projeto "projetos\meu.json"
rem
rem  Na primeira execucao cria a pasta .venv e instala as dependencias.
rem  Nas execucoes seguintes apenas sincroniza o que estiver faltando.
rem =====================================================================
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title El Gravador 18 Pro Max
cd /d "%~dp0"

set "RAIZ=%~dp0"
set "VENV=%RAIZ%.venv"
set "PYVENV=%VENV%\Scripts\python.exe"
set "REQ=%RAIZ%requirements.txt"
set "LOG=%RAIZ%logs\instalacao.log"

echo.
echo  ==========================================================
echo    El Gravador 18 Pro Max
echo  ==========================================================
echo.

if not exist "%RAIZ%main.py" goto :pasta_errada
if not exist "%REQ%" goto :sem_requirements
if not exist "%RAIZ%logs" mkdir "%RAIZ%logs" >nul 2>&1

if exist "%PYVENV%" goto :venv_existente

rem ---------------------------------------------------------------------
rem  1. Localizar o Python do sistema
rem ---------------------------------------------------------------------
:localizar_python
echo  [ELG] Procurando Python...
set "PY="

py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3.12"
if defined PY goto :python_ok

py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto :python_ok

python -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=python"

:python_ok
if not defined PY goto :sem_python

%PY% -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto :python_velho

for /f "usebackq delims=" %%v in (`%PY% -c "import platform; print(platform.python_version())"`) do set "PYVER=%%v"
echo         Python %PYVER% encontrado.

rem  O Tkinter vem com o Python e nao pode ser instalado via pip.
%PY% -c "import tkinter" >nul 2>&1
if errorlevel 1 goto :sem_tkinter

rem ---------------------------------------------------------------------
rem  2. Criar o ambiente virtual
rem ---------------------------------------------------------------------
echo  [ELG] Criando ambiente virtual em .venv...
%PY% -m venv "%VENV%"
if errorlevel 1 goto :erro_venv
if not exist "%PYVENV%" goto :erro_venv
goto :dependencias

rem ---------------------------------------------------------------------
rem  Ambiente virtual existente: validar antes de usar
rem ---------------------------------------------------------------------
:venv_existente
"%PYVENV%" -c "import sys" >nul 2>&1
if not errorlevel 1 goto :dependencias
echo  [ELG] Ambiente virtual invalido. Recriando...
rmdir /s /q "%VENV%" >nul 2>&1
if exist "%PYVENV%" goto :erro_venv
goto :localizar_python

rem ---------------------------------------------------------------------
rem  3. Instalar / sincronizar as dependencias
rem ---------------------------------------------------------------------
:dependencias
echo  [ELG] Verificando dependencias...

"%PYVENV%" -c "import webview, pyautogui, pynput, cv2, numpy, PIL" >nul 2>&1
if errorlevel 1 goto :instalar_tudo

"%PYVENV%" -m pip install -r "%REQ%" --disable-pip-version-check --quiet --no-input >>"%LOG%" 2>&1
if errorlevel 1 goto :erro_deps
goto :verificar

:instalar_tudo
echo.
echo         Primeira execucao: baixando componentes. Isso pode levar
echo         alguns minutos e precisa de internet.
echo.
"%PYVENV%" -m pip install --upgrade pip --disable-pip-version-check --quiet --no-input >>"%LOG%" 2>&1
"%PYVENV%" -m pip install -r "%REQ%" --disable-pip-version-check --no-input
if errorlevel 1 goto :erro_deps

rem ---------------------------------------------------------------------
rem  4. Conferir e abrir
rem ---------------------------------------------------------------------
:verificar
echo  [ELG] Conferindo componentes...
"%PYVENV%" -c "import tkinter" >nul 2>&1
if errorlevel 1 goto :sem_tkinter
"%PYVENV%" -c "import webview, pyautogui, pynput, cv2, numpy, PIL" >nul 2>&1
if errorlevel 1 goto :erro_import

call :checar_webview2

echo.
echo  [ELG] Abrindo o El Gravador 18 Pro Max...
echo.
set "PYTHONUTF8=1"
"%PYVENV%" "%RAIZ%main.py" %*
set "CODIGO=%ERRORLEVEL%"
if not "%CODIGO%"=="0" goto :erro_app
exit /b 0

rem ---------------------------------------------------------------------
rem  Sub-rotinas
rem ---------------------------------------------------------------------
:checar_webview2
set "WV2="
for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv 2^>nul ^| findstr /i "REG_SZ"') do set "WV2=%%b"
if defined WV2 exit /b 0
for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv 2^>nul ^| findstr /i "REG_SZ"') do set "WV2=%%b"
if defined WV2 exit /b 0
for /f "tokens=2,*" %%a in ('reg query "HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv 2^>nul ^| findstr /i "REG_SZ"') do set "WV2=%%b"
if defined WV2 exit /b 0

echo.
echo  AVISO: WebView2 Runtime nao encontrado.
echo         A interface web pode nao abrir. Instale em:
echo         https://developer.microsoft.com/microsoft-edge/webview2/
echo         Alternativa: executar.bat --tk
echo.
exit /b 0

rem ---------------------------------------------------------------------
rem  Mensagens de erro
rem ---------------------------------------------------------------------
:pasta_errada
echo  ERRO: main.py nao encontrado nesta pasta.
echo         Coloque o executar.bat na raiz do El Gravador 18 Pro Max.
echo.
pause
exit /b 1

:sem_requirements
echo  ERRO: requirements.txt nao encontrado.
echo         Ele precisa estar na mesma pasta do executar.bat.
echo.
pause
exit /b 1

:sem_python
echo.
echo  ERRO: Python nao encontrado.
echo.
echo  1. Baixe o Python 3.12 (64 bits):
echo     https://www.python.org/downloads/windows/
echo  2. No instalador, marque "Add python.exe to PATH".
echo  3. Feche e abra este arquivo novamente.
echo.
pause
exit /b 1

:python_velho
echo.
echo  ERRO: o Python encontrado e antigo demais.
%PY% -c "import platform; print('        Versao:', platform.python_version())"
echo  O El Gravador 18 Pro Max precisa do Python 3.10 ou superior.
echo  Recomendado: Python 3.12 (64 bits).
echo.
pause
exit /b 1

:sem_tkinter
echo.
echo  ERRO: este Python nao tem o Tkinter, necessario para o HUD,
echo        os atalhos e a interface classica.
echo.
echo  Reinstale o Python pelo site oficial e marque:
echo    - "tcl/tk and IDLE"
echo    - "Add python.exe to PATH"
echo  Depois apague a pasta .venv e rode este arquivo de novo.
echo.
pause
exit /b 1

:erro_venv
echo.
echo  ERRO: nao foi possivel criar o ambiente virtual em:
echo    %VENV%
echo.
echo  Verifique espaco em disco, permissao de escrita na pasta e o
echo  antivirus. Se a pasta .venv existir, apague-a e tente de novo.
echo.
pause
exit /b 1

:erro_deps
echo.
echo  ERRO: falha ao instalar as dependencias.
echo.
echo  Veja o log: %LOG%
echo  Confira a conexao com a internet (ou proxy) e tente novamente.
echo.
pause
exit /b 1

:erro_import
echo.
echo  ERRO: as dependencias foram instaladas, mas a importacao falhou.
echo.
echo  Rode manualmente para ver o detalhe:
echo    "%PYVENV%" -c "import webview, pyautogui, pynput, cv2, numpy, PIL"
echo.
pause
exit /b 1

:erro_app
echo.
echo  O programa terminou com codigo %CODIGO%.
echo.
echo  Verifique:
echo    - o log em %RAIZ%logs
echo    - o WebView2 Runtime instalado
echo    - tente a interface classica: executar.bat --tk
echo.
pause
exit /b %CODIGO%
