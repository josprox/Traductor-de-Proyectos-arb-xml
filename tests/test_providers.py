import os
import tempfile
import unittest

from model.providers import TranslationProviderManager


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
            google = FakeProvider(None)
            mymemory = FakeProvider("Hola")
            manager.providers.update({
                "cloud_ai": primary,
                "google": google,
                "mymemory": mymemory,
            })
            manager.config["active_provider"] = "cloud_ai"
            manager.config["auto_failover"] = True

            result = manager.translate_single_with_failover("en", "es", "Hello")

            self.assertEqual(result, "Hola")
            self.assertEqual(len(primary.calls), 1)
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


if __name__ == "__main__":
    unittest.main()
