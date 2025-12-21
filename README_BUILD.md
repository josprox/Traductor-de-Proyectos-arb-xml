# 📦 Guía de Compilación a Ejecutable

Esta guía explica cómo convertir la aplicación Python en un ejecutable de Windows (.exe).

## 🔧 Requisitos Previos

- Python 3.8 o superior instalado
- Todas las dependencias del proyecto instaladas

## 📋 Pasos para Compilar

### 1. Instalar Dependencias

Primero, asegúrate de tener todas las dependencias instaladas:

```bash
pip install -r requirements.txt
```

Esto instalará:
- PySide6 (GUI)
- openpyxl (Excel)
- lxml (XML)
- requests (HTTP)
- **PyInstaller** (empaquetado)

### 2. Compilar la Aplicación

#### Opción A: Usando el script automatizado (Recomendado)

Simplemente ejecuta el archivo batch:

```bash
build.bat
```

Este script:
- ✅ Verifica que PyInstaller esté instalado
- ✅ Limpia compilaciones anteriores
- ✅ Compila la aplicación con el archivo de configuración
- ✅ Verifica que el ejecutable se haya creado correctamente

#### Opción B: Comando manual

Si prefieres ejecutar el comando directamente:

```bash
python -m PyInstaller build.spec --clean
```

### 3. Encontrar el Ejecutable

Una vez completada la compilación, encontrarás:

```
dist/
└── TraductorApp/
    ├── TraductorApp.exe     ← Tu aplicación ejecutable
    ├── icon/                 ← Carpeta con iconos
    └── [otros archivos]      ← Librerías necesarias
```

## 🎁 Crear Instalador de Windows (Opcional)

Si quieres crear un instalador profesional con Inno Setup:

### Prerrequisitos

1. Descargar e instalar [Inno Setup 6](https://jrsoftware.org/isdl.php)

### Crear el Instalador

#### Opción A: Todo en uno

Ejecuta el script que compila la aplicación Y crea el instalador:

```bash
build_all.bat
```

#### Opción B: Solo el instalador (si ya compilaste la app)

```bash
build_installer.bat
```

El instalador se creará en la carpeta `app/` con el nombre:
```
app/TraductorAppSetup_1.5.exe
```

### Características del Instalador

✅ Instalación asistida con interfaz moderna
✅ Icono personalizado
✅ Crea acceso directo en el menú de inicio
✅ Opción para crear icono en el escritorio
✅ Desinstalador incluido
✅ Soporte para arquitectura x64
✅ No requiere permisos de administrador

## 🚀 Distribución

### Opción 1: Distribuir solo el ejecutable

Para distribuir tu aplicación sin instalador:

1. **Comprime la carpeta completa** `dist/TraductorApp/` en un archivo ZIP
2. **Comparte el ZIP** con los usuarios
3. Los usuarios solo necesitan:
   - Extraer el ZIP
   - Ejecutar `TraductorApp.exe`
   - **NO necesitan Python instalado**

### Opción 2: Distribuir con instalador (Recomendado)

Para una experiencia más profesional:

1. **Compila el instalador** usando `build_installer.bat` o `build_all.bat`
2. **Comparte el archivo** `app/TraductorAppSetup_1.5.exe`
3. Los usuarios solo necesitan:
   - Ejecutar el instalador
   - Seguir el asistente de instalación
   - La app quedará instalada en "Archivos de programa"
   - Incluye desinstalador automático

## ⚙️ Configuración Personalizada

### Archivo build.spec (PyInstaller)

El archivo [build.spec](build.spec) contiene la configuración de PyInstaller:

#### Cambiar el icono del ejecutable

```python
icon='icon/icono.ico'  # Ruta al archivo .ico
```

#### Agregar archivos adicionales

```python
datas=[
    ('icon/icono.ico', 'icon'),
    ('tu_archivo.txt', '.'),  # Agregar nuevo archivo
],
```

#### Ocultar/Mostrar la consola

```python
console=False  # False = sin consola, True = con consola
```

#### Cambiar el nombre del ejecutable

```python
name='TraductorApp'  # Cambiar por el nombre deseado
```

### Archivo buildinno.iss (Inno Setup)

El archivo [buildinno.iss](buildinno.iss) contiene la configuración del instalador:

#### Cambiar la versión de la aplicación

```iss
#define MyAppVersion "1.5"
```

#### Cambiar el nombre del instalador generado

```iss
OutputBaseFilename=TraductorAppSetup_{#MyAppVersion}
```

#### Modificar información de la empresa

```iss
#define MyAppPublisher "JOSPROX MX"
#define MyAppURL "https://josprox.com/"
```

#### Cambiar el icono del instalador

```iss
SetupIconFile={#ProjectRoot}\icon\icono.ico
```

**Nota:** Las rutas ahora son dinámicas usando `{#ProjectRoot}`, por lo que el script funciona en cualquier ubicación.

## 🐛 Solución de Problemas

### Error: "PyInstaller no encontrado"
```bash
pip install pyinstaller
```

### Error: "Failed to execute script"
- Verifica que todos los módulos estén en `hiddenimports` en [build.spec](build.spec)
- Prueba ejecutar desde la terminal para ver errores detallados

### El ejecutable es muy grande
- Es normal, incluye Python y todas las librerías
- Un ejecutable con PySide6 suele pesar 80-150 MB

### Error con archivos de recursos
- Asegúrate de que todos los archivos estén listados en `datas=[]`
- Las rutas deben ser relativas al archivo [main.py](main.py)

## 📝 Notas Importantes

- ✅ El ejecutable **NO es un solo archivo** (es una carpeta con el .exe y sus dependencias)
- ✅ Incluye el **icono personalizado** (icono.ico)
- ✅ **No muestra consola** al ejecutarse (console=False)
- ✅ Compatible con **Windows 10/11**
- ⚠️ El ejecutable solo funciona en Windows (compila en el mismo OS donde se usará)

## 🔄 Recompilar después de cambios

Cada vez que modifiques el código:

1. Ejecuta `build.bat` para recompilar el ejecutable
2. Ejecuta `build_installer.bat` para recrear el instalador
3. O usa `build_all.bat` para hacer ambos pasos automáticamente

Si agregaste archivos nuevos:
- Actualiza `datas=[]` en [build.spec](build.spec)
- Si es necesario, actualiza la sección `[Files]` en [buildinno.iss](buildinno.iss)

## 📁 Estructura de Archivos de Compilación

```
proyecto/
├── build.bat                    # Compila la aplicación
├── build_installer.bat          # Crea el instalador
├── build_all.bat               # Compila app + instalador
├── build.spec                  # Configuración de PyInstaller
├── buildinno.iss               # Configuración de Inno Setup
├── dist/
│   └── TraductorApp/           # Ejecutable y dependencias
│       └── TraductorApp.exe
└── app/
    └── TraductorAppSetup_1.5.exe  # Instalador final
```

---

**¿Dudas?** Revisa la [documentación oficial de PyInstaller](https://pyinstaller.org/en/stable/)
