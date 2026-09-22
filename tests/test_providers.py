import os
import tempfile
import unittest

from model.providers import ArgosTranslateProvider, TranslationProviderManager


class FakeProvider:
    def __init__(self, result=None, available=True):
        self.result = result
        self.available = available
        self.calls = []

    def is_available(self):
        return self.available

    def translate_single(self, source, target, text):
        self.calls.append((source, target, text))
        return self.result


class ProviderManagerTests(unittest.TestCase):
    def test_argos_never_exposes_placeholders_to_the_model(self):
        class Translation:
            def translate(self, text):
                self.last_texts.append(text)
                return f"TR:{text}"

            def __init__(self):
                self.last_texts = []

        translation = Translation()

        class Language:
            def __init__(self, code):
                self.code = code

            def get_translation(self, _target):
                return translation

        class TranslateModule:
            @staticmethod
            def get_installed_languages():
                return [Language("en"), Language("es")]

        provider = ArgosTranslateProvider(
            auto_install=False,
            package_module=object(),
            translate_module=TranslateModule(),
        )
        result = provider.translate_single(
            "en", "es", "Hello ___PH_0___, you have ___PH_1___ songs"
        )

        self.assertEqual(result.count("___PH_0___"), 1)
        self.assertEqual(result.count("___PH_1___"), 1)
        self.assertTrue(all("___PH_" not in text for text in translation.last_texts))

    def test_configuration_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = TranslationProviderManager(directory)
            config = manager.get_public_config()
            config["active_provider"] = "cloud_ai"
            config["auto_failover"] = False
            config["cloud_ai"] = {
                "base_url": "https://example.test/v1",
                "api_key": "secret",
                "model": "translator-model",
            }
            manager.save_config(config)

            restored = TranslationProviderManager(directory).get_public_config()
            self.assertEqual(restored["active_provider"], "cloud_ai")
            self.assertFalse(restored["auto_failover"])
            self.assertEqual(restored["cloud_ai"]["model"], "translator-model")
            self.assertTrue(os.path.isfile(os.path.join(directory, "translation_config.json")))

    def test_failover_uses_google_then_mymemory(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = TranslationProviderManager(directory)
            primary = FakeProvider(None)
            argos = FakeProvider(None)
            microsoft = FakeProvider(None)
            google = FakeProvider(None)
            mymemory = FakeProvider("Hola")
            manager.providers.update({
                "cloud_ai": primary,
                "argos": argos,
                "microsoft": microsoft,
                "google": google,
                "mymemory": mymemory,
            })
            manager.config["active_provider"] = "cloud_ai"
            manager.config["auto_failover"] = True

            result = manager.translate_single_with_failover("en", "es", "Hello")

            self.assertEqual(result, "Hola")
            self.assertEqual(len(primary.calls), 1)
            self.assertEqual(len(argos.calls), 1)
            self.assertEqual(len(microsoft.calls), 1)
            self.assertEqual(len(google.calls), 1)
            self.assertEqual(len(mymemory.calls), 1)

    def test_disabled_failover_stops_after_primary(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = TranslationProviderManager(directory)
            primary = FakeProvider(None)
            google = FakeProvider("Should not be used")
            manager.providers.update({"local_ai": primary, "google": google})
            manager.config["active_provider"] = "local_ai"
            manager.config["auto_failover"] = False

            self.assertIsNone(manager.translate_single_with_failover("en", "es", "Hello"))
            self.assertEqual(len(primary.calls), 1)
            self.assertEqual(len(google.calls), 0)

    def test_argos_is_the_default_primary_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = TranslationProviderManager(directory)
            argos = FakeProvider("Hola local")
            google = FakeProvider("Hola remota")
            manager.providers.update({"argos": argos, "google": google})

            self.assertEqual(manager.config["active_provider"], "argos")
            self.assertEqual(
                manager.translate_single_with_failover("en", "es", "Hello"),
                "Hola local",
            )
            self.assertEqual(len(argos.calls), 1)
            self.assertEqual(len(google.calls), 0)

    def test_legacy_configuration_migrates_google_to_argos_once(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, "translation_config.json")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write('{"active_provider":"google","auto_failover":true}')

            manager = TranslationProviderManager(directory)
            self.assertEqual(manager.config["active_provider"], "argos")
            manager.save_config(manager.get_public_config())
            restored = TranslationProviderManager(directory)
            self.assertEqual(restored.config["active_provider"], "argos")

    def test_fallback_success_is_logged_once_per_language_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            logs = []
            manager = TranslationProviderManager(directory, logs.append)
            manager.providers.update({
                "argos": FakeProvider(None),
                "microsoft": FakeProvider(None),
                "google": FakeProvider(None),
                "mymemory": FakeProvider("Hola"),
            })
            manager.config["active_provider"] = "argos"
            manager.translate_single_with_failover("en", "es", "Hello")
            manager.translate_single_with_failover("en", "es", "World")

            fallback_logs = [message for message in logs if "Respaldo activo" in message]
            self.assertEqual(len(fallback_logs), 1)

    def test_extract_json_dict_handles_markdown_and_raw_json(self):
        from model.providers import OpenAICompatibleProvider
        
        # Raw json
        raw = '{"en": "Hello", "fr": "Bonjour"}'
        self.assertEqual(OpenAICompatibleProvider._extract_json_dict(raw), {"en": "Hello", "fr": "Bonjour"})

        # Markdown json fence
        fenced = '```json\n{"es": "Hola", "de": "Hallo"}\n```'
        self.assertEqual(OpenAICompatibleProvider._extract_json_dict(fenced), {"es": "Hola", "de": "Hallo"})

        # Extra conversational text around json
        conversational = 'Here are your translations:\n{"it": "Ciao", "pt": "Ola"}\nHope this helps!'
        self.assertEqual(OpenAICompatibleProvider._extract_json_dict(conversational), {"it": "Ciao", "pt": "Ola"})

    def test_multi_target_provider_support_and_dispatch(self):
        from model.translation_model import TranslationCore
        with tempfile.TemporaryDirectory() as directory:
            manager = TranslationProviderManager(directory)
            
            class FakeMultiTargetProvider:
                supports_multi_target = True
                def __init__(self):
                    self.calls = []
                def is_available(self):
                    return True
                def translate_multi_target(self, base_lang, target_langs, protected_text):
                    self.calls.append((base_lang, target_langs, protected_text))
                    # Returns translations for all requested targets
                    return {lang: f"{protected_text}_{lang}" for lang in target_langs}
                def translate_single(self, base_lang, target_lang, protected_text):
                    return f"{protected_text}_{target_lang}"

            multi_provider = FakeMultiTargetProvider()
            manager.providers["cloud_ai"] = multi_provider
            manager.config["active_provider"] = "cloud_ai"

            core = TranslationCore(directory, lambda _msg: None)
            core.provider_manager = manager

            translations = core.fetch_translations_from_api("es", "Hola", "flutter")
            
            # Debería haber hecho exactamente 1 llamada multi-target
            self.assertEqual(len(multi_provider.calls), 1)
            self.assertEqual(multi_provider.calls[0][0], "es")
            # Debería tener las 30 traducciones completadas
            self.assertEqual(len(translations), len(core.FLUTTER_LANGUAGE_FILES))
            self.assertEqual(translations["es"], "Hola")
            self.assertEqual(translations["en"], "Hola_en")
            self.assertEqual(translations["fr"], "Hola_fr")

    def test_chunk_multi_target_fallback_to_argos_on_rate_limit(self):
        from model.translation_model import TranslationCore
        with tempfile.TemporaryDirectory() as directory:
            manager = TranslationProviderManager(directory)

            class RateLimitedMultiProvider:
                supports_multi_target = True
                def __init__(self):
                    self.calls = 0
                    self.active = True
                def is_available(self):
                    return self.active
                def translate_chunk_multi_target(self, base_lang, target_langs, protected_items):
                    self.calls += 1
                    # Simular 429 inmediato: se desactiva por cooldown y devuelve {}
                    self.active = False
                    return {}
                def translate_single(self, base_lang, target_lang, text):
                    return None

            class FakeArgos:
                def __init__(self):
                    self.calls = []
                def is_available(self):
                    return True
                def translate_single(self, base_lang, target_lang, text):
                    self.calls.append((base_lang, target_lang, text))
                    return f"ARGOS:{text}"

            rl_provider = RateLimitedMultiProvider()
            argos_provider = FakeArgos()
            manager.providers["cloud_ai"] = rl_provider
            manager.providers["argos"] = argos_provider
            manager.config["active_provider"] = "cloud_ai"

            core = TranslationCore(directory, lambda _msg: None)
            core.provider_manager = manager

            batch = core.translate_batch_optimized("es", {"k1": "Hola", "k2": "Mundo"}, "flutter")

            # Intentó el mini-lote 1 sola vez
            self.assertEqual(rl_provider.calls, 1)
            # Y al fallar entró Argos directo
            self.assertTrue(len(argos_provider.calls) > 0)
            self.assertEqual(batch["en"]["k1"], "ARGOS:Hola")
            self.assertEqual(batch["en"]["k2"], "ARGOS:Mundo")

    def test_argos_can_translate_checks_installed_only_without_network(self):
        class Translation:
            def translate(self, text):
                return f"TR:{text}"

        class Language:
            def __init__(self, code, targets=None):
                self.code = code
                self._targets = targets or []

            def get_translation(self, target):
                if target.code in self._targets:
                    return Translation()
                return None

        class TranslateModule:
            @staticmethod
            def get_installed_languages():
                return [
                    Language("es", ["en"]),
                    Language("en", ["fr"]),
                    Language("fr"),
                ]

        class ShouldNeverBeCalledPackageModule:
            @staticmethod
            def update_package_index():
                raise AssertionError("update_package_index should NOT be called!")

            @staticmethod
            def get_available_packages():
                raise AssertionError("get_available_packages should NOT be called!")

        provider = ArgosTranslateProvider(
            auto_install=True,
            package_module=ShouldNeverBeCalledPackageModule(),
            translate_module=TranslateModule(),
        )

        # Direct installed: es -> en
        self.assertTrue(provider.can_translate("es", "en"))
        # Pivot installed: es -> en -> fr
        self.assertTrue(provider.can_translate("es", "fr"))
        # Uninstalled: es -> de (must return False immediately without touching package_module)
        self.assertFalse(provider.can_translate("es", "de"))
        # translate_single on uninstalled must return None immediately
        self.assertIsNone(provider.translate_single("es", "de", "Hola"))

    def test_microsoft_provider_language_normalization(self):
        from model.providers import MicrosoftTranslatorProvider
        self.assertEqual(MicrosoftTranslatorProvider._normalize_ms_lang("es"), "es")
        self.assertEqual(MicrosoftTranslatorProvider._normalize_ms_lang("zh"), "zh-Hans")
        self.assertEqual(MicrosoftTranslatorProvider._normalize_ms_lang("zh-tw"), "zh-Hant")
        self.assertEqual(MicrosoftTranslatorProvider._normalize_ms_lang("no"), "nb")
        self.assertEqual(MicrosoftTranslatorProvider._normalize_ms_lang("iw"), "he")
        self.assertEqual(MicrosoftTranslatorProvider._normalize_ms_lang("in"), "id")
        self.assertEqual(MicrosoftTranslatorProvider._normalize_ms_lang("fil"), "fil")

    def test_microsoft_provider_azure_mode_mocked(self):
        from model.providers import MicrosoftTranslatorProvider
        class MockResponse:
            status_code = 200
            ok = True
            @staticmethod
            def json():
                return [{"translations": [{"text": "Hello world", "to": "en"}]}]
            @staticmethod
            def raise_for_status():
                pass

        class MockSession:
            def __init__(self):
                self.headers = {}
                self.posts = []
            def post(self, url, **kwargs):
                self.posts.append((url, kwargs))
                return MockResponse()

        session = MockSession()
        provider = MicrosoftTranslatorProvider(api_key="test_key", region="eastus", session=session)
        result = provider.translate_single("es", "en", "Hola mundo")
        self.assertEqual(result, "Hello world")
        self.assertEqual(len(session.posts), 1)
        self.assertIn("Ocp-Apim-Subscription-Key", session.posts[0][1]["headers"])
        self.assertEqual(session.posts[0][1]["headers"]["Ocp-Apim-Subscription-Key"], "test_key")
        self.assertEqual(session.posts[0][1]["headers"]["Ocp-Apim-Subscription-Region"], "eastus")

    def test_microsoft_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = TranslationProviderManager(directory)
            config = manager.get_public_config()
            config["active_provider"] = "microsoft"
            config["microsoft"] = {"api_key": "my_azure_key", "region": "westeurope"}
            manager.save_config(config)

            restored = TranslationProviderManager(directory).get_public_config()
            self.assertEqual(restored["active_provider"], "microsoft")
            self.assertEqual(restored["microsoft"]["api_key"], "my_azure_key")
            self.assertEqual(restored["microsoft"]["region"], "westeurope")


if __name__ == "__main__":
    unittest.main()

