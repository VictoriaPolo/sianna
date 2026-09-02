@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    where py >nul 2>nul
    if %errorlevel% neq 0 (
        echo No se encontro Python en el PATH de esta ventana.
        echo Abre el mismo Anaconda Prompt / entorno que usas para el proyecto
        echo y corre manualmente:
        echo     pip install -r requirements.txt
        echo     python app.py
        pause
        exit /b 1
    )
    set PYCMD=py
) else (
    set PYCMD=python
)

echo Usando: %PYCMD%
echo.
echo Instalando/actualizando dependencias del panel web (Flask)...
%PYCMD% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo La instalacion fallo. Revisa el mensaje de arriba.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Panel SIANNA iniciando en http://127.0.0.1:5050
echo  Dejalo abierto y entra a esa direccion en tu navegador.
echo  Para cerrarlo: Ctrl+C en esta ventana.
echo ============================================
echo.
%PYCMD% app.py
pause
