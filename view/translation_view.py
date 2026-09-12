import os
from PySide6.QtWidgets import (
    QMainWindow, QPushButton, QWidget, QVBoxLayout,
    QLabel, QLineEdit, QTextEdit, QInputDialog, QMessageBox, QProgressBar,
    QHBoxLayout, QComboBox, QFileDialog, QDialog, QListWidget, QStackedWidget,
    QCheckBox, QTreeWidget, QTreeWidgetItem, QFrame, QGridLayout, QHeaderView,
    QSizePolicy, QTabWidget, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QFont
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
    navigation_selected = Signal(str) # Nueva señal para la selección del menú de navegación
    translate_batch_requested = Signal(str, str, str) # content, platform, base_lang
    fix_files_requested = Signal(dict)
    provider_changed = Signal(str)
    save_provider_config_requested = Signal(dict)
    test_ai_connection_requested = Signal(dict)

    def __init__(self, initial_project_path):
        super().__init__()
        self.setWindowTitle("Sistema de Traducción Masiva y Linter ARB/XML - Joss Red")
        self.setMinimumSize(1050, 700)
        self._current_platform = "flutter" # Estado inicial, se actualiza con el selector
        self._provider_config = {
            "active_provider": "argos", "auto_failover": True,
            "argos": {"auto_install": True},
            "local_ai": {"base_url": "http://localhost:11434/v1", "api_key": "", "model": "llama3.2"},
            "cloud_ai": {"base_url": "https://api.deepseek.com/v1", "api_key": "", "model": "deepseek-chat"},
        }

        self.init_ui(initial_project_path)
        self._update_ui_for_platform(self._current_platform) # Asegurar estado inicial de la UI

    def init_ui(self, initial_project_path):
        self.setStyleSheet(self._application_stylesheet())
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_horizontal_layout = QHBoxLayout(central_widget)
        main_horizontal_layout.setContentsMargins(10, 10, 10, 10)
        main_horizontal_layout.setSpacing(12)

        nav_panel = QFrame()
        nav_panel.setObjectName("navigationPanel")
        nav_panel.setFixedWidth(220)
        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(10, 14, 10, 12)
        brand = QLabel("<span style='font-size:22px'>◆</span>  <b style='font-size:17px'>JOSS RED</b>")
        brand.setObjectName("brand")
        nav_layout.addWidget(brand)
        subtitle = QLabel("LOCALIZATION STUDIO")
        subtitle.setObjectName("brandSubtitle")
        nav_layout.addWidget(subtitle)
        nav_layout.addSpacing(14)
        self.navbar_list_widget = QListWidget()
        self.navbar_list_widget.setObjectName("navigation")
        self.navbar_list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.navbar_list_widget.addItem("🌐  Traductor")
        self.navbar_list_widget.addItem("📦  Modo Lote")
        self.navbar_list_widget.addItem("🔧  Corregir Archivos")
        nav_layout.addWidget(self.navbar_list_widget, 1)
        self.provider_status_label = QLabel("●  Motor listo")
        self.provider_status_label.setObjectName("providerStatus")
        nav_layout.addWidget(self.provider_status_label)
        version = QLabel("v2.0  •  ARB / XML")
        version.setObjectName("brandSubtitle")
        nav_layout.addWidget(version)

        right_panel_widget = QWidget()
        right_panel_layout = QVBoxLayout(right_panel_widget)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(8)

        # Cabecera compartida, igual que en la versión instalada.
        header_card = self._make_card()
        header_grid = QGridLayout(header_card)
        header_grid.setContentsMargins(14, 10, 14, 10)
        header_grid.setSpacing(8)
        header_grid.addWidget(QLabel("Motor:"), 0, 0)
        self.provider_selector = QComboBox()
        self.provider_selector.addItem("🖥️  Argos Translate (Local, sin límites)", "argos")
        self.provider_selector.addItem("⚡  Google Translate (Multi-Tier)", "google")
        self.provider_selector.addItem("🤖  IA Local (Ollama / LM Studio)", "local_ai")
        self.provider_selector.addItem("☁️  IA Cloud (OpenAI / DeepSeek / Groq)", "cloud_ai")
        self.provider_selector.addItem("🌍  MyMemory", "mymemory")
        self.provider_selector.currentIndexChanged.connect(
            lambda index: self.provider_changed.emit(self.provider_selector.itemData(index))
        )
        header_grid.addWidget(self.provider_selector, 0, 1)
        self.config_ai_btn = QPushButton("⚙  Configurar Motores")
        self.config_ai_btn.clicked.connect(self._open_ai_config_dialog)
        header_grid.addWidget(self.config_ai_btn, 0, 2)
        header_grid.addWidget(QLabel("Plataforma:"), 0, 3)
        self.platform_selector = QComboBox()
        self.platform_selector.addItem("Flutter (ARB)", "flutter")
        self.platform_selector.addItem("Kotlin (XML)", "kotlin")
        self.platform_selector.currentIndexChanged.connect(
            lambda index: self.platform_changed.emit(self.platform_selector.itemData(index))
        )
        header_grid.addWidget(self.platform_selector, 0, 4)
        header_grid.addWidget(QLabel("Ruta:"), 1, 0)
        self.project_path_display = QLineEdit(initial_project_path)
        self.project_path_display.setReadOnly(True)
        header_grid.addWidget(self.project_path_display, 1, 1, 1, 3)
        self.select_folder_btn = QPushButton("📁  Seleccionar Carpeta")
        self.select_folder_btn.clicked.connect(self.select_folder_requested.emit)
        header_grid.addWidget(self.select_folder_btn, 1, 4)
        header_grid.setColumnStretch(1, 1)
        right_panel_layout.addWidget(header_card)

        self.stacked_widget = QStackedWidget()

        # Traductor
        translator_page_widget = QWidget()
        translator_layout = QVBoxLayout(translator_page_widget)
        translator_layout.setContentsMargins(0, 0, 0, 0)
        translator_layout.setSpacing(8)
        form_card = self._make_card()
        form_layout = QGridLayout(form_card)
        form_layout.setContentsMargins(14, 12, 14, 12)
        form_layout.setSpacing(7)
        form_layout.addWidget(QLabel("Idioma base (ej. 'es', 'en'):"), 0, 0)
        form_layout.addWidget(QLabel("Nombre de la etiqueta / String:"), 0, 1)
        self.base_lang_input = QLineEdit()
        self.base_lang_input.setPlaceholderText("ej. 'es', 'en'")
        form_layout.addWidget(self.base_lang_input, 1, 0)
        self.key_input = QLineEdit()
        form_layout.addWidget(self.key_input, 1, 1)
        form_layout.addWidget(QLabel("Texto original a traducir:"), 2, 0, 1, 2)
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Texto original con o sin variables (ej. 'Hola {name}, bienvenido')")
        form_layout.addWidget(self.text_input, 3, 0, 1, 2)
        self.desc_label = QLabel("Descripción (Flutter - opcional)")
        form_layout.addWidget(self.desc_label, 4, 0, 1, 2)
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Contexto o descripción para traductores (opcional)")
        form_layout.addWidget(self.desc_input, 5, 0, 1, 2)
        form_layout.setColumnStretch(0, 1)
        form_layout.setColumnStretch(1, 2)
        translator_layout.addWidget(form_card)

        self.translate_button = QPushButton("🚀  Traducir y Agregar a Todos los Idiomas")
        self.translate_button.setObjectName("primaryButton")
        self.translate_button.setMinimumHeight(44)
        self.translate_button.clicked.connect(self._emit_translate_request)
        translator_layout.addWidget(self.translate_button)

        actions_card = self._make_card()
        actions_grid = QGridLayout(actions_card)
        actions_grid.setContentsMargins(10, 8, 10, 8)
        actions_grid.setSpacing(7)
        self.create_files_btn = QPushButton("📁  Crear Archivos")
        self.create_files_btn.clicked.connect(lambda: self.create_assets_requested.emit(self._current_platform))
        self.delete_key_btn = QPushButton("🗑️  Eliminar Clave")
        self.delete_key_btn.clicked.connect(self._prompt_delete_key)
        self.flutter_intl_generate_btn = QPushButton("⚡  Intl Generate")
        self.flutter_intl_generate_btn.clicked.connect(self.flutter_intl_generate_requested.emit)
        self.history_btn = QPushButton("📋  Ver Historial")
        self.history_btn.clicked.connect(self.show_history_requested.emit)
        self.undo_btn = QPushButton("↶  Deshacer")
        self.undo_btn.clicked.connect(self._confirm_undo_action)
        self.delete_files_btn = QPushButton("⚠️  Eliminar Todo")
        self.delete_files_btn.clicked.connect(self._confirm_delete_assets)
        for index, button in enumerate((self.create_files_btn, self.delete_key_btn,
                                        self.flutter_intl_generate_btn, self.history_btn,
                                        self.undo_btn, self.delete_files_btn)):
            actions_grid.addWidget(button, index // 3, index % 3)
        translator_layout.addWidget(actions_card)
        translator_layout.addStretch()
        self.stacked_widget.addWidget(translator_page_widget)

        # Modo lote
        batch_translator_page_widget = QWidget()
        batch_layout = QVBoxLayout(batch_translator_page_widget)
        batch_layout.setContentsMargins(0, 0, 0, 0)
        batch_layout.setSpacing(8)
        batch_banner = QLabel(
            "<b>Pega contenido ARB (JSON) o Android (strings.xml).</b> "
            "El sistema deduplica y traduce en paralelo a todos los idiomas configurados."
        )
        batch_banner.setObjectName("banner")
        batch_banner.setWordWrap(True)
        batch_layout.addWidget(batch_banner)
        self.batch_text_input = QTextEdit()
        self.batch_text_input.setFont(QFont("Consolas", 10))
        self.batch_text_input.setPlaceholderText("Pega tu código ARB o XML aquí...")
        batch_layout.addWidget(self.batch_text_input, 1)
        self.batch_platform_selector = QComboBox()
        self.batch_platform_selector.addItem("Flutter (ARB)", "flutter")
        self.batch_platform_selector.addItem("Kotlin/Android (XML)", "kotlin")
        self.batch_platform_selector.hide()
        batch_footer = QHBoxLayout()
        batch_footer.addWidget(QLabel("Idioma base:"))
        self.batch_base_lang_input = QLineEdit()
        self.batch_base_lang_input.setPlaceholderText("Autodetectar o ej. 'en', 'es'")
        self.batch_base_lang_input.setMaximumWidth(190)
        batch_footer.addWidget(self.batch_base_lang_input)
        self.batch_translate_btn = QPushButton("🚀  Procesar y Traducir Lote Masivo")
        self.batch_translate_btn.setObjectName("primaryButton")
        self.batch_translate_btn.setMinimumHeight(42)
        self.batch_translate_btn.clicked.connect(self._emit_translate_batch_request)
        batch_footer.addWidget(self.batch_translate_btn, 1)
        batch_layout.addLayout(batch_footer)
        self.stacked_widget.addWidget(batch_translator_page_widget)

        # Corregir archivos
        fix_page_widget = QWidget()
        fix_layout = QVBoxLayout(fix_page_widget)
        fix_layout.setContentsMargins(0, 0, 0, 0)
        fix_layout.setSpacing(8)
        fix_desc = QLabel(
            "<b>Diagnóstico, Formateo, Linter y Sincronización Automática:</b><br>"
            "&nbsp;&nbsp;• <b>Traducciones faltantes:</b> completa claves sin sobrescribir valores válidos.<br>"
            "&nbsp;&nbsp;• <b>Missing Metadata:</b> genera metadatos <span style='color:#38bdf8'>@clave</span> faltantes.<br>"
            "&nbsp;&nbsp;• <b>Placeholders:</b> conserva variables y genera sus bloques ARB.<br>"
            "&nbsp;&nbsp;• <b>Aislamiento:</b> procesa exclusivamente el formato seleccionado."
        )
        fix_desc.setObjectName("banner")
        fix_desc.setWordWrap(True)
        fix_layout.addWidget(fix_desc)
        fix_controls = self._make_card()
        fix_controls_layout = QHBoxLayout(fix_controls)
        self.sync_missing_cb = QCheckBox("Sincronizar y traducir claves faltantes entre idiomas")
        self.sync_missing_cb.setChecked(True)
        fix_controls_layout.addWidget(self.sync_missing_cb, 1)
        self.cleanup_unexpected_cb = QCheckBox("Respaldar ARB no configurados")
        self.cleanup_unexpected_cb.setChecked(True)
        self.cleanup_unexpected_cb.setToolTip(
            "Mueve intl_*.arb ajenos a la lista Flutter a .joss-red-backup; no los elimina."
        )
        fix_controls_layout.addWidget(self.cleanup_unexpected_cb)
        self.run_fix_btn = QPushButton("🚀  Ejecutar Corrección y Sincronización")
        self.run_fix_btn.setObjectName("primaryButton")
        self.run_fix_btn.clicked.connect(lambda: self.fix_files_requested.emit({
            "platform": self._current_platform,
            "sync_missing": self.sync_missing_cb.isChecked(),
            "cleanup_unexpected": self.cleanup_unexpected_cb.isChecked(),
        }))
        fix_controls_layout.addWidget(self.run_fix_btn)
        fix_layout.addWidget(fix_controls)
        stats = QGridLayout()
        self.stat_files_lbl = self._make_stat("📁 Archivos corregidos", "#60a5fa")
        self.stat_synced_lbl = self._make_stat("🔄 Faltantes sincronizados", "#c084fc")
        self.stat_meta_lbl = self._make_stat("🏷 Metadatos @key añadidos", "#4ade80")
        self.stat_ph_lbl = self._make_stat("🧩 Placeholders generados", "#facc15")
        self.stat_archived_lbl = self._make_stat("📦 ARB no configurados respaldados", "#fb923c")
        stats.addWidget(self.stat_files_lbl, 0, 0)
        stats.addWidget(self.stat_synced_lbl, 0, 1)
        stats.addWidget(self.stat_meta_lbl, 1, 0)
        stats.addWidget(self.stat_ph_lbl, 1, 1)
        stats.addWidget(self.stat_archived_lbl, 2, 0, 1, 2)
        fix_layout.addLayout(stats)
        self.fix_summary_label = QLabel("")
        self.fix_summary_label.hide()
        fix_layout.addWidget(QLabel("<b>Detalle de modificaciones por archivo:</b>"))
        self.fix_report_tree = QTreeWidget()
        self.fix_report_tree.setHeaderLabels(["Archivo / Plataforma", "Modificación aplicada"])
        self.fix_report_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.fix_report_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        fix_layout.addWidget(self.fix_report_tree, 1)
        self.stacked_widget.addWidget(fix_page_widget)

        self.navbar_list_widget.currentRowChanged.connect(self._on_navbar_selection_changed)
        self.navbar_list_widget.setCurrentRow(0)
        right_panel_layout.addWidget(self.stacked_widget, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Progreso: %p%")
        right_panel_layout.addWidget(self.progress_bar)

        console_card = self._make_card()
        console_layout = QVBoxLayout(console_card)
        console_layout.setContentsMargins(10, 6, 10, 8)
        console_layout.setSpacing(3)
        console_layout.addWidget(QLabel("<b>Consola de salida y registros:</b>"))
        self.output = QTextEdit()
        self.output.setFont(QFont("Consolas", 9))
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(120)
        console_layout.addWidget(self.output)
        right_panel_layout.addWidget(console_card)

        main_horizontal_layout.addWidget(nav_panel)
        main_horizontal_layout.addWidget(right_panel_widget, 1)

    @staticmethod
    def _make_card():
        card = QFrame()
        card.setObjectName("card")
        return card

    @staticmethod
    def _make_stat(label, color):
        widget = QLabel(f"{label}: <b style='color:{color}'>0</b>")
        widget.setTextFormat(Qt.RichText)
        widget.setStyleSheet(
            f"background:#1e293b; color:#cbd5e1; border:1px solid {color}; "
            "border-radius:6px; padding:8px 12px;"
        )
        return widget

    @staticmethod
    def _application_stylesheet():
        return """
            QMainWindow, QWidget { background-color: #17191d; color: #e5e7eb; font-family: "Segoe UI"; font-size: 13px; }
            QFrame#card, QLabel#banner { background-color: #1e2227; border: 1px solid #30353d; border-radius: 8px; }
            QLabel#banner { padding: 10px 14px; }
            QFrame#navigationPanel { background-color: #1d2126; border: 1px solid #30353d; border-radius: 12px; }
            QLabel#brand { color: #f8fafc; padding: 4px 8px; }
            QLabel#brandSubtitle { color: #66758a; font-size: 10px; font-weight: 700; letter-spacing: 2px; padding-left: 9px; }
            QLabel#providerStatus { color: #4ade80; background: #17251e; border: 1px solid #244b34; border-radius: 7px; padding: 8px 10px; }
            QListWidget#navigation { background-color: transparent; border: none; padding: 2px; outline: none; }
            QListWidget#navigation::item { color: #aebbd0; min-height: 43px; padding: 7px 10px; margin: 3px 0; border-radius: 7px; }
            QListWidget#navigation::item:hover { background-color: #252b33; color: white; }
            QListWidget#navigation::item:selected { background-color: #2563eb; color: white; border: 1px solid #60a5fa; }
            QLineEdit, QTextEdit, QComboBox, QTreeWidget { background-color: #1d2126; color: #e5e7eb; border: 1px solid #30353d; border-radius: 7px; padding: 7px; selection-background-color: #2563eb; }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid #3b82f6; }
            QComboBox::drop-down { border: none; width: 24px; }
            QPushButton { background-color: #20242a; color: #e5e7eb; border: 1px solid #343a43; border-radius: 7px; padding: 8px 12px; }
            QPushButton:hover { background-color: #2a3038; border-color: #4b5563; }
            QPushButton:disabled { color: #68707d; background-color: #1b1e22; }
            QPushButton#primaryButton { background-color: #2563eb; color: white; border-color: #3b82f6; font-weight: 700; }
            QPushButton#primaryButton:hover { background-color: #1d4ed8; }
            QProgressBar { background-color: #1d2126; border: 1px solid #30353d; border-radius: 5px; min-height: 17px; text-align: center; }
            QProgressBar::chunk { background-color: #2563eb; border-radius: 4px; }
            QTreeWidget::item { padding: 4px; }
            QHeaderView::section { background-color: #252a31; color: #9fb0c8; border: none; border-right: 1px solid #343a43; padding: 7px; font-weight: 700; }
            QCheckBox { spacing: 8px; }
            QCheckBox::indicator { width: 17px; height: 17px; }
            QTabWidget::pane { background:#1e2227; border:1px solid #343a43; border-radius:7px; top:-1px; }
            QTabBar::tab { background:#20242a; color:#94a3b8; padding:9px 16px; border:1px solid #343a43; }
            QTabBar::tab:selected { background:#2563eb; color:white; }
            QScrollBar:vertical { background:#17191d; width:10px; margin:0; }
            QScrollBar::handle:vertical { background:#3b4654; min-height:24px; border-radius:5px; }
            QToolTip { background:#111827; color:white; border:1px solid #3b82f6; padding:5px; }
        """

    def _on_navbar_selection_changed(self, row):
        """
        Maneja el cambio de selección en el menú de navegación y emite una señal.
        """
        item_text = self.navbar_list_widget.item(row).text()
        self.navigation_selected.emit(item_text)
        # También actualiza el stacked widget directamente para la navegación
        self.stacked_widget.setCurrentIndex(row)


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
        self.provider_selector.setEnabled(enabled)
        self.config_ai_btn.setEnabled(enabled)
        self.select_folder_btn.setEnabled(enabled)
        
        # Batch Mode UI elements
        if hasattr(self, 'batch_translate_btn'):
            self.batch_translate_btn.setEnabled(enabled)
        if hasattr(self, 'batch_text_input'):
            self.batch_text_input.setEnabled(enabled)
        if hasattr(self, 'batch_platform_selector'):
            self.batch_platform_selector.setEnabled(enabled)
        if hasattr(self, 'batch_base_lang_input'):
            self.batch_base_lang_input.setEnabled(enabled)
        if hasattr(self, 'run_fix_btn'):
            self.run_fix_btn.setEnabled(enabled)
        if hasattr(self, 'sync_missing_cb'):
            self.sync_missing_cb.setEnabled(enabled)
        if hasattr(self, 'cleanup_unexpected_cb'):
            self.cleanup_unexpected_cb.setEnabled(enabled and self._current_platform == "flutter")

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

    def _open_ai_config_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Centro de Motores de Traducción")
        dialog.setMinimumSize(650, 520)
        layout = QVBoxLayout(dialog)
        heading = QLabel(
            "<b style='font-size:18px'>Configurar motores inteligentes</b><br>"
            "<span style='color:#94a3b8'>Traduce localmente con Argos o conecta Ollama, "
            "LM Studio, OpenAI, DeepSeek, Groq y endpoints compatibles.</span>"
        )
        heading.setWordWrap(True)
        layout.addWidget(heading)
        tabs = QTabWidget()

        def provider_tab(config_key, default_url, default_model, cloud=False):
            page = QWidget()
            form = QVBoxLayout(page)
            form.setContentsMargins(16, 16, 16, 16)
            form.setSpacing(8)
            config = self._provider_config.get(config_key, {})
            badge = QLabel(
                "☁️ Proveedor remoto OpenAI-compatible" if cloud
                else "🤖 Servidor local OpenAI-compatible"
            )
            badge.setObjectName("banner")
            form.addWidget(badge)
            form.addWidget(QLabel("Endpoint base"))
            url = QLineEdit(config.get("base_url", default_url))
            url.setPlaceholderText(default_url)
            form.addWidget(url)
            form.addWidget(QLabel("Modelo"))
            model = QLineEdit(config.get("model", default_model))
            model.setPlaceholderText(default_model)
            form.addWidget(model)
            form.addWidget(QLabel("API Key" + ("" if cloud else " (opcional)")))
            api_key = QLineEdit(config.get("api_key", ""))
            api_key.setEchoMode(QLineEdit.Password)
            api_key.setPlaceholderText("sk-..." if cloud else "No requerida normalmente")
            form.addWidget(api_key)
            test = QPushButton("🔍  Probar conexión y traducción")
            test.clicked.connect(lambda: self.test_ai_connection_requested.emit({
                "type": config_key, "base_url": url.text().strip(),
                "model": model.text().strip(), "api_key": api_key.text().strip(),
            }))
            form.addWidget(test)
            form.addStretch()
            return page, url, model, api_key

        argos_page = QWidget()
        argos_layout = QVBoxLayout(argos_page)
        argos_layout.setContentsMargins(16, 16, 16, 16)
        argos_layout.setSpacing(10)
        argos_badge = QLabel("🖥️ Motor neuronal local • sin API • sin errores 429")
        argos_badge.setObjectName("banner")
        argos_layout.addWidget(argos_badge)
        argos_description = QLabel(
            "Argos descarga los modelos de idioma una sola vez y después traduce completamente "
            "sin conexión. La primera traducción de cada idioma puede tardar mientras se prepara "
            "el modelo; las siguientes reutilizan el modelo instalado."
        )
        argos_description.setWordWrap(True)
        argos_layout.addWidget(argos_description)
        argos_auto_install = QCheckBox("Descargar automáticamente los modelos que falten")
        argos_auto_install.setChecked(
            self._provider_config.get("argos", {}).get("auto_install", True)
        )
        argos_layout.addWidget(argos_auto_install)
        argos_storage = QLabel(
            "Los modelos se guardan en el perfil local del usuario. Para idiomas sin modelo "
            "disponible se utilizará el motor de respaldo configurado."
        )
        argos_storage.setWordWrap(True)
        argos_storage.setStyleSheet("color:#94a3b8;")
        argos_layout.addWidget(argos_storage)
        argos_layout.addStretch()

        local_page, local_url, local_model, local_key = provider_tab(
            "local_ai", "http://localhost:11434/v1", "llama3.2"
        )
        cloud_page, cloud_url, cloud_model, cloud_key = provider_tab(
            "cloud_ai", "https://api.deepseek.com/v1", "deepseek-chat", True
        )
        tabs.addTab(argos_page, "🖥️  Argos Local")
        tabs.addTab(local_page, "🤖  IA Local")
        tabs.addTab(cloud_page, "☁️  IA Cloud")
        layout.addWidget(tabs, 1)
        failover = QCheckBox(
            "Failover automático: proveedor seleccionado → Argos → Google → MyMemory"
        )
        failover.setChecked(self._provider_config.get("auto_failover", True))
        layout.addWidget(failover)
        note = QLabel(
            "🔒 La configuración se guarda localmente en translation_config.json. "
            "No se envían credenciales salvo al endpoint configurado."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#94a3b8; padding:6px;")
        layout.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(dialog.reject)
        save = QPushButton("Guardar configuración")
        save.setObjectName("primaryButton")

        def save_config():
            self.save_provider_config_requested.emit({
                "active_provider": self.provider_selector.currentData(),
                "auto_failover": failover.isChecked(),
                "argos": {"auto_install": argos_auto_install.isChecked()},
                "local_ai": {"base_url": local_url.text(), "model": local_model.text(), "api_key": local_key.text()},
                "cloud_ai": {"base_url": cloud_url.text(), "model": cloud_model.text(), "api_key": cloud_key.text()},
            })
            dialog.accept()

        save.clicked.connect(save_config)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        dialog.exec()

    def update_provider_config_ui(self, config):
        self._provider_config = config
        active = config.get("active_provider", "argos")
        index = self.provider_selector.findData(active)
        if index >= 0:
            self.provider_selector.blockSignals(True)
            self.provider_selector.setCurrentIndex(index)
            self.provider_selector.blockSignals(False)
        names = {
            "argos": "Argos Local", "google": "Google Multi-Tier", "local_ai": "IA Local",
            "cloud_ai": "IA Cloud", "mymemory": "MyMemory",
        }
        fallback = " + failover" if config.get("auto_failover", True) else ""
        self.provider_status_label.setText(f"●  {names.get(active, active)}{fallback}")

    def show_ai_test_result(self, result):
        if result.get("success"):
            QMessageBox.information(self, "Prueba de conexión", result.get("message", "Conexión correcta."))
        else:
            QMessageBox.warning(self, "Prueba de conexión", result.get("message", "No fue posible conectar."))

    def display_fix_files_report(self, result):
        self.stat_files_lbl.setText(f"📁 Archivos corregidos: <b style='color:#60a5fa'>{result.get('files_fixed', 0)}</b>")
        self.stat_synced_lbl.setText(f"🔄 Faltantes sincronizados: <b style='color:#c084fc'>{result.get('missing_synced', 0)}</b>")
        self.stat_meta_lbl.setText(f"🏷 Metadatos @key añadidos: <b style='color:#4ade80'>{result.get('metadata_added', 0)}</b>")
        self.stat_ph_lbl.setText(f"🧩 Placeholders generados: <b style='color:#facc15'>{result.get('placeholders_added', 0)}</b>")
        self.stat_archived_lbl.setText(f"📦 ARB no configurados respaldados: <b style='color:#fb923c'>{result.get('unexpected_archived', 0)}</b>")
        self.fix_report_tree.clear()
        for detail in result.get('details', []):
            parent = QTreeWidgetItem([
                f"{detail.get('file', '')} / {detail.get('platform', '')}", ""
            ])
            for change in detail.get('changes', []):
                parent.addChild(QTreeWidgetItem(["", str(change)]))
            self.fix_report_tree.addTopLevelItem(parent)
            parent.setExpanded(True)

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
                elif action_type == 'batch_add_keys':
                    affected = data.get('affected_files', {})
                    num_files = len(affected)
                    # Count total keys in the first file as a representative
                    first_file = next(iter(affected.values())) if affected else {}
                    num_keys = len(first_file)
                    display_text += f" - Traducción Lote: {num_keys} keys en {num_files} archivos"

                history_list_widget.addItem(display_text)

        layout.addWidget(history_list_widget)
        history_dialog.setLayout(layout)
        history_dialog.exec()

    def _update_ui_for_platform(self, platform):
        """
        Ajusta la visibilidad y el texto de los elementos de la UI según la plataforma.
        """
        self._current_platform = platform # Actualiza el estado interno de la plataforma
        if hasattr(self, 'cleanup_unexpected_cb'):
            self.cleanup_unexpected_cb.setEnabled(platform == "flutter")
        if hasattr(self, 'batch_platform_selector'):
            batch_index = self.batch_platform_selector.findData(platform)
            if batch_index >= 0:
                self.batch_platform_selector.setCurrentIndex(batch_index)
        if platform == "flutter":
            self.desc_label.show()
            self.desc_input.show()
            self.key_input.setPlaceholderText("Nombre de la etiqueta (ej. 'similarToTitle')")
            self.translate_button.setText("🚀  Traducir y Agregar a Todos los Idiomas")
            self.create_files_btn.setText("📁  Crear Archivos")
            self.delete_files_btn.setText("⚠️  Eliminar Todo")
            self.delete_key_btn.setText("🗑️  Eliminar Clave")
            self.flutter_intl_generate_btn.show()
        elif platform == "kotlin":
            self.desc_label.hide()
            self.desc_input.hide()
            self.key_input.setPlaceholderText("Nombre del string (ej. 'app_name')")
            self.translate_button.setText("🚀  Traducir y Agregar a Todos los Idiomas")
            self.create_files_btn.setText("📁  Crear Carpetas/XML")
            self.delete_files_btn.setText("⚠️  Eliminar Todo")
            self.delete_key_btn.setText("🗑️  Eliminar String")
            self.flutter_intl_generate_btn.hide()
        # Asegurar que el estado de los botones se actualice después de cambiar la visibilidad
        self.set_ui_enabled(True) # Se re-habilitarán y el controlador ajustará el estado final

    def _emit_translate_batch_request(self):
        """Emite la señal de traducción por lote."""
        content = self.batch_text_input.toPlainText().strip()
        platform = self.batch_platform_selector.currentData()
        base_lang = self.batch_base_lang_input.text().strip()
        if not content:
            self.append_log("⚠️ Por favor pega algún contenido JSON/XML para traducir.")
            return
        self.translate_batch_requested.emit(content, platform, base_lang)
