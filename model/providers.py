import html
import json
import os
import re
import sys
import threading
import time
import types

import requests
from requests.adapters import HTTPAdapter


MAX_RETRY_ATTEMPTS = 3


def normalize_language_code(code):
    """Convierte variantes usadas por Flutter/Android a códigos de los modelos."""
    normalized = (code or "").strip().replace("_", "-")
    aliases = {
        "in": "id", "iw": "he", "fil": "tl",
        "no": "nb", "nb-no": "nb",
        "zh-cn": "zh", "zh-tw": "zh", "zh-hans": "zh", "zh-hant": "zh",
    }
    lowered = normalized.casefold()
    if lowered in aliases:
        return aliases[lowered]
    return lowered.split("-r", 1)[0].split("-", 1)[0]


class BaseTranslationProvider:
    display_name = "Proveedor"

    def __init__(self, session=None, log_callback=None):
        self.session = session or self._create_session()
        self.log_callback = log_callback or (lambda _message: None)

    @staticmethod
    def _create_session():
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({"User-Agent": "JossRedTranslator/2.0"})
        return session

    def log(self, message):
        self.log_callback(message)

    def is_available(self):
        return True

    def translate_single(self, base_lang, target_lang, protected_text):
        raise NotImplementedError

    def translate_chunk(self, base_lang, target_lang, chunk):
        results = {}
        for item_id, protected_text, _placeholders in chunk:
            translated = self.translate_single(base_lang, target_lang, protected_text)
            if translated:
                results[item_id] = translated
        return results


class ArgosTranslateProvider(BaseTranslationProvider):
    display_name = "Argos Translate Local"

    def __init__(self, auto_install=True, session=None, log_callback=None,
                 package_module=None, translate_module=None):
        super().__init__(session=session, log_callback=log_callback)
        self.auto_install = bool(auto_install)
        self._model_lock = threading.RLock()
        self._failed_pairs = set()
        self._reported_pairs = set()
        self._available_packages = None
        self.package_module = package_module
        self.translate_module = translate_module
        if self.package_module is None or self.translate_module is None:
            try:
                # MiniSBD evita cargar Stanza/PyTorch para la segmentación. Argos
                # importa `stanza` de forma incondicional, así que proporcionamos
                # un módulo mínimo que nunca se ejecuta bajo este modo.
                os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")
                os.environ.setdefault("ARGOS_STANZA_AVAILABLE", "false")
                sys.modules.setdefault("spacy", None)
                if "stanza" not in sys.modules:
                    stanza_stub = types.ModuleType("stanza")

                    def unavailable_pipeline(*_args, **_kwargs):
                        raise RuntimeError("Stanza está desactivado; Argos utiliza MiniSBD.")

                    stanza_stub.Pipeline = unavailable_pipeline
                    sys.modules["stanza"] = stanza_stub
                import argostranslate.package as argos_package
                import argostranslate.translate as argos_translate
                self.package_module = argos_package
                self.translate_module = argos_translate
            except ImportError:
                self.package_module = None
                self.translate_module = None

    def is_available(self):
        return self.package_module is not None and self.translate_module is not None

    def _get_translation(self, source, target):
        languages = self.translate_module.get_installed_languages()
        source_language = next((lang for lang in languages if lang.code == source), None)
        target_language = next((lang for lang in languages if lang.code == target), None)
        if source_language is None or target_language is None:
            return None
        try:
            return source_language.get_translation(target_language)
        except Exception:
            return None

    def _install_package(self, available, source, target):
        candidate = next(
            (item for item in available
             if item.from_code == source and item.to_code == target),
            None,
        )
        if candidate is None:
            return False
        self.log(f"⬇️ Descargando modelo Argos {source} → {target}...")
        self.package_module.install_from_path(candidate.download())
        self.log(f"✅ Modelo Argos {source} → {target} instalado.")
        return True

    def _get_available_packages(self):
        if self._available_packages is None:
            self.log("🔎 Actualizando catálogo de modelos Argos...")
            self.package_module.update_package_index()
            self._available_packages = self.package_module.get_available_packages()
        return self._available_packages

    def _ensure_translation(self, source, target):
        pair = (source, target)
        with self._model_lock:
            translation = self._get_translation(source, target)
            if translation is not None or pair in self._failed_pairs:
                return translation
            if not self.auto_install:
                self._failed_pairs.add(pair)
                return None
            try:
                available = self._get_available_packages()
                installed = self._install_package(available, source, target)
                # Argos puede encadenar traducciones mediante inglés. Instalamos
                # ambas piernas únicamente cuando no existe un modelo directo.
                if not installed and source != "en" and target != "en":
                    first = self._install_package(available, source, "en")
                    second = self._install_package(available, "en", target)
                    installed = first and second
                translation = self._get_translation(source, target) if installed else None
            except Exception as exc:
                self.log(f"⚠️ No se pudo preparar Argos {source} → {target}: {exc}")
                translation = None
            if translation is None:
                self._failed_pairs.add(pair)
            return translation

    @staticmethod
    def _translate_preserving_tokens(translation, protected_text):
        """Traduce solo texto natural y jamás expone placeholders al modelo."""
        token_pattern = re.compile(r"(___PH_\d+___)")
        if not token_pattern.search(protected_text):
            return translation.translate(protected_text)
        translated_parts = []
        for part in token_pattern.split(protected_text):
            if not part:
                continue
            if token_pattern.fullmatch(part):
                translated_parts.append(part)
                continue
            leading = re.match(r"^\s*", part).group(0)
            trailing = re.search(r"\s*$", part).group(0)
            natural_text = part[len(leading):]
            if trailing:
                natural_text = natural_text[:-len(trailing)]
            if not natural_text or not re.search(r"\w", natural_text, flags=re.UNICODE):
                translated_parts.append(part)
                continue
            translated_natural = translation.translate(natural_text).strip()
            translated_parts.append(f"{leading}{translated_natural}{trailing}")
        return "".join(translated_parts)

    def translate_single(self, base_lang, target_lang, protected_text):
        if not self.is_available():
            return None
        source = normalize_language_code(base_lang)
        target = normalize_language_code(target_lang)
        if source == target:
            return protected_text
        translation = self._ensure_translation(source, target)
        if translation is None:
            pair = (source, target)
            if pair not in self._reported_pairs:
                self._reported_pairs.add(pair)
                self.log(f"ℹ️ Argos no dispone del modelo {source} → {target}; usando respaldo.")
            return None
        with self._model_lock:
            return self._translate_preserving_tokens(translation, protected_text)


class GoogleTranslateProvider(BaseTranslationProvider):
    display_name = "Google Translate"
    PRIMARY_URL = "https://translate.googleapis.com/translate_a/single"
    FALLBACK_URL = "https://translate.google.com/m"

    def __init__(self, session=None, log_callback=None):
        super().__init__(session=session, log_callback=log_callback)
        self._request_gate = threading.BoundedSemaphore(2)
        self._cooldown_until = 0.0
        self._cooldown_lock = threading.Lock()
        self._rate_limit_reported = False

    def translate_single(self, base_lang, target_lang, protected_text):
        source = normalize_language_code(base_lang)
        target = normalize_language_code(target_lang)
        google_aliases = {"nb": "no", "zh": "zh-CN"}
        source = google_aliases.get(source, source)
        target = google_aliases.get(target, target)
        with self._cooldown_lock:
            if time.monotonic() < self._cooldown_until:
                return None
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                params = {
                    "client": "gtx", "sl": source, "tl": target,
                    "dt": "t", "q": protected_text,
                }
                with self._request_gate:
                    # Varias tareas pueden haber esperado el semáforo antes del
                    # primer 429. Se vuelve a comprobar aquí para cortar la cola.
                    with self._cooldown_lock:
                        if time.monotonic() < self._cooldown_until:
                            return None
                    response = self.session.get(self.PRIMARY_URL, params=params, timeout=15)
                if response.status_code == 429:
                    with self._cooldown_lock:
                        self._cooldown_until = time.monotonic() + 60
                        should_log = not self._rate_limit_reported
                        self._rate_limit_reported = True
                    if should_log:
                        self.log("⚠️ Google limitó temporalmente las solicitudes (429). "
                                 "Se pausará Google durante 60 segundos y se usará el respaldo configurado.")
                    return None
                response.raise_for_status()
                with self._cooldown_lock:
                    self._rate_limit_reported = False
                data = response.json()
                translated = "".join(
                    segment[0] for segment in (data[0] if data and data[0] else [])
                    if isinstance(segment, list) and segment and isinstance(segment[0], str)
                )
                if translated:
                    return translated
            except Exception as exc:
                if attempt == MAX_RETRY_ATTEMPTS:
                    self.log(f"⚠️ Google API falló: {exc}. Intentando endpoint alternativo...")
                else:
                    time.sleep(0.2 * attempt)
        try:
            response = self.session.get(
                self.FALLBACK_URL,
                params={"sl": source, "tl": target, "q": protected_text},
                timeout=15,
            )
            response.raise_for_status()
            match = re.search(r'class="result-container">(.*?)</div>', response.text, re.DOTALL)
            return html.unescape(match.group(1)).strip() if match else None
        except Exception as exc:
            self.log(f"⚠️ Google Translate no disponible: {exc}")
            return None


class OpenAICompatibleProvider(BaseTranslationProvider):
    display_name = "IA OpenAI-Compatible"

    def __init__(self, base_url="http://localhost:11434/v1", api_key="", model="llama3.2",
                 session=None, log_callback=None):
        super().__init__(session=session, log_callback=log_callback)
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""

    def is_available(self):
        return bool(self.base_url and self.model)

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def translate_single(self, base_lang, target_lang, protected_text):
        if not self.is_available():
            return None
        prompt = (
            f"Translate the following app localization text from {base_lang} to {target_lang}. "
            "Return only the translated text. Preserve every placeholder, token, XML tag, "
            "newline and formatting marker exactly. Do not add quotes or explanations.\n\n"
            f"TEXT:\n{protected_text}"
        )
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": "You are a precise software localization translator."},
                {"role": "user", "content": prompt},
            ],
        }
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                response = self.session.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(), json=payload, timeout=60,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"].strip()
                if content.startswith("```") and content.endswith("```"):
                    content = re.sub(r"^```(?:text)?\s*|\s*```$", "", content).strip()
                return content or None
            except Exception as exc:
                if attempt == MAX_RETRY_ATTEMPTS:
                    self.log(f"⚠️ IA {self.model} no respondió: {exc}")
                else:
                    time.sleep(0.35 * attempt)
        return None

    def check_health(self):
        if not self.is_available():
            return False, "Faltan endpoint o modelo."
        try:
            response = self.session.get(f"{self.base_url}/models", headers=self._headers(), timeout=10)
            if response.ok:
                return True, "Endpoint accesible."
            return False, f"El endpoint respondió HTTP {response.status_code}."
        except Exception as exc:
            return False, str(exc)


class MyMemoryProvider(BaseTranslationProvider):
    display_name = "MyMemory"
    URL = "https://api.mymemory.translated.net/get"

    def translate_single(self, base_lang, target_lang, protected_text):
        base_lang = normalize_language_code(base_lang)
        target_lang = normalize_language_code(target_lang)
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                response = self.session.get(
                    self.URL,
                    params={"q": protected_text, "langpair": f"{base_lang}|{target_lang}"},
                    timeout=15,
                )
                response.raise_for_status()
                translated = response.json().get("responseData", {}).get("translatedText")
                if translated:
                    return html.unescape(translated)
            except Exception as exc:
                if attempt == MAX_RETRY_ATTEMPTS:
                    self.log(f"⚠️ MyMemory no disponible: {exc}")
                else:
                    time.sleep(0.2 * attempt)
        return None


class TranslationProviderManager:
    CONFIG_FILE = "translation_config.json"
    CONFIG_VERSION = 2
    PROVIDER_NAMES = ("argos", "google", "local_ai", "cloud_ai", "mymemory")

    def __init__(self, config_dir=None, log_callback=None):
        self.config_dir = config_dir or os.getcwd()
        self.log_callback = log_callback or (lambda _message: None)
        self.config_path = os.path.join(self.config_dir, self.CONFIG_FILE)
        self._reported_fallbacks = set()
        self.config = {
            "config_version": self.CONFIG_VERSION,
            "active_provider": "argos",
            "auto_failover": True,
            "argos": {"auto_install": True},
            "local_ai": {
                "base_url": "http://localhost:11434/v1", "api_key": "", "model": "llama3.2"
            },
            "cloud_ai": {
                "base_url": "https://api.deepseek.com/v1", "api_key": "", "model": "deepseek-chat"
            },
        }
        self._load_config()
        self._build_providers()

    def _build_providers(self):
        local = self.config["local_ai"]
        cloud = self.config["cloud_ai"]
        self.providers = {
            "argos": ArgosTranslateProvider(
                auto_install=self.config["argos"].get("auto_install", True),
                log_callback=self.log_callback,
            ),
            "google": GoogleTranslateProvider(log_callback=self.log_callback),
            "local_ai": OpenAICompatibleProvider(**local, log_callback=self.log_callback),
            "cloud_ai": OpenAICompatibleProvider(**cloud, log_callback=self.log_callback),
            "mymemory": MyMemoryProvider(log_callback=self.log_callback),
        }

    def _load_config(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
            if isinstance(saved, dict):
                saved_version = int(saved.get("config_version", 1))
                for key in ("active_provider", "auto_failover"):
                    if key in saved:
                        self.config[key] = saved[key]
                # La versión 2 introduce Argos como motor principal. Los proyectos
                # antiguos se migran una vez; después se respeta la elección manual.
                if saved_version < self.CONFIG_VERSION:
                    self.config["active_provider"] = "argos"
                if isinstance(saved.get("argos"), dict):
                    self.config["argos"].update(saved["argos"])
                for key in ("local_ai", "cloud_ai"):
                    if isinstance(saved.get(key), dict):
                        self.config[key].update(saved[key])
        except (OSError, json.JSONDecodeError):
            pass

    def get_public_config(self):
        return json.loads(json.dumps(self.config))

    def save_config(self, new_config):
        if not isinstance(new_config, dict):
            raise ValueError("Configuración de proveedores inválida.")
        active = new_config.get("active_provider", self.config["active_provider"])
        if active not in self.PROVIDER_NAMES:
            raise ValueError(f"Proveedor desconocido: {active}")
        self.config["active_provider"] = active
        self.config["config_version"] = self.CONFIG_VERSION
        self.config["auto_failover"] = bool(new_config.get("auto_failover", True))
        if isinstance(new_config.get("argos"), dict):
            self.config["argos"]["auto_install"] = bool(
                new_config["argos"].get("auto_install", True)
            )
        for key in ("local_ai", "cloud_ai"):
            values = new_config.get(key, {})
            if isinstance(values, dict):
                for field in ("base_url", "api_key", "model"):
                    if field in values:
                        self.config[key][field] = str(values[field]).strip()
        os.makedirs(self.config_dir, exist_ok=True)
        temporary = f"{self.config_path}.tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(self.config, handle, indent=2, ensure_ascii=False)
        os.replace(temporary, self.config_path)
        self._build_providers()

    def set_active_provider(self, provider_name):
        if provider_name not in self.PROVIDER_NAMES:
            raise ValueError(f"Proveedor desconocido: {provider_name}")
        config = self.get_public_config()
        config["active_provider"] = provider_name
        self.save_config(config)

    def get_provider(self, provider_name=None):
        name = provider_name or self.config.get("active_provider", "argos")
        return self.providers.get(name, self.providers["google"])

    def translate_single_with_failover(self, base_lang, target_lang, protected_text):
        active_name = self.config.get("active_provider", "argos")
        auto_failover = self.config.get("auto_failover", True)
        chain = [active_name]
        if auto_failover:
            chain.extend(name for name in ("argos", "google", "mymemory") if name not in chain)
        for name in chain:
            provider = self.get_provider(name)
            if not provider.is_available():
                self.log_callback(f"ℹ️ {name} no está configurado; probando el siguiente proveedor.")
                continue
            try:
                translated = provider.translate_single(base_lang, target_lang, protected_text)
                if translated:
                    if name != active_name:
                        fallback_key = (active_name, name, base_lang, target_lang)
                        if fallback_key not in self._reported_fallbacks:
                            self._reported_fallbacks.add(fallback_key)
                            self.log_callback(
                                f"✅ Respaldo activo para {base_lang} → {target_lang}: {name}."
                            )
                    return translated
            except Exception as exc:
                self.log_callback(f"⚠️ Error con {name}: {exc}")
            if not auto_failover:
                break
        return None
