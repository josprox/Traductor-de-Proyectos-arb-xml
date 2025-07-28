import os
import sys
from datetime import datetime
# Importar la clase TranslationCore del nuevo archivo
from translation_core import TranslationCore

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QWidget, QVBoxLayout,
    QLabel, QLineEdit, QTextEdit, QInputDialog, QMessageBox, QProgressBar,
    QHBoxLayout, QDialog, QListWidget, QListWidgetItem, QComboBox, QFileDialog
)
from PySide6.QtCore import Qt, QThread, Signal

def get_script_dir():
    """
    Devuelve el directorio donde se encuentra el script.
    """
    return os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.realpath(__file__))

class WorkerThread(QThread):
    """
    Una subclase de QThread para realizar operaciones de larga duración en segundo plano,
    manteniendo la UI responsiva. Delega las operaciones a TranslationCore.
    """
    progress_updated = Signal(int)
    log_message = Signal(str)
    operation_finished = Signal(dict) # Señal genérica para indicar que una operación terminó
    error_occurred = Signal(str)
    command_output = Signal(str)

    def __init__(self, operation_type, core_instance, data=None):
        super().__init__()
        self.operation_type = operation_type
        self.core = core_instance # Instancia de TranslationCore
        self.data = data

    def run(self):
        """
        Ejecuta la operación especificada.
        """
        try:
            if self.operation_type == "translate_and_add":
                # Realizar la llamada a la API y luego añadir la entrada
                self.log_message.emit(f"Iniciando traducción para '{self.data['key']}' en plataforma {self.data['platform'].upper()}...")
                self.progress_updated.emit(0)
                translations = self.core.fetch_translations_from_api(
                    self.data['base_lang'], self.data['original_text'], self.data['platform']
                )
                self.progress_updated.emit(50) # Progreso después de la API

                # Pasar las traducciones y otros datos a la lógica de adición de entrada
                self.core.add_translation_entry(
                    self.data['base_lang'], self.data['original_text'], self.data['key'],
                    self.data['desc'], translations, self.data['existing_key_files'], self.data['platform']
                )
                self.operation_finished.emit({'type': 'translate_and_add', 'platform': self.data['platform']})

            elif self.operation_type == "delete_key":
                self.log_message.emit(f"Iniciando eliminación de clave/string '{self.data['key']}' en plataforma {self.data['platform'].upper()}...")
                self.progress_updated.emit(0)
                self.core.delete_key_entry(self.data['key'], self.data['platform'])
                self.operation_finished.emit({'type': 'delete_key', 'platform': self.data['platform']})

            elif self.operation_type == "run_flutter_intl_generate":
                output, return_code = self.core.run_flutter_intl_generate()
                self.command_output.emit(output)
                self.operation_finished.emit({'type': 'run_flutter_intl_generate', 'platform': 'flutter'})

        except Exception as e:
            self.error_occurred.emit(f"❌ Error en la operación '{self.operation_type}': {e}")
        finally:
            self.progress_updated.emit(100) # Asegurar que la barra de progreso llegue al final

class TranslatorApp(QMainWindow):
    """
    Ventana principal de la aplicación Traductor ARB/Kotlin.
    Gestiona la UI e interactúa con TranslationCore para la lógica de negocio.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Traductor ARB/Kotlin - Joss Red")
        self.setMinimumSize(700, 600)
        self.project_path = get_script_dir()
        self.current_platform = "flutter"

        # Primero inicializar la UI para que self.output exista
        self.init_ui() 

        # Ahora inicializar TranslationCore con la ruta del proyecto y un callback para el log de la UI
        self.core = TranslationCore(self.project_path, log_callback=self.log)

        self._update_project_path_display() # Actualizar el QLineEdit con la ruta inicial
        self._update_undo_button_state() # Asegurar estado inicial del botón deshacer

    def init_ui(self):
        """
        Inicializa los elementos de la interfaz de usuario y su diseño.
        """
        main_layout = QVBoxLayout()

        # Selector de plataforma
        platform_layout = QHBoxLayout()
        platform_layout.addWidget(QLabel("Seleccionar Plataforma:"))
        self.platform_selector = QComboBox()
        self.platform_selector.addItem("Flutter (ARB)", "flutter")
        self.platform_selector.addItem("Kotlin (XML)", "kotlin")
        self.platform_selector.currentIndexChanged.connect(self._on_platform_changed)
        platform_layout.addWidget(self.platform_selector)
        platform_layout.addStretch()
        main_layout.addLayout(platform_layout)

        # Selector de carpeta de proyecto
        project_path_layout = QHBoxLayout()
        project_path_layout.addWidget(QLabel("Ruta del Proyecto:"))
        self.project_path_display = QLineEdit(self.project_path)
        self.project_path_display.setReadOnly(True)
        project_path_layout.addWidget(self.project_path_display)
        self.select_folder_btn = QPushButton("Seleccionar Carpeta")
        self.select_folder_btn.clicked.connect(self._select_project_folder)
        project_path_layout.addWidget(self.select_folder_btn)
        main_layout.addLayout(project_path_layout)

        # Campos de entrada
        input_grid_layout = QVBoxLayout()
        input_grid_layout.addWidget(QLabel("Idioma base"))
        self.base_lang_input = QLineEdit()
        self.base_lang_input.setPlaceholderText("Idioma base (ej. 'es', 'en')")
        input_grid_layout.addWidget(self.base_lang_input)

        input_grid_layout.addWidget(QLabel("Texto original"))
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Texto original")
        input_grid_layout.addWidget(self.text_input)

        input_grid_layout.addWidget(QLabel("Nombre de la etiqueta / String"))
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Nombre de la etiqueta (Flutter) / Nombre del string (Kotlin)")
        input_grid_layout.addWidget(self.key_input)

        self.desc_label = QLabel("Descripción (Flutter - opcional)")
        input_grid_layout.addWidget(self.desc_label)
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Descripción (opcional)")
        input_grid_layout.addWidget(self.desc_input)

        main_layout.addLayout(input_grid_layout)

        # Botones de acción
        button_layout = QHBoxLayout()
        self.translate_button = QPushButton("Traducir y Agregar")
        self.translate_button.clicked.connect(self._start_translation)
        button_layout.addWidget(self.translate_button)

        self.create_files_btn = QPushButton("Crear Archivos/Carpetas de Idioma")
        self.create_files_btn.clicked.connect(self.create_language_assets)
        button_layout.addWidget(self.create_files_btn)

        self.delete_files_btn = QPushButton("Eliminar Archivos/Carpetas de Idioma")
        self.delete_files_btn.clicked.connect(self.delete_language_assets)
        button_layout.addWidget(self.delete_files_btn)

        self.delete_key_btn = QPushButton("Eliminar Etiqueta/String")
        self.delete_key_btn.clicked.connect(self.delete_key_prompt)
        button_layout.addWidget(self.delete_key_btn)
        main_layout.addLayout(button_layout)
        
        # Botón específico de Flutter Intl Generate
        intl_generate_layout = QHBoxLayout()
        self.flutter_intl_generate_btn = QPushButton("Actualizar Intl de Flutter")
        self.flutter_intl_generate_btn.clicked.connect(self._start_flutter_intl_generate)
        intl_generate_layout.addWidget(self.flutter_intl_generate_btn)
        intl_generate_layout.addStretch()
        main_layout.addLayout(intl_generate_layout)

        # Botones de Historial y Deshacer
        history_undo_layout = QHBoxLayout()
        self.history_btn = QPushButton("Ver Historial")
        self.history_btn.clicked.connect(self.show_history)
        history_undo_layout.addWidget(self.history_btn)

        self.undo_btn = QPushButton("Deshacer Último Cambio")
        self.undo_btn.clicked.connect(self.undo_last_action)
        history_undo_layout.addWidget(self.undo_btn)
        # self._update_undo_button_state() # Esto se moverá después de que core esté inicializado
        main_layout.addLayout(history_undo_layout)

        # Barra de progreso
        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Progreso: %p%")
        main_layout.addWidget(self.progress_bar)

        main_layout.addSpacing(10)

        # Consola de salida
        main_layout.addWidget(QLabel("Consola de salida"))
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        main_layout.addWidget(self.output)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Establecer el estado inicial de la UI para Flutter
        self._update_ui_for_platform("flutter")

    def _on_platform_changed(self, index):
        """
        Actualiza la plataforma seleccionada y ajusta la UI.
        """
        self.current_platform = self.platform_selector.itemData(index)
        self._update_ui_for_platform(self.current_platform)
        self.log(f"Plataforma cambiada a: {self.current_platform.upper()}")

    def _update_ui_for_platform(self, platform):
        """
        Ajusta la visibilidad y el texto de los elementos de la UI según la plataforma.
        """
        if platform == "flutter":
            self.desc_label.show()
            self.desc_input.show()
            self.key_input.setPlaceholderText("Nombre de la etiqueta")
            self.translate_button.setText("Traducir y Agregar Etiqueta")
            self.create_files_btn.setText("Crear Archivos ARB")
            self.delete_files_btn.setText("Eliminar Archivos ARB")
            self.delete_key_btn.setText("Eliminar Etiqueta de Archivos")
            self.flutter_intl_generate_btn.show()
        elif platform == "kotlin":
            self.desc_label.hide()
            self.desc_input.hide()
            self.key_input.setPlaceholderText("Nombre del string (ej. 'app_name')")
            self.translate_button.setText("Traducir y Agregar String")
            self.create_files_btn.setText("Crear Carpetas y Archivos XML")
            self.delete_files_btn.setText("Eliminar Carpetas y Archivos XML")
            self.delete_key_btn.setText("Eliminar String de Archivos")
            self.flutter_intl_generate_btn.hide()

    def _select_project_folder(self):
        """
        Abre un diálogo para que el usuario seleccione la carpeta del proyecto.
        Actualiza la ruta del proyecto y recarga el historial/log si es necesario.
        """
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        
        selected_dir = dialog.getExistingDirectory(self, "Seleccionar Carpeta del Proyecto", self.project_path)
        
        if selected_dir and selected_dir != self.project_path:
            self.project_path = selected_dir
            self._update_project_path_display()
            self.log(f"Carpeta del proyecto seleccionada: {self.project_path}")
            # Actualizar la ruta del proyecto en la instancia de TranslationCore
            self.core.project_path = self.project_path
            # Recargar historial y re-inicializar log para la nueva ruta
            self.core._load_history()
            self.core._initialize_log_file()
            self._update_undo_button_state()
        elif selected_dir == self.project_path:
            self.log("La carpeta seleccionada ya es la carpeta del proyecto actual.")
        else:
            self.log("Selección de carpeta de proyecto cancelada.")

    def _update_project_path_display(self):
        """
        Actualiza el QLineEdit que muestra la ruta del proyecto.
        """
        self.project_path_display.setText(self.project_path)

    def log(self, text):
        """
        Añade un mensaje a la consola de salida.
        """
        self.output.append(text)

    def _update_undo_button_state(self):
        """
        Habilita o deshabilita el botón de deshacer según si hay historial.
        """
        self.undo_btn.setEnabled(len(self.core.get_history()) > 0)

    def create_language_assets(self):
        """
        Crea los archivos/carpetas de idioma según la plataforma seleccionada.
        """
        self._set_ui_enabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Creando archivos/carpetas: %p%")
        
        if self.current_platform == "flutter":
            self.core.create_flutter_language_files()
        elif self.current_platform == "kotlin":
            self.core.create_kotlin_language_folders()
        
        self.progress_bar.setValue(100)
        self.progress_bar.setValue(0)
        self._set_ui_enabled(True)

    def delete_language_assets(self):
        """
        Elimina los archivos/carpetas de idioma según la plataforma seleccionada.
        """
        msg_box = QMessageBox()
        msg_box.setWindowTitle("Confirmar Eliminación")
        msg_box.setText(f"¿Estás seguro de que quieres eliminar TODOS los archivos/carpetas de idioma para {self.current_platform.upper()}? Esta acción no se puede deshacer fácilmente.")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        reply = msg_box.exec()

        if reply == QMessageBox.No:
            self.log("Operación de eliminación de archivos/carpetas cancelada.")
            return

        self._set_ui_enabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Eliminando archivos/carpetas: %p%")

        if self.current_platform == "flutter":
            self.core.delete_flutter_language_files()
        elif self.current_platform == "kotlin":
            self.core.delete_kotlin_language_folders()
        
        self.progress_bar.setValue(100)
        self.progress_bar.setValue(0)
        self._set_ui_enabled(True)

    def _start_translation(self):
        """
        Inicia el proceso de traducción en un hilo separado, según la plataforma.
        """
        base_lang = self.base_lang_input.text().strip()
        original_text = self.text_input.text().strip()
        key = self.key_input.text().strip()
        desc = self.desc_input.text().strip() if self.current_platform == "flutter" else "Generado con Joss Red"

        if not all([base_lang, original_text, key]):
            self.log("⚠️ Por favor, completa todos los campos requeridos (Idioma base, Texto original, Nombre de la etiqueta/string).")
            return

        existing_key_files = self.core.check_key_existence(key, self.current_platform)

        if existing_key_files:
            msg = (f"⚠️ La clave/string '{key}' ya existe en las siguientes ubicaciones y no será sobrescrita:\n"
                   + "\n".join(existing_key_files)
                   + "\n\nLa traducción continuará para las ubicaciones donde la clave/string no existe.")
            self.log(msg)
            QMessageBox.information(self, "Clave/String existente en algunas ubicaciones", msg)

        self._set_ui_enabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Traduciendo y agregando: %p%")

        self.worker_thread = WorkerThread(
            operation_type="translate_and_add",
            core_instance=self.core,
            data={
                'base_lang': base_lang,
                'original_text': original_text,
                'key': key,
                'desc': desc,
                'existing_key_files': existing_key_files,
                'platform': self.current_platform
            }
        )
        self.worker_thread.progress_updated.connect(self.progress_bar.setValue)
        self.worker_thread.log_message.connect(self.log)
        self.worker_thread.operation_finished.connect(self._finish_operation)
        self.worker_thread.error_occurred.connect(self._handle_operation_error)
        self.worker_thread.start()

    def _start_flutter_intl_generate(self):
        """
        Inicia la ejecución del comando 'dart run intl_utils:generate' en un hilo de trabajo.
        """
        self.log("Iniciando comando 'dart run intl_utils:generate'...")
        self._set_ui_enabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Ejecutando comando: %p%")

        self.worker_thread = WorkerThread(
            operation_type="run_flutter_intl_generate",
            core_instance=self.core,
            data={} # No se necesitan datos adicionales para esta operación
        )
        self.worker_thread.progress_updated.connect(self.progress_bar.setValue)
        self.worker_thread.log_message.connect(self.log)
        self.worker_thread.command_output.connect(self.log)
        self.worker_thread.operation_finished.connect(self._finish_operation)
        self.worker_thread.error_occurred.connect(self._handle_operation_error)
        self.worker_thread.start()

    def delete_key_prompt(self):
        """
        Pide al usuario una clave/string para eliminar y luego inicia la eliminación.
        """
        key, ok = QInputDialog.getText(self, "Eliminar clave/string", "Nombre de la etiqueta/string a eliminar:")
        if ok and key:
            self.log(f"Iniciando eliminación de clave/string '{key.strip()}' en plataforma {self.current_platform.upper()}...")
            self._set_ui_enabled(False)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Eliminando clave/string: %p%")

            self.worker_thread = WorkerThread(
                operation_type="delete_key",
                core_instance=self.core,
                data={'key': key.strip(), 'platform': self.current_platform}
            )
            self.worker_thread.progress_updated.connect(self.progress_bar.setValue)
            self.worker_thread.log_message.connect(self.log)
            self.worker_thread.operation_finished.connect(self._finish_operation)
            self.worker_thread.error_occurred.connect(self._handle_operation_error)
            self.worker_thread.start()

    def _finish_operation(self, result_data):
        """
        Se llama cuando una operación del hilo de trabajo finaliza con éxito.
        """
        self.log(f"Operación '{result_data.get('type', 'desconocida')}' finalizada para {result_data.get('platform', 'desconocida').upper()}.")
        self.progress_bar.setValue(0)
        self._set_ui_enabled(True)
        self._update_undo_button_state()

    def _handle_operation_error(self, message):
        """
        Maneja los errores reportados por el hilo de trabajo.
        """
        self.log(message)
        QMessageBox.critical(self, "Error de Operación", message)
        self.progress_bar.setValue(0)
        self._set_ui_enabled(True)
        self._update_undo_button_state()

    def _set_ui_enabled(self, enabled):
        """
        Habilita o deshabilita todos los botones e inputs principales de la UI.
        """
        self.translate_button.setEnabled(enabled)
        self.create_files_btn.setEnabled(enabled)
        self.delete_files_btn.setEnabled(enabled)
        self.delete_key_btn.setEnabled(enabled)
        self.history_btn.setEnabled(enabled)
        self.base_lang_input.setEnabled(enabled)
        self.text_input.setEnabled(enabled)
        self.key_input.setEnabled(enabled)
        self.desc_input.setEnabled(enabled)
        self.platform_selector.setEnabled(enabled)
        self.select_folder_btn.setEnabled(enabled)
        
        self.flutter_intl_generate_btn.setEnabled(enabled and self.current_platform == "flutter")
        
        self._update_undo_button_state()

    def show_history(self):
        """
        Muestra el historial de traducciones en una nueva ventana de diálogo.
        """
        history_dialog = QDialog(self)
        history_dialog.setWindowTitle("Historial de Acciones")
        history_dialog.setMinimumSize(600, 400)
        layout = QVBoxLayout()

        history_list_widget = QListWidget()
        history = self.core.get_history()
        if not history:
            history_list_widget.addItem("No hay historial disponible.")
        else:
            for entry in reversed(history):
                action_type = entry.get('type', 'Desconocido')
                timestamp = datetime.fromisoformat(entry.get('timestamp')).strftime("%Y-%m-%d %H:%M:%S")
                data = entry.get('data', {})
                platform_hist = entry.get('platform', 'Desconocida')

                display_text = f"[{timestamp}] Plataforma: {platform_hist.upper()} - Tipo: {action_type.replace('_', ' ').title()}"

                if action_type == 'add_key':
                    key = data.get('key', 'N/A')
                    base_lang = data.get('base_lang', 'N/A')
                    original_text = data.get('original_text', 'N/A')
                    display_text += f" - Clave/String: '{key}', Idioma Base: '{base_lang}', Texto: '{original_text}'"
                elif action_type == 'delete_key':
                    key = data.get('key', 'N/A')
                    display_text += f" - Clave/String: '{key}'"

                history_list_widget.addItem(display_text)

        layout.addWidget(history_list_widget)
        history_dialog.setLayout(layout)
        history_dialog.exec()

    def undo_last_action(self):
        """
        Intenta deshacer la última acción registrada en el historial.
        """
        last_action = self.core.get_history()[-1] if self.core.get_history() else None

        if not last_action:
            self.log("⚠️ No hay acciones en el historial para deshacer.")
            return

        action_type = last_action['type']
        data = last_action['data']
        platform = last_action['platform']

        msg_box = QMessageBox()
        msg_box.setWindowTitle("Confirmar Deshacer")
        msg_box.setText(f"¿Estás seguro de que quieres deshacer la última acción ({action_type.replace('_', ' ').title()}) para {platform.upper()}?")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        reply = msg_box.exec()

        if reply == QMessageBox.No:
            self.log("Operación de deshacer cancelada.")
            return

        self.log(f"Intentando deshacer la acción: {action_type} en {platform.upper()}...")
        self._set_ui_enabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"Deshaciendo acción ({platform.upper()}): %p%")

        try:
            if action_type == 'add_key':
                key_to_delete = data['key']
                self.core.undo_delete_key_action(key_to_delete, platform)
                self.core.pop_last_history_entry()
                self.log(f"✅ Acción 'add_key' deshecha para '{key_to_delete}' en {platform.upper()}.")

            elif action_type == 'delete_key':
                key_to_restore = data['key']
                deleted_content = data['deleted_content_per_file']
                self.core.undo_add_key_action(key_to_restore, deleted_content, platform)
                self.core.pop_last_history_entry()
                self.log(f"✅ Acción 'delete_key' deshecha para '{key_to_restore}' en {platform.upper()}.")

            else:
                self.log(f"⚠️ Tipo de acción '{action_type}' no soportado para deshacer.")
                QMessageBox.warning(self, "Deshacer", "Tipo de acción no soportado para deshacer.")

        except Exception as e:
            self.log(f"❌ Error al deshacer la acción: {e}")
            QMessageBox.critical(self, "Error al Deshacer", f"Ocurrió un error al intentar deshacer: {e}")
        finally:
            self.progress_bar.setValue(0)
            self._set_ui_enabled(True)
            self._update_undo_button_state()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TranslatorApp()
    window.show()
    sys.exit(app.exec())
