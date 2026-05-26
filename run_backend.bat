@echo off

REM ==========================================
REM GUARDAR CARPETA ACTUAL
REM ==========================================

set ROOT_DIR=%cd%

REM ==========================================
REM ENTORNO VIRTUAL DEL PROYECTO
REM ==========================================

set VENV_ACTIVATE=%ROOT_DIR%\.venv313\Scripts\activate.bat

REM ==========================================
REM ACTIVAR ENTORNO VIRTUAL
REM ==========================================

if not exist "%VENV_ACTIVATE%" (
    echo No existe el entorno virtual .venv313.
    echo Cree el entorno con: py -3.13 -m venv .venv313
    pause
    exit /b 1
)

call "%VENV_ACTIVATE%"

REM ==========================================
REM VOLVER A LA CARPETA PRINCIPAL
REM ==========================================

cd /d %ROOT_DIR%

echo.
echo 🚀 Iniciando servidores...
echo.

REM ==========================================
REM SERVIDORES FASTAPI
REM ==========================================

start cmd /k "cd /d %ROOT_DIR% && call .venv313\Scripts\activate.bat && python -m uvicorn login.main:app --reload --port 8000"

start cmd /k "cd /d %ROOT_DIR% && call .venv313\Scripts\activate.bat && python -m uvicorn usuarios.usuarios:app --reload --port 8001"

start cmd /k "cd /d %ROOT_DIR% && call .venv313\Scripts\activate.bat && python -m uvicorn personal.personal:app --reload --port 8002"

start cmd /k "cd /d %ROOT_DIR% && call .venv313\Scripts\activate.bat && python -m uvicorn armamento.armamento:app --reload --port 8003"

REM ==========================================
REM SERVIDOR ARCHIVOS
REM ==========================================

start cmd /k "cd /d %ROOT_DIR% && call .venv313\Scripts\activate.bat && python servidor_archivos.py"

echo.
echo ✅ Todos los servidores iniciados
echo.

pause
