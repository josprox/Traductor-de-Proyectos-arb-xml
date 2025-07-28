import os
import sys
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtCore import QThread, Signal, QObject

# Importar las clases del modelo y la vista
from model.model import TranslationCore
from view.view import TranslatorAppView

class WorkerThread(QThread):
    """
    Una subclase de QThread para realizar operaciones de larga duración en segundo plano.
    Delega las operaciones directamente a la instancia de TranslationCore.
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
        Ejecuta la operación especificada, llamando a los métodos del core.
        """
        try:
            if self.operation_type == "translate_and_add":
                self.log_message.emit(f"Iniciando traducción para '{self.data['key']}' en plataforma {self.data['platform'].upper()}...")
                self.progress_updated.emit(0)
                translations = self.core.fetch_translations_from_api(
                    self.data['base_lang'], self.data['original_text'], self.data['platform']
                )
                self.progress_updated.emit(50) # Progreso después de la API

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

class TranslatorAppController(QObject):
    """
    Controlador principal de la aplicación.
    Conecta la vista (UI) con el modelo (lógica de negocio).
    """
    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance
        self.project_path = self._get_initial_script_dir() # Ruta inicial del script

        # Inicializar la vista (UI)
        self.view = TranslatorAppView(self.project_path)
        self.view.show()

        # Inicializar el modelo (lógica de negocio)
        # Pasar el método log de la vista como callback para que el modelo pueda enviar mensajes a la UI
        self.model = TranslationCore(self.project_path, log_callback=self.view.append_log)

        self._connect_signals()
        self._update_ui_state() # Actualizar el estado inicial de la UI y botones

    def _get_initial_script_dir(self):
        """Devuelve el directorio donde se encuentra el script principal al inicio."""
        return os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.realpath(__file__))

    def _connect_signals(self):
        """Conecta las señales de la vista a los slots del controlador."""
        self.view.platform_changed.connect(self._handle_platform_changed)
        self.view.select_folder_requested.connect(self._handle_select_folder)
        self.view.translate_requested.connect(self._handle_translate_request)
        self.view.create_assets_requested.connect(self._handle_create_assets)
        self.view.delete_assets_requested.connect(self._handle_delete_assets)
        self.view.delete_key_requested.connect(self._handle_delete_key)
        self.view.flutter_intl_generate_requested.connect(self._handle_flutter_intl_generate)
        self.view.undo_requested.connect(self._handle_undo_action)
        self.view.show_history_requested.connect(self._handle_show_history)

    def _update_ui_state(self):
        """Actualiza el estado de la UI (botones, etc.) basado en el modelo."""
        self.view.set_ui_enabled(True) # Re-habilitar todos los controles inicialmente
        # Ajustar el estado del botón de deshacer basado en el historial del modelo
        self.view.undo_btn.setEnabled(len(self.model.get_history()) > 0)

    def _handle_platform_changed(self, platform):
        """Maneja el cambio de plataforma en la UI."""
        self.view._update_ui_for_platform(platform) # Actualizar la vista directamente
        self.view.append_log(f"Plataforma cambiada a: {platform.upper()}")
        self._update_ui_state() # Re-evaluar el estado de los botones

    def _handle_select_folder(self):
        """Maneja la solicitud de selección de carpeta."""
        dialog = QFileDialog(self.view)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        
        selected_dir = dialog.getExistingDirectory(self.view, "Seleccionar Carpeta del Proyecto", self.project_path)
        
        if selected_dir and selected_dir != self.project_path:
            self.project_path = selected_dir
            self.view.update_project_path_display(self.project_path)
            self.model.set_project_path(self.project_path) # Notificar al modelo del cambio de ruta
            self.view.append_log(f"Carpeta del proyecto seleccionada: {self.project_path}")
            self._update_ui_state()
        elif selected_dir == self.project_path:
            self.view.append_log("La carpeta seleccionada ya es la carpeta del proyecto actual.")
        else:
            self.view.append_log("Selección de carpeta de proyecto cancelada.")

    def _handle_translate_request(self, base_lang, original_text, key, desc, platform):
        """Maneja la solicitud de traducción y adición de etiqueta."""
        if not all([base_lang, original_text, key]):
            self.view.append_log("⚠️ Por favor, completa todos los campos requeridos (Idioma base, Texto original, Nombre de la etiqueta/string).")
            return

        existing_key_files = self.model.check_key_existence(key, platform)

        if existing_key_files:
            msg = (f"⚠️ La clave/string '{key}' ya existe en las siguientes ubicaciones y no será sobrescrita:\n"
                   + "\n".join(existing_key_files)
                   + "\n\nLa traducción continuará para las ubicaciones donde la clave/string no existe.")
            self.view.show_info_message("Clave/String existente en algunas ubicaciones", msg)

        self.view.set_ui_enabled(False)
        self.view.update_progress_bar(0)
        self.view.set_progress_bar_format("Traduciendo y agregando: %p%")

        self.worker_thread = WorkerThread(
            operation_type="translate_and_add",
            core_instance=self.model,
            data={
                'base_lang': base_lang,
                'original_text': original_text,
                'key': key,
                'desc': desc,
                'existing_key_files': existing_key_files,
                'platform': platform
            }
        )
        self.worker_thread.progress_updated.connect(self.view.update_progress_bar)
        self.worker_thread.log_message.connect(self.view.append_log)
        self.worker_thread.operation_finished.connect(self._on_worker_finished)
        self.worker_thread.error_occurred.connect(self._on_worker_error)
        self.worker_thread.start()

    def _handle_create_assets(self, platform):
        """Maneja la solicitud de creación de archivos/carpetas de idioma."""
        self.view.set_ui_enabled(False)
        self.view.update_progress_bar(0)
        self.view.set_progress_bar_format("Creando archivos/carpetas: %p%")
        
        if platform == "flutter":
            self.model.create_flutter_language_files()
        elif platform == "kotlin":
            self.model.create_kotlin_language_folders()
        
        self.view.update_progress_bar(100)
        self.view.update_progress_bar(0) # Reset
        self._update_ui_state()

    def _handle_delete_assets(self, platform):
        """Maneja la solicitud de eliminación de archivos/carpetas de idioma."""
        # La confirmación ya se hizo en la vista (_confirm_delete_assets)
        self.view.set_ui_enabled(False)
        self.view.update_progress_bar(0)
        self.view.set_progress_bar_format("Eliminando archivos/carpetas: %p%")

        if platform == "flutter":
            self.model.delete_flutter_language_files()
        elif platform == "kotlin":
            self.model.delete_kotlin_language_folders()
        
        self.view.update_progress_bar(100)
        self.view.update_progress_bar(0) # Reset
        self._update_ui_state()

    def _handle_delete_key(self, key, platform):
        """Maneja la solicitud de eliminación de una clave/string."""
        self.view.set_ui_enabled(False)
        self.view.update_progress_bar(0)
        self.view.set_progress_bar_format("Eliminando clave/string: %p%")

        self.worker_thread = WorkerThread(
            operation_type="delete_key",
            core_instance=self.model,
            data={'key': key, 'platform': platform}
        )
        self.worker_thread.progress_updated.connect(self.view.update_progress_bar)
        self.worker_thread.log_message.connect(self.view.append_log)
        self.worker_thread.operation_finished.connect(self._on_worker_finished)
        self.worker_thread.error_occurred.connect(self._on_worker_error)
        self.worker_thread.start()

    def _handle_flutter_intl_generate(self):
        """Maneja la solicitud de ejecutar 'dart run intl_utils:generate'."""
        self.view.append_log("Iniciando comando 'dart run intl_utils:generate'...")
        self.view.set_ui_enabled(False)
        self.view.update_progress_bar(0)
        self.view.set_progress_bar_format("Ejecutando comando: %p%")

        self.worker_thread = WorkerThread(
            operation_type="run_flutter_intl_generate",
            core_instance=self.model,
            data={}
        )
        self.worker_thread.progress_updated.connect(self.view.update_progress_bar)
        self.worker_thread.log_message.connect(self.view.append_log)
        self.worker_thread.command_output.connect(self.view.append_log)
        self.worker_thread.operation_finished.connect(self._on_worker_finished)
        self.worker_thread.error_occurred.connect(self._on_worker_error)
        self.worker_thread.start()

    def _handle_undo_action(self):
        """Maneja la solicitud de deshacer la última acción."""
        last_action = self.model.get_history()[-1] if self.model.get_history() else None

        if not last_action:
            self.view.append_log("⚠️ No hay acciones en el historial para deshacer.")
            self._update_ui_state() # Asegurarse de que el botón esté deshabilitado
            return

        action_type = last_action['type']
        data = last_action['data']
        platform = last_action['platform']

        self.view.append_log(f"Intentando deshacer la acción: {action_type} en {platform.upper()}...")
        self.view.set_ui_enabled(False)
        self.view.update_progress_bar(0)
        self.view.set_progress_bar_format(f"Deshaciendo acción ({platform.upper()}): %p%")

        try:
            if action_type == 'add_key':
                key_to_delete = data['key']
                self.model.undo_delete_key_action(key_to_delete, platform)
                self.model.pop_last_history_entry()
                self.view.append_log(f"✅ Acción 'add_key' deshecha para '{key_to_delete}' en {platform.upper()}.")

            elif action_type == 'delete_key':
                key_to_restore = data['key']
                deleted_content = data['deleted_content_per_file']
                self.model.undo_add_key_action(key_to_restore, deleted_content, platform)
                self.model.pop_last_history_entry()
                self.view.append_log(f"✅ Acción 'delete_key' deshecha para '{key_to_restore}' en {platform.upper()}.")

            else:
                self.view.append_log(f"⚠️ Tipo de acción '{action_type}' no soportado para deshacer.")
                self.view.show_info_message("Deshacer", "Tipo de acción no soportado para deshacer.")

        except Exception as e:
            self.view.append_log(f"❌ Error al deshacer la acción: {e}")
            self.view.show_critical_message("Error al Deshacer", f"Ocurrió un error al intentar deshacer: {e}")
        finally:
            self.view.update_progress_bar(0)
            self._update_ui_state() # Re-habilitar UI y actualizar estado del botón deshacer

    def _handle_show_history(self):
        """Maneja la solicitud de mostrar el historial."""
        history_data = self.model.get_history()
        self.view.show_history_dialog(history_data)

    def _on_worker_finished(self, result_data):
        """Callback cuando un WorkerThread termina exitosamente."""
        self.view.append_log(f"Operación '{result_data.get('type', 'desconocida')}' finalizada para {result_data.get('platform', 'desconocida').upper()}.")
        self.view.update_progress_bar(0)
        self._update_ui_state() # Re-habilitar UI y actualizar estado del botón deshacer

    def _on_worker_error(self, message):
        """Callback cuando un WorkerThread reporta un error."""
        self.view.append_log(message)
        self.view.show_critical_message("Error de Operación", message)
        self.view.update_progress_bar(0)
        self._update_ui_state() # Re-habilitar UI y actualizar estado del botón deshacer

