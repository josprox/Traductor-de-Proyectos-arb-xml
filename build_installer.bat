@echo off
echo =============================================
echo  Creando Instalador con Inno Setup
echo =============================================
echo.

REM Verificar que el ejecutable exista
if not exist "dist\TraductorApp\TraductorApp.exe" (
    echo [ERROR] No se encuentra el ejecutable compilado.
    echo Por favor, ejecuta primero "build.bat" para compilar la aplicacion.
    echo.
    pause
    exit /b 1
)

REM Buscar Inno Setup en ubicaciones comunes
set INNO_PATH=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set INNO_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set INNO_PATH=C:\Program Files\Inno Setup 6\ISCC.exe
if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" set INNO_PATH=C:\Program Files (x86)\Inno Setup 5\ISCC.exe
if exist "C:\Program Files\Inno Setup 5\ISCC.exe" set INNO_PATH=C:\Program Files\Inno Setup 5\ISCC.exe

if "%INNO_PATH%"=="" (
    echo [ERROR] No se encontro Inno Setup instalado.
    echo.
    echo Por favor, descarga e instala Inno Setup desde:
    echo https://jrsoftware.org/isdl.php
    echo.
    pause
    exit /b 1
)

echo [OK] Inno Setup encontrado: %INNO_PATH%
echo.

echo [1/2] Creando directorio de salida...
if not exist "app" mkdir app
echo [OK] Directorio creado.
echo.

echo [2/2] Compilando instalador con Inno Setup...
"%INNO_PATH%" "buildinno.iss"
if errorlevel 1 (
    echo.
    echo [ERROR] La compilacion del instalador fallo.
    pause
    exit /b 1
)

echo.
echo =============================================
echo  INSTALADOR CREADO EXITOSAMENTE
echo =============================================
echo.
echo El instalador se encuentra en:
echo %CD%\app\
echo.
dir /b app\*.exe
echo.
pause
