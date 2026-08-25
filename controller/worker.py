# controller/worker.py
import os
import time
from PySide6.QtCore import QObject, Signal, Slot
from model.translation_model import TranslationCore
from model.providers import OpenAICompatibleProvider

class TranslationWorker(QObject):
    """
    Vive en un QThread. Crea y usa TranslationCore DENTRO del hilo del worker.
    Expone slots para que el controlador le mande trabajo por señales.
    """
    # Señales hacia la GUI / Controlador
    progress_updated = Signal(int)
    log_message = Signal(str)
    operation_finished = Signal(dict)
    error_occurred = Signal(str)
    command_output = Signal(str)
    history_ready = Signal(list)
    provider_config_ready = Signal(dict)
    ai_test_result = Signal(dict)

    def __init__(self, project_path: str):
        super().__init__()
        self.project_path = project_path
        self.core = None  # se crea en on_start

    @Slot()
    def on_start(self):
        # Se ejecuta cuando arranca el hilo: aquí nacen objetos Qt del core si los usa.
        try:
            self.core = TranslationCore(self.project_path, log_callback=self._thread_safe_log)
            self._thread_safe_log(f"✅ Core inicializado en: {os.path.abspath(self.project_path)}")
            self.provider_config_ready.emit(self.core.get_provider_config())
        except Exception as e:
            self.error_occurred.emit(f"❌ Error inicializando Core: {e}")

    # ============ Utilidades internas ============

    def _thread_safe_log(self, msg: str):
        # El core llama a este callback; nosotros reenviamos como señal (GUI-safe)
        self.log_message.emit(msg)

    # ============ Slots de trabajo ============

    @Slot(str)
    def do_set_provider(self, provider_name):
        try:
            self.core.set_active_provider(provider_name)
            self.provider_config_ready.emit(self.core.get_provider_config())
        except Exception as e:
            self.error_occurred.emit(f"❌ Error al cambiar de proveedor: {e}")

    @Slot(dict)
    def do_save_provider_config(self, config):
        try:
            self.core.save_provider_config(config)
            self.provider_config_ready.emit(self.core.get_provider_config())
            self._thread_safe_log("✅ Configuración de traductores guardada.")
        except Exception as e:
            self.error_occurred.emit(f"❌ Error al guardar configuración de traductores: {e}")

    @Slot(dict)
    def do_test_ai_connection(self, data):
        try:
            provider = OpenAICompatibleProvider(
                base_url=data.get('base_url', ''), api_key=data.get('api_key', ''),
                model=data.get('model', ''), log_callback=self._thread_safe_log,
            )
            started = time.time()
            translated = provider.translate_single('en', 'es', 'Hello world')
            elapsed = time.time() - started
            if translated and translated != 'Hello world':
                result = {"success": True, "message": f"✅ Conexión correcta ({elapsed:.2f}s): {translated}"}
            else:
                result = {"success": False, "message": "El endpoint respondió sin una traducción válida. Revisa el modelo."}
            self.ai_test_result.emit(result)
        except Exception as e:
            self.ai_test_result.emit({"success": False, "message": f"❌ Error de conexión: {e}"})

    @Slot(dict)
    def do_translate_and_add(self, data):
        try:
            self.log_message.emit(f"Iniciando traducción para '{data['key']}' en {data['platform'].upper()}...")
            self.progress_updated.emit(0)

            platform = data['platform']
            if platform not in ('flutter', 'kotlin'):
                raise ValueError(f"Plataforma no reconocida: {platform!r}")
            existing_key_files = self.core.check_key_existence(data['key'], platform)
            target_count = (
                len(self.core.FLUTTER_LANGUAGE_FILES)
                if platform == 'flutter'
                else len(self.core.KOTLIN_LANGUAGE_FOLDERS)
            )
            translations = {}
            if len(existing_key_files) < target_count:
                translations = self.core.fetch_translations_from_api(
                    data['base_lang'], data['original_text'], platform
                )
            else:
                self.log_message.emit("ℹ️ La clave ya existe en todos los destinos; no se llamó al traductor.")
            self.progress_updated.emit(50)

            self.core.add_translation_entry(
                data['base_lang'], data['original_text'], data['key'],
                data['desc'], translations, existing_key_files, platform
            )
            self.operation_finished.emit({'type': 'translate_and_add', 'platform': data['platform']})
        except Exception as e:
            self.error_occurred.emit(f"❌ Error en 'translate_and_add': {e}")
        finally:
            self.progress_updated.emit(100)

    @Slot(dict)
    def do_delete_key(self, data):
        try:
            self.log_message.emit(f"Iniciando eliminación de '{data['key']}' en {data['platform'].upper()}...")
            self.progress_updated.emit(0)
            self.core.delete_key_entry(data['key'], data['platform'])
            self.operation_finished.emit({'type': 'delete_key', 'platform': data['platform']})
        except Exception as e:
            self.error_occurred.emit(f"❌ Error en 'delete_key': {e}")
        finally:
            self.progress_updated.emit(100)

    @Slot()
    def do_flutter_generate(self):
        try:
            self.progress_updated.emit(0)
            out, rc = self.core.run_flutter_intl_generate()
            self.command_output.emit(out)
            self.operation_finished.emit({'type': 'run_flutter_intl_generate', 'platform': 'flutter'})
        except Exception as e:
            self.error_occurred.emit(f"❌ Error en 'flutter_intl_generate': {e}")
        finally:
            self.progress_updated.emit(100)

    @Slot(str)
    def do_create_assets(self, platform: str):
        try:
            self.progress_updated.emit(0)
            if platform == "flutter":
                self.core.create_flutter_language_files()
            elif platform == "kotlin":
                self.core.create_kotlin_language_folders()
            else:
                self._thread_safe_log(f"⚠️ Plataforma desconocida: {platform}")
            self.operation_finished.emit({'type': 'create_assets', 'platform': platform})
        except Exception as e:
            self.error_occurred.emit(f"❌ Error creando assets ({platform}): {e}")
        finally:
            self.progress_updated.emit(100)

    @Slot(str)
    def do_delete_assets(self, platform: str):
        try:
            self.progress_updated.emit(0)
            if platform == "flutter":
                self.core.delete_flutter_language_files()
            elif platform == "kotlin":
                self.core.delete_kotlin_language_folders()
            else:
                self._thread_safe_log(f"⚠️ Plataforma desconocida: {platform}")
            self.operation_finished.emit({'type': 'delete_assets', 'platform': platform})
        except Exception as e:
            self.error_occurred.emit(f"❌ Error eliminando assets ({platform}): {e}")
        finally:
            self.progress_updated.emit(100)

    @Slot()
    def do_get_history(self):
        try:
            hist = self.core.get_history()
            self.history_ready.emit(hist)
        except Exception as e:
            self.error_occurred.emit(f"❌ Error obteniendo historial: {e}")

    @Slot(dict)
    def do_undo_last(self, data):
        """
        data esperado:
        {
          'action_type': str,
          'payload': {...},
          'platform': str
        }
        """
        try:
            self.progress_updated.emit(0)
            action_type = data.get('action_type')
            payload = data.get('payload') or {}
            platform = data.get('platform', 'desconocida')

            if action_type == 'add_key':
                key_to_delete = payload['key']
                self.core.undo_delete_key_action(key_to_delete, platform)
                self.core.pop_last_history_entry()
                self._thread_safe_log(f"✅ Acción 'add_key' deshecha para '{key_to_delete}' en {platform.upper()}.")
            elif action_type == 'delete_key':
                key_to_restore = payload['key']
                deleted_content = payload['deleted_content_per_file']
                self.core.undo_add_key_action(key_to_restore, deleted_content, platform)
                self.core.pop_last_history_entry()
                self._thread_safe_log(f"✅ Acción 'delete_key' deshecha para '{key_to_restore}' en {platform.upper()}.")
            elif action_type == 'batch_add_keys':
                self.core.undo_batch_add_keys_action(payload, platform)
                self.core.pop_last_history_entry()
                self._thread_safe_log(f"✅ Lote de traducciones deshecho en {platform.upper()}.")
            else:
                self._thread_safe_log(f"⚠️ Tipo de acción '{action_type}' no soportado para deshacer.")

            self.operation_finished.emit({'type': 'undo', 'platform': platform})
        except Exception as e:
            self.error_occurred.emit(f"❌ Error deshaciendo acción: {e}")
        finally:
            self.progress_updated.emit(100)

    @Slot(dict)
    def do_translate_batch(self, data):
        """
        data esperado:
        {
            'content': str,
            'platform': str,
            'base_lang': str
        }
        """
        try:
            self.log_message.emit("Iniciando procesamiento de lote...")
            self.progress_updated.emit(0)

            # 1. Parsear el contenido
            detected_platform, detected_base, key_values, descriptions = self.core.parse_batch_content(data['content'])
            
            # Resolver el formato una sola vez. Una selección manual que no
            # coincide con el contenido es un error: continuar mezclaría el
            # parser de un formato con los idiomas/escritor del otro.
            requested_platform = data['platform']
            platform = detected_platform if requested_platform == 'auto' else requested_platform
            if platform not in ('flutter', 'kotlin'):
                raise ValueError(f"Plataforma no reconocida: {platform!r}")
            if requested_platform != 'auto' and platform != detected_platform:
                raise ValueError(
                    f"El contenido es {detected_platform.upper()}, pero se seleccionó "
                    f"{platform.upper()}. Corrige la selección antes de continuar."
                )
            
            # Determinar idioma base
            base_lang = data['base_lang']
            if not base_lang:
                base_lang = detected_base
            if not base_lang:
                base_lang = 'en' # fallback por defecto
            
            self.log_message.emit(f"✓ Formato detectado: {platform.upper()}, Idioma Base: {base_lang}")
            self.log_message.emit(f"✓ Claves encontradas para procesar: {len(key_values)}")

            if not key_values:
                raise ValueError("No se encontraron claves válidas para traducir en el contenido proporcionado.")

            # 2. Deduplicar textos y traducirlos en paralelo.
            batch_translations = self.core.translate_batch_optimized(
                base_lang,
                key_values,
                platform,
                progress_callback=lambda value: self.progress_updated.emit(value),
            )

            # 3. Guardar en lote
            self.log_message.emit("Escribiendo traducciones en los archivos de idioma...")
            self.core.add_translation_batch(base_lang, batch_translations, descriptions, platform)
            
            self.log_message.emit("✅ Proceso de traducción por lote finalizado con éxito.")
            self.operation_finished.emit({'type': 'translate_batch', 'platform': platform})

        except Exception as e:
            self.error_occurred.emit(f"❌ Error en 'translate_batch': {e}")
        finally:
            self.progress_updated.emit(100)

    @Slot(dict)
    def do_fix_files(self, data):
        """Corrige exclusivamente los archivos del formato seleccionado."""
        try:
            platform = data.get('platform')
            if platform not in ('flutter', 'kotlin'):
                raise ValueError("Selecciona explícitamente Flutter (ARB) o Kotlin (XML).")
            sync_missing = bool(data.get('sync_missing', True))
            cleanup_unexpected = bool(data.get('cleanup_unexpected', True))
            self.progress_updated.emit(0)
            result = self.core.fix_and_format_project_files(
                platform=platform,
                sync_missing=sync_missing,
                cleanup_unexpected=cleanup_unexpected,
                progress_callback=self.progress_updated.emit,
            )
            self.operation_finished.emit({
                'type': 'fix_files',
                'platform': platform,
                **result,
            })
        except Exception as e:
            self.error_occurred.emit(f"❌ Error en 'fix_files': {e}")
        finally:
            self.progress_updated.emit(100)

    @Slot(str)
    def do_set_project_path(self, new_path: str):
        try:
            self.project_path = new_path
            if self.core:
                self.core.set_project_path(new_path)
            self._thread_safe_log(f"📁 Carpeta del proyecto actualizada en el core: {new_path}")
            self.operation_finished.emit({'type': 'set_project_path', 'platform': 'n/a'})
        except Exception as e:
            self.error_occurred.emit(f"❌ Error actualizando project_path: {e}")
