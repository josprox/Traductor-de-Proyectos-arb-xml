# controller/worker.py
import os
from PySide6.QtCore import QObject, Signal, Slot
from model.translation_model import TranslationCore

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
        except Exception as e:
            self.error_occurred.emit(f"❌ Error inicializando Core: {e}")

    # ============ Utilidades internas ============

    def _thread_safe_log(self, msg: str):
        # El core llama a este callback; nosotros reenviamos como señal (GUI-safe)
        self.log_message.emit(msg)

    # ============ Slots de trabajo ============

    @Slot(dict)
    def do_translate_and_add(self, data):
        try:
            self.log_message.emit(f"Iniciando traducción para '{data['key']}' en {data['platform'].upper()}...")
            self.progress_updated.emit(0)

            translations = self.core.fetch_translations_from_api(
                data['base_lang'], data['original_text'], data['platform']
            )
            self.progress_updated.emit(50)

            self.core.add_translation_entry(
                data['base_lang'], data['original_text'], data['key'],
                data['desc'], translations, data['existing_key_files'], data['platform']
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
            
            # Determinar plataforma
            platform = data['platform']
            if platform == 'auto':
                platform = detected_platform
            
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

            # 2. Traducir cada clave
            total_keys = len(key_values)
            batch_translations = {} # { lang: { key: value } }
            
            # Inicializar los diccionarios de traducciones por idioma
            if platform == "flutter":
                target_langs = self.core.get_flutter_target_languages()
            else:
                target_langs = self.core.get_kotlin_target_languages_for_api()

            for lang in target_langs:
                batch_translations[lang] = {}

            # Traducir clave a clave e ir actualizando el progreso
            for idx, (key, original_text) in enumerate(key_values.items()):
                self.log_message.emit(f"Traduciendo [{idx + 1}/{total_keys}]: '{key}' -> '{original_text[:30]}...'")
                
                # Traduce esta clave a todos los idiomas de destino
                key_translations = self.core.fetch_translations_from_api(base_lang, original_text, platform)
                
                # Guardar las traducciones en nuestra estructura por lote
                for lang, translated_text in key_translations.items():
                    batch_translations[lang][key] = translated_text
                
                # Actualizar el progreso (reservando el 90% para traducción, 10% para guardado final)
                progress = int((idx + 1) / total_keys * 90)
                self.progress_updated.emit(progress)

            # 3. Guardar en lote
            self.log_message.emit("Escribiendo traducciones en los archivos de idioma...")
            self.core.add_translation_batch(base_lang, batch_translations, descriptions, platform)
            
            self.log_message.emit("✅ Proceso de traducción por lote finalizado con éxito.")
            self.operation_finished.emit({'type': 'translate_batch', 'platform': platform})

        except Exception as e:
            self.error_occurred.emit(f"❌ Error en 'translate_batch': {e}")
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
