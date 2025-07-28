
# Herramienta Multi-propósito: Traductor de Proyectos Flutter/Kotlin

Esta herramienta de escritorio, construida con PySide6, ofrece funcionalidades para la gestión de traducciones en proyectos Flutter (con archivos ARB) y Kotlin (con archivos XML de recursos).

## Características Principales

### 1. Traductor de Idiomas
Permite gestionar cadenas de texto y traducciones para aplicaciones móviles.

* **Soporte Multiplataforma**: Compatible con proyectos Flutter (usando archivos `.arb`) y Kotlin (usando archivos `strings.xml`).
* **Adición y Traducción de Cadenas**: Añade nuevas etiquetas/strings y las traduce automáticamente a múltiples idiomas utilizando la API de Google Translate (requiere configuración de una clave API).
* **Gestión de Activos de Idioma**:
    * **Creación de Archivos/Carpetas de Idioma**: Genera los archivos o carpetas necesarios para nuevos idiomas basándose en un idioma base existente.
    * **Eliminación de Archivos/Carpetas de Idioma**: Elimina los archivos o carpetas de idioma (excepto el idioma base).
    * **Eliminación de Claves Específicas**: Elimina una etiqueta o string específico de todos los archivos de idioma.
* **Integración con Flutter Intl**: Ejecuta el comando `flutter pub run flutter_intl:generate` para actualizar las clases de internacionalización en proyectos Flutter.
* **Historial de Operaciones**: Mantiene un registro de las acciones realizadas (traducciones, creaciones, eliminaciones).
* **Deshacer Última Acción**: Permite revertir la última operación de traducción o creación de activos.

## Requisitos

* **Python 3.x**
* **PySide6**: Para la interfaz gráfica.
* **`requests`**: Para la comunicación con APIs web (ej. Google Translate).
* **Flutter SDK**: Instalado y configurado en la PATH del sistema, necesario para las funcionalidades de Flutter (intl, etc.).

## Estructura del Proyecto (Versión Original)

```

.
├── controller/
│   └── translation\_controller.py
├── model/
│   └── translation\_model.py
├── view/
│   └── translation\_view.py
├── main.py
└── README.md

````

## Uso

1.  **Clonar el repositorio** (o descargar los archivos).
2.  **Instalar dependencias Python**:
    ```bash
    pip install PySide6 requests
    ```
3.  **Asegurarse de tener Flutter SDK instalado y en la PATH.**
4.  **Ejecutar la aplicación**:
    ```bash
    python main.py
    ```

### Interfaz de Usuario

* Selecciona la plataforma (Flutter o Kotlin).
* Selecciona la carpeta raíz de tu proyecto.
* Introduce el idioma base, el texto original y la clave/nombre del string.
* Haz clic en "Traducir y Agregar" para añadir la entrada a todos los idiomas.
* Usa los botones para crear, eliminar archivos de idioma o claves específicas.
* Si usas Flutter, recuerda ejecutar "Actualizar Intl de Flutter" después de hacer cambios en los `.arb` para generar las clases Dart.

## Consideraciones

* Para Flutter, la herramienta espera una estructura de proyecto estándar, especialmente en `lib/l10n` para los archivos ARB. El archivo ARB base debe tener la clave `@@locale`.
* Para Kotlin, espera la estructura `app/src/main/res/values` para el idioma base y `values-xx` para otros idiomas.