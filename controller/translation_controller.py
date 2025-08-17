# controller/translation_controller.py
import os
import sys
from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtWidgets import QFileDialog
from view.translation_view import TranslatorAppView
from .worker import TranslationWorker

class TranslatorAppController(QObject):
    """
    Controlador principal. Orquesta UI y worker.
    Nunca toca la UI desde hilos secundarios; toda interacción va por señales queued.
    """

    # Señal de logging GUI-safe
    log_signal = Signal(str)

    # Señales -> Worker (commands)
    sig_translate_and_add = Signal(dict)
    sig_delete_key = Signal(dict)
    sig_flutter_generate = Signal()
    sig_create_assets = Signal(str)
    sig_delete_assets = Signal(str)
    sig_get_history = Signal()
    sig_undo_last = Signal(dict)
    sig_set_project_path = Signal(str)

    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance

        # Ruta del proyecto (del script principal)
        self.project_path = os.path.dirname(os.path.abspath(sys.argv[0]))

        # Banderas internas para coordinar acciones que dependen del historial
        self._pending_show_history = False
        self._pending_undo = False

        # Vista
        self.view = TranslatorAppView(self.project_path)
        self.view.show()

        # Conectar log_signal a la vista (thread-safe)
        self.log_signal.connect(self.view.append_log, Qt.QueuedConnection)

        # Hilo + Worker
        self.thread = QThread(self)
        self.worker = TranslationWorker(self.project_path)
        self.worker.moveToThread(self.thread)

        # Al iniciar el hilo, el worker crea el core
        self.thread.started.connect(self.worker.on_start)

        # Worker -> Vista / Controlador
        self.worker.progress_updated.connect(self.view.update_progress_bar, Qt.QueuedConnection)
        self.worker.log_message.connect(self.view.append_log, Qt.QueuedConnection)
        self.worker.operation_finished.connect(self._on_worker_finished, Qt.QueuedConnection)
        self.worker.error_occurred.connect(self._on_worker_error, Qt.QueuedConnection)
        self.worker.command_output.connect(self.view.append_log, Qt.QueuedConnection)
        self.worker.history_ready.connect(self._on_history_ready, Qt.QueuedConnection)

        # Controlador -> Worker (commands)
        self.sig_translate_and_add.connect(self.worker.do_translate_and_add, Qt.QueuedConnection)
        self.sig_delete_key.connect(self.worker.do_delete_key, Qt.QueuedConnection)
        self.sig_flutter_generate.connect(self.worker.do_flutter_generate, Qt.QueuedConnection)
        self.sig_create_assets.connect(self.worker.do_create_assets, Qt.QueuedConnection)
        self.sig_delete_assets.connect(self.worker.do_delete_assets, Qt.QueuedConnection)
        self.sig_get_history.connect(self.worker.do_get_history, Qt.QueuedConnection)
        self.sig_undo_last.connect(self.worker.do_undo_last, Qt.QueuedConnection)
        self.sig_set_project_path.connect(self.worker.do_set_project_path, Qt.QueuedConnection)

        # Señales desde la vista
        self._connect_view_signals()

        # Estado inicial
        self._update_ui_state()

        # Arrancar hilo
        self.thread.start()

        # Apagado limpio
        self.app.aboutToQuit.connect(self._shutdown)

    # ================= Conexión de vista =================

    def _connect_view_signals(self):
        self.view.platform_changed.connect(self._handle_platform_changed)
        self.view.select_folder_requested.connect(self._handle_select_folder)
        self.view.translate_requested.connect(self._handle_translate_request)
        self.view.create_assets_requested.connect(self._handle_create_assets)
        self.view.delete_assets_requested.connect(self._handle_delete_assets)
        self.view.delete_key_requested.connect(self._handle_delete_key)
        self.view.flutter_intl_generate_requested.connect(self._handle_flutter_intl_generate)
        self.view.undo_requested.connect(self._handle_undo_action)
        self.view.show_history_requested.connect(self._handle_show_history)
        self.view.navigation_selected.connect(self._handle_navigation_selection)

    # ================= Utilidades =================

    def _update_ui_state(self):
        # No bloqueamos: la UI se habilita; el progreso lo controla el worker mediante señales
        self.view.set_ui_enabled(True)
        # Consultar historial para habilitar/deshabilitar Undo
        self.sig_get_history.emit()

    # ================= Handlers de Vista =================

    def _handle_platform_changed(self, platform: str):
        self.view._update_ui_for_platform(platform)
        self.view.append_log(f"Plataforma cambiada a: {platform.upper()}")
        self._update_ui_state()

    def _handle_select_folder(self):
        dialog = QFileDialog(self.view)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        selected_dir = dialog.getExistingDirectory(self.view, "Seleccionar Carpeta del Proyecto", self.project_path)

        if selected_dir and selected_dir != self.project_path:
            self.project_path = selected_dir
            self.view.update_project_path_display(self.project_path)
            self.view.append_log(f"Carpeta del proyecto seleccionada: {self.project_path}")
            # Avisar al worker que actualice el core
            self.sig_set_project_path.emit(self.project_path)
            self._update_ui_state()
        elif selected_dir == self.project_path:
            self.view.append_log("La carpeta seleccionada ya es la carpeta del proyecto actual.")
        else:
            self.view.append_log("Selección de carpeta de proyecto cancelada.")

    def _handle_translate_request(self, base_lang, original_text, key, desc, platform):
        if not all([base_lang, original_text, key]):
            self.view.append_log("⚠️ Completa idioma base, texto original y nombre de etiqueta/string.")
            return

        self.view.set_ui_enabled(False)
        self.view.update_progress_bar(0)
        self.view.set_progress_bar_format("Traduciendo y agregando: %p%")

        payload = {
            'base_lang': base_lang,
            'original_text': original_text,
            'key': key,
            'desc': desc,
            'existing_key_files': [],  # opcional: mantener compatibilidad con tu core
            'platform': platform
        }
        self.sig_translate_and_add.emit(payload)

    def _handle_create_assets(self, platform):
        self.view.set_ui_enabled(False)
        self.view.update_progress_bar(0)
        self.view.set_progress_bar_format("Creando archivos/carpetas: %p%")
        self.sig_create_assets.emit(platform)

    def _handle_delete_assets(self, platform):
        self.view.set_ui_enabled(False)
        self.view.update_progress_bar(0)
        self.view.set_progress_bar_format("Eliminando archivos/carpetas: %p%")
        self.sig_delete_assets.emit(platform)

    def _handle_delete_key(self, key, platform):
        self.view.set_ui_enabled(False)
        self.view.update_progress_bar(0)
        self.view.set_progress_bar_format("Eliminando clave/string: %p%")
        self.sig_delete_key.emit({'key': key, 'platform': platform})

    def _handle_flutter_intl_generate(self):
        self.view.append_log("Iniciando comando 'dart run intl_utils:generate'...")
        self.view.set_ui_enabled(False)
        self.view.update_progress_bar(0)
        self.view.set_progress_bar_format("Ejecutando comando: %p%")
        self.sig_flutter_generate.emit()

    def _handle_undo_action(self):
        # Marca que el próximo historial que llegue será para deshacer
        self._pending_undo = True
        self.sig_get_history.emit()

    def _handle_show_history(self):
        # Marca que el próximo historial que llegue será para mostrar
        self._pending_show_history = True
        self.sig_get_history.emit()

    def _handle_navigation_selection(self, item_text):
        self.view.append_log(f"Navegación seleccionada: {item_text}")
        # Si tu vista usa stacked_widget, probablemente ya lo maneja internamente.

    # ================= Callbacks de Worker =================

    @Slot(dict)
    def _on_worker_finished(self, result_data):
        t = result_data.get('type', 'desconocida')
        p = result_data.get('platform', 'desconocida')
        p = p.upper() if isinstance(p, str) else str(p)
        self.view.append_log(f"Operación '{t}' finalizada para {p}.")
        self.view.update_progress_bar(0)
        self._update_ui_state()

    @Slot(str)
    def _on_worker_error(self, message):
        self.view.append_log(message)
        self.view.show_critical_message("Error de Operación", message)
        self.view.update_progress_bar(0)
        self._update_ui_state()

    @Slot(list)
    def _on_history_ready(self, history_data):
        # Habilita/Deshabilita Undo según historial
        has_history = bool(history_data)
        self.view.undo_btn.setEnabled(has_history)

        # ¿Debemos mostrar historial?
        if self._pending_show_history:
            self._pending_show_history = False
            self.view.show_history_dialog(history_data)

        # ¿Debemos deshacer la última acción?
        if self._pending_undo:
            self._pending_undo = False
            last_action = history_data[-1] if history_data else None
            if not last_action:
                self.view.append_log("⚠️ No hay acciones en el historial para deshacer.")
                self._update_ui_state()
                return

            action_type = last_action.get('type')
            platform = last_action.get('platform')
            payload = last_action.get('data', {})

            self.view.append_log(f"Intentando deshacer la acción: {action_type} en {platform.upper()}...")
            self.view.set_ui_enabled(False)
            self.view.update_progress_bar(0)
            self.view.set_progress_bar_format(f"Deshaciendo acción ({platform.upper()}): %p%")

            self.sig_undo_last.emit({
                'action_type': action_type,
                'payload': payload,
                'platform': platform
            })

    # ================= Shutdown =================

    def _shutdown(self):
        # Parar el hilo con seguridad
        self.thread.quit()
        self.thread.wait()

    # ================= Logging helper =================

    def thread_safe_log(self, msg: str):
        self.log_signal.emit(msg)
