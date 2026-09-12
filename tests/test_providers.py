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
            google = FakeProvider(None)
            mymemory = FakeProvider("Hola")
            manager.providers.update({
                "cloud_ai": primary,
                "argos": argos,
                "google": google,
                "mymemory": mymemory,
            })
            manager.config["active_provider"] = "cloud_ai"
            manager.config["auto_failover"] = True

            result = manager.translate_single_with_failover("en", "es", "Hello")

            self.assertEqual(result, "Hola")
            self.assertEqual(len(primary.calls), 1)
            self.assertEqual(len(argos.calls), 1)
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
                "google": FakeProvider(None),
                "mymemory": FakeProvider("Hola"),
            })
            manager.config["active_provider"] = "argos"
            manager.translate_single_with_failover("en", "es", "Hello")
            manager.translate_single_with_failover("en", "es", "World")

            fallback_logs = [message for message in logs if "Respaldo activo" in message]
            self.assertEqual(len(fallback_logs), 1)


if __name__ == "__main__":
    unittest.main()
