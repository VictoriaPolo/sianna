@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    where py >nul 2>nul
    if %errorlevel% neq 0 (
        echo No se encontro Python en el PATH de esta ventana.
        echo Abre el Anaconda Prompt ^(o el entorno^) que usas normalmente para
        echo este proyecto ^(el que tiene mediapipe/opencv instalados^), navega a
        echo esta carpeta y corre:  python gestureRecognition.py
        pause
        exit /b 1
    )
    set PYCMD=py
) else (
    set PYCMD=python
)

echo Usando: %PYCMD%
%PYCMD% -c "import cv2, mediapipe, serial" 2>nul
if %errorlevel% neq 0 (
    echo.
    echo Este Python no tiene mediapipe / opencv / pyserial instalados.
    echo ^(El proyecto se compilo originalmente con Python 3.8 - probablemente
    echo  tengas un entorno conda especifico para esto.^)
    echo Abre el Anaconda Prompt / entorno donde SI los tengas instalados,
    echo navega a esta carpeta y corre:
    echo     pip install requests
    echo     python gestureRecognition.py
    pause
    exit /b 1
)

%PYCMD% -m pip install requests >nul 2>nul

echo.
echo ============================================
echo  Iniciando reconocimiento de gestos SIANNA...
echo  Controles: [q] salir    [t] prueba de precision
echo  (Asegurate de que el panel web ya este corriendo:
echo   iniciar_panel_web.bat en la carpeta WebApp)
echo ============================================
echo.
%PYCMD% gestureRecognition.py
pause
