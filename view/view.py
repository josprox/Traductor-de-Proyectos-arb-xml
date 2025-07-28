import os
from PySide6.QtWidgets import (
    QMainWindow, QPushButton, QWidget, QVBoxLayout,
    QLabel, QLineEdit, QTextEdit, QInputDialog, QMessageBox, QProgressBar,
    QHBoxLayout, QComboBox, QFileDialog, QDialog, QListWidget # Añadido QDialog y QListWidget
)
from PySide6.QtCore import Qt, Signal, QObject
from datetime import datetime # Necesario para mostrar el historial

class TranslatorAppView(QMainWindow):
    """
    Clase que representa la vista (interfaz de usuario) de la aplicación.
    Emite señales para las interacciones del usuario y tiene métodos para actualizar la UI.
    """
    # Señales que la vista emite al controlador
    platform_changed = Signal(str)
    select_folder_requested = Signal()
    translate_requested = Signal(str, str, str, str, str) # base_lang, original_text, key, desc, platform
    create_assets_requested = Signal(str) # platform
    delete_assets_requested = Signal(str) # platform
    delete_key_requested = Signal(str, str) # key, platform
    flutter_intl_generate_requested = Signal()
    undo_requested = Signal()
    show_history_requested = Signal()

    def __init__(self, initial_project_path):
        super().__init__()
        self.setWindowTitle("Traductor ARB/Kotlin - Joss Red")
        self.setMinimumSize(700, 600)
        self._current_platform = "flutter" # Estado inicial, se actualiza con el selector

        self.init_ui(initial_project_path)
        self._update_ui_for_platform(self._current_platform) # Asegurar estado inicial de la UI

    def init_ui(self, initial_project_path):
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
        self.platform_selector.currentIndexChanged.connect(
            lambda index: self.platform_changed.emit(self.platform_selector.itemData(index))
        )
        platform_layout.addWidget(self.platform_selector)
        platform_layout.addStretch()
        main_layout.addLayout(platform_layout)

        # Selector de carpeta de proyecto
        project_path_layout = QHBoxLayout()
        project_path_layout.addWidget(QLabel("Ruta del Proyecto:"))
        self.project_path_display = QLineEdit(initial_project_path)
        self.project_path_display.setReadOnly(True)
        project_path_layout.addWidget(self.project_path_display)
        self.select_folder_btn = QPushButton("Seleccionar Carpeta")
        self.select_folder_btn.clicked.connect(self.select_folder_requested.emit)
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
        self.translate_button.clicked.connect(self._emit_translate_request)
        button_layout.addWidget(self.translate_button)

        self.create_files_btn = QPushButton("Crear Archivos/Carpetas de Idioma")
        self.create_files_btn.clicked.connect(lambda: self.create_assets_requested.emit(self._current_platform))
        button_layout.addWidget(self.create_files_btn)

        self.delete_files_btn = QPushButton("Eliminar Archivos/Carpetas de Idioma")
        self.delete_files_btn.clicked.connect(lambda: self._confirm_delete_assets())
        button_layout.addWidget(self.delete_files_btn)

        self.delete_key_btn = QPushButton("Eliminar Etiqueta/String")
        self.delete_key_btn.clicked.connect(self._prompt_delete_key)
        button_layout.addWidget(self.delete_key_btn)
        main_layout.addLayout(button_layout)
        
        # Botón específico de Flutter Intl Generate
        intl_generate_layout = QHBoxLayout()
        self.flutter_intl_generate_btn = QPushButton("Actualizar Intl de Flutter")
        self.flutter_intl_generate_btn.clicked.connect(self.flutter_intl_generate_requested.emit)
        intl_generate_layout.addWidget(self.flutter_intl_generate_btn)
        intl_generate_layout.addStretch()
        main_layout.addLayout(intl_generate_layout)

        # Botones de Historial y Deshacer
        history_undo_layout = QHBoxLayout()
        self.history_btn = QPushButton("Ver Historial")
        self.history_btn.clicked.connect(self.show_history_requested.emit)
        history_undo_layout.addWidget(self.history_btn)

        self.undo_btn = QPushButton("Deshacer Último Cambio")
        self.undo_btn.clicked.connect(self._confirm_undo_action)
        history_undo_layout.addWidget(self.undo_btn)
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

    def _emit_translate_request(self):
        """Emite la señal de traducción con los datos de los campos de entrada."""
        base_lang = self.base_lang_input.text().strip()
        original_text = self.text_input.text().strip()
        key = self.key_input.text().strip()
        desc = self.desc_input.text().strip() if self._current_platform == "flutter" else "Generado con Joss Red"
        self.translate_requested.emit(base_lang, original_text, key, desc, self._current_platform)

    def _confirm_delete_assets(self):
        """Muestra un diálogo de confirmación antes de emitir la señal de eliminación de assets."""
        msg_box = QMessageBox()
        msg_box.setWindowTitle("Confirmar Eliminación")
        msg_box.setText(f"¿Estás seguro de que quieres eliminar TODOS los archivos/carpetas de idioma para {self._current_platform.upper()}? Esta acción no se puede deshacer fácilmente.")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        reply = msg_box.exec()
        if reply == QMessageBox.Yes:
            self.delete_assets_requested.emit(self._current_platform)

    def _prompt_delete_key(self):
        """Pide al usuario la clave a eliminar y emite la señal."""
        key, ok = QInputDialog.getText(self, "Eliminar clave/string", "Nombre de la etiqueta/string a eliminar:")
        if ok and key:
            self.delete_key_requested.emit(key.strip(), self._current_platform)

    def _confirm_undo_action(self):
        """Muestra un diálogo de confirmación antes de emitir la señal de deshacer."""
        msg_box = QMessageBox()
        msg_box.setWindowTitle("Confirmar Deshacer")
        msg_box.setText("¿Estás seguro de que quieres deshacer la última acción? Esto puede modificar archivos.")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        reply = msg_box.exec()
        if reply == QMessageBox.Yes:
            self.undo_requested.emit()

    # Métodos para que el controlador actualice la vista
    def append_log(self, text):
        """Añade un mensaje a la consola de salida."""
        self.output.append(text)

    def update_progress_bar(self, value):
        """Actualiza el valor de la barra de progreso."""
        self.progress_bar.setValue(value)

    def set_progress_bar_format(self, format_string):
        """Establece el formato del texto de la barra de progreso."""
        self.progress_bar.setFormat(format_string)

    def set_ui_enabled(self, enabled):
        """Habilita o deshabilita todos los botones e inputs principales de la UI."""
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
        
        # El botón de Flutter Intl Generate solo se habilita si la plataforma es Flutter
        self.flutter_intl_generate_btn.setEnabled(enabled and self._current_platform == "flutter")
        self.undo_btn.setEnabled(enabled) # El controlador gestionará si hay historial o no

    def update_project_path_display(self, path):
        """Actualiza el QLineEdit que muestra la ruta del proyecto."""
        self.project_path_display.setText(path)

    def show_info_message(self, title, message):
        """Muestra un cuadro de diálogo de información."""
        QMessageBox.information(self, title, message)

    def show_critical_message(self, title, message):
        """Muestra un cuadro de diálogo de error crítico."""
        QMessageBox.critical(self, title, message)

    def show_history_dialog(self, history_data):
        """
        Muestra el historial de traducciones en un nuevo diálogo.
        """
        history_dialog = QDialog(self)
        history_dialog.setWindowTitle("Historial de Acciones")
        history_dialog.setMinimumSize(600, 400)
        layout = QVBoxLayout()

        history_list_widget = QListWidget()
        if not history_data:
            history_list_widget.addItem("No hay historial disponible.")
        else:
            for entry in reversed(history_data):
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

    def _update_ui_for_platform(self, platform):
        """
        Ajusta la visibilidad y el texto de los elementos de la UI según la plataforma.
        """
        self._current_platform = platform # Actualiza el estado interno de la plataforma
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
        # Asegurar que el estado de los botones se actualice después de cambiar la visibilidad
        self.set_ui_enabled(True) # Se re-habilitarán y el controlador ajustará el estado final
