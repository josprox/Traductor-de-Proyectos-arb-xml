@echo off
echo ====================================
echo  Compilando Aplicacion a Ejecutable
echo ====================================
echo.

REM Verificar que PyInstaller este instalado
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [ERROR] PyInstaller no esta instalado.
    echo Instalando dependencias...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar las dependencias.
        pause
        exit /b 1
    )
)

echo [1/3] Limpiando archivos de compilacion anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo [OK] Limpieza completada.
echo.

echo [2/3] Compilando con PyInstaller...
python -m PyInstaller build.spec --clean
if errorlevel 1 (
    echo.
    echo [ERROR] La compilacion fallo.
    pause
    exit /b 1
)
echo [OK] Compilacion exitosa.
echo.

echo [3/3] Verificando resultado...
if exist "dist\TraductorApp\TraductorApp.exe" (
    echo.
    echo ====================================
    echo  COMPILACION EXITOSA
    echo ====================================
    echo El ejecutable se encuentra en:
    echo %CD%\dist\TraductorApp\
    echo.
    echo Puedes distribuir toda la carpeta "TraductorApp" con todos sus archivos.
    echo.
) else (
    echo [ERROR] No se encontro el ejecutable generado.
)

pause
