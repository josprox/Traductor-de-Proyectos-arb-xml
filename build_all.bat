@echo off
echo =============================================
echo  Compilacion Completa: App + Instalador
echo =============================================
echo.

echo PASO 1: Compilando aplicacion Python a ejecutable...
echo.
call build.bat
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la compilacion de la aplicacion.
    echo No se puede continuar con el instalador.
    pause
    exit /b 1
)

echo.
echo =============================================
echo.
echo PASO 2: Creando instalador de Windows...
echo.
call build_installer.bat
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la creacion del instalador.
    pause
    exit /b 1
)

echo.
echo =============================================
echo  PROCESO COMPLETADO
echo =============================================
echo.
echo Se han creado:
echo   1. Ejecutable en: dist\TraductorApp\
echo   2. Instalador en: app\
echo.
pause
