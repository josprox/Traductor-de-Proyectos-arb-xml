import html
import json
import os
import re
import threading
import time

import requests
from requests.adapters import HTTPAdapter


MAX_RETRY_ATTEMPTS = 3


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
        with self._cooldown_lock:
            if time.monotonic() < self._cooldown_until:
                return None
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                params = {
                    "client": "gtx", "sl": base_lang, "tl": target_lang,
                    "dt": "t", "q": protected_text,
                }
                with self._request_gate:
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
                params={"sl": base_lang, "tl": target_lang, "q": protected_text},
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
    PROVIDER_NAMES = ("google", "local_ai", "cloud_ai", "mymemory")

    def __init__(self, config_dir=None, log_callback=None):
        self.config_dir = config_dir or os.getcwd()
        self.log_callback = log_callback or (lambda _message: None)
        self.config_path = os.path.join(self.config_dir, self.CONFIG_FILE)
        self.config = {
            "active_provider": "google",
            "auto_failover": True,
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
                for key in ("active_provider", "auto_failover"):
                    if key in saved:
                        self.config[key] = saved[key]
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
        self.config["auto_failover"] = bool(new_config.get("auto_failover", True))
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
        name = provider_name or self.config.get("active_provider", "google")
        return self.providers.get(name, self.providers["google"])

    def translate_single_with_failover(self, base_lang, target_lang, protected_text):
        active_name = self.config.get("active_provider", "google")
        auto_failover = self.config.get("auto_failover", True)
        chain = [active_name]
        if auto_failover:
            chain.extend(name for name in ("google", "mymemory") if name not in chain)
        for name in chain:
            provider = self.get_provider(name)
            if not provider.is_available():
                self.log_callback(f"ℹ️ {name} no está configurado; probando el siguiente proveedor.")
                continue
            try:
                translated = provider.translate_single(base_lang, target_lang, protected_text)
                if translated:
                    if name != active_name:
                        self.log_callback(f"✅ Traducción completada mediante respaldo: {name}.")
                    return translated
            except Exception as exc:
                self.log_callback(f"⚠️ Error con {name}: {exc}")
            if not auto_failover:
                break
        return None
