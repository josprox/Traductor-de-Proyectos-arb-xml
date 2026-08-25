import json
import os
import tempfile
import unittest
from unittest.mock import patch

from lxml import etree

from model.translation_model import TranslationCore


class FormatIsolationTests(unittest.TestCase):
    def make_core(self, path):
        core = TranslationCore.__new__(TranslationCore)
        core.project_path = path
        core.log_callback = lambda _message: None
        core._translation_cache = {}
        return core

    def test_flutter_correction_never_touches_xml(self):
        with tempfile.TemporaryDirectory() as project:
            with open(os.path.join(project, "intl_en.arb"), "w", encoding="utf-8") as handle:
                json.dump({"@@locale": "en", "hello": "Hello {name}"}, handle)
            with open(os.path.join(project, "intl_es.arb"), "w", encoding="utf-8") as handle:
                json.dump({"@@locale": "es"}, handle)
            xml_dir = os.path.join(project, "values-es")
            os.makedirs(xml_dir)
            xml_path = os.path.join(xml_dir, TranslationCore.KOTLIN_STRINGS_FILE_NAME)
            xml_before = '<resources><string name="xml_only">Sin cambios</string></resources>'
            with open(xml_path, "w", encoding="utf-8") as handle:
                handle.write(xml_before)

            core = self.make_core(project)
            core.translate_missing_for_target = lambda *_args, **_kwargs: {
                "hello": "Hola {name}"
            }
            report = core.fix_and_format_project_files("flutter", True)

            with open(os.path.join(project, "intl_es.arb"), encoding="utf-8") as handle:
                spanish = json.load(handle)
            with open(xml_path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), xml_before)
            self.assertEqual(spanish["hello"], "Hola {name}")
            self.assertIn("name", spanish["@hello"]["placeholders"])
            self.assertTrue(all(item["platform"] == "Flutter (ARB)" for item in report["details"]))

    def test_flutter_correction_translates_only_missing_keys(self):
        with tempfile.TemporaryDirectory() as project:
            with open(os.path.join(project, "intl_en.arb"), "w", encoding="utf-8") as handle:
                json.dump({"@@locale": "en", "existing": "Existing", "missing": "Missing"}, handle)
            with open(os.path.join(project, "intl_es.arb"), "w", encoding="utf-8") as handle:
                json.dump({"@@locale": "es", "existing": "Ya existe"}, handle)

            core = self.make_core(project)
            calls = []

            def fake_translate(source, target, values, **_kwargs):
                calls.append((source, target, dict(values)))
                return {"missing": "Faltante"}

            core.translate_missing_for_target = fake_translate
            core.fix_and_format_project_files("flutter", True, cleanup_unexpected=False)

            self.assertEqual(calls, [("en", "es", {"missing": "Missing"})])
            with open(os.path.join(project, "intl_es.arb"), encoding="utf-8") as handle:
                spanish = json.load(handle)
            self.assertEqual(spanish["existing"], "Ya existe")
            self.assertEqual(spanish["missing"], "Faltante")

    def test_kotlin_correction_never_touches_arb(self):
        with tempfile.TemporaryDirectory() as project:
            arb_path = os.path.join(project, "intl_en.arb")
            arb_before = '{"@@locale":"en","arb_only":"Untouched"}'
            with open(arb_path, "w", encoding="utf-8") as handle:
                handle.write(arb_before)
            for folder, value in (("values", "Hello"), ("values-es", None)):
                directory = os.path.join(project, folder)
                os.makedirs(directory)
                root = etree.Element("resources")
                if value:
                    element = etree.SubElement(root, "string", name="hello")
                    element.text = value
                with open(os.path.join(directory, TranslationCore.KOTLIN_STRINGS_FILE_NAME), "wb") as handle:
                    handle.write(etree.tostring(root))

            core = self.make_core(project)
            core.translate_batch_optimized = lambda *_args, **_kwargs: {
                "en": {"hello": "Hello"},
                "es": {"hello": "Hola"},
            }
            report = core.fix_and_format_project_files("kotlin", True)

            with open(arb_path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), arb_before)
            tree = etree.parse(os.path.join(project, "values-es", TranslationCore.KOTLIN_STRINGS_FILE_NAME))
            self.assertEqual(tree.getroot().xpath("string[@name='hello']")[0].text, "Hola")
            self.assertTrue(all(item["platform"] == "Kotlin (XML)" for item in report["details"]))

    def test_batch_deduplicates_equal_texts(self):
        core = self.make_core(".")
        calls = []

        def fake_fetch(base_lang, text, platform):
            calls.append((base_lang, text, platform))
            return {"en": text, "es": f"ES:{text}"}

        core.fetch_translations_from_api = fake_fetch
        result = core.translate_batch_optimized(
            "en", {"first": "Same", "second": "Same", "third": "Different"}, "flutter"
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["es"]["first"], result["es"]["second"])

    def test_invalid_platform_is_rejected(self):
        core = self.make_core(".")
        with self.assertRaises(ValueError):
            core.fix_and_format_project_files("auto")
        with self.assertRaises(ValueError):
            core.translate_batch_optimized("en", {"key": "Text"}, "xml")

    def test_unconfigured_flutter_file_is_archived_not_deleted(self):
        with tempfile.TemporaryDirectory() as project:
            allowed_path = os.path.join(project, "intl_en.arb")
            unexpected_path = os.path.join(project, "intl_hi.arb")
            custom_path = os.path.join(project, "app_hi.arb")
            for path, locale in ((allowed_path, "en"), (unexpected_path, "hi"), (custom_path, "hi")):
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump({"@@locale": locale, "hello": "Hello"}, handle)
            core = self.make_core(project)
            core.translate_batch_optimized = lambda *_args, **_kwargs: {"en": {"hello": "Hello"}}

            report = core.fix_and_format_project_files("flutter", sync_missing=False)

            self.assertTrue(os.path.isfile(allowed_path))
            self.assertFalse(os.path.exists(unexpected_path))
            self.assertTrue(os.path.isfile(custom_path), "Los ARB con nombres no administrados no deben tocarse")
            archived_path = os.path.join(report["backup_dir"], "intl_hi.arb")
            self.assertTrue(os.path.isfile(archived_path))
            self.assertEqual(report["unexpected_archived"], 1)

    def test_unconfigured_flutter_cleanup_can_be_disabled(self):
        with tempfile.TemporaryDirectory() as project:
            for file_name in ("intl_en.arb", "intl_hi.arb"):
                with open(os.path.join(project, file_name), "w", encoding="utf-8") as handle:
                    json.dump({"@@locale": "en", "hello": "Hello"}, handle)
            core = self.make_core(project)
            core.fix_and_format_project_files(
                "flutter", sync_missing=False, cleanup_unexpected=False
            )
            self.assertTrue(os.path.isfile(os.path.join(project, "intl_hi.arb")))

    def test_api_joins_segments_and_preserves_placeholders(self):
        core = self.make_core(".")

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return [[["Hola ", "Hello "], ["___PH_0___", "___PH_0___"]]]

        with patch.object(TranslationCore, "FLUTTER_LANGUAGE_FILES", ["intl_en.arb", "intl_es.arb"]):
            with patch("model.translation_model.requests.get", return_value=Response()) as request:
                translations = core.fetch_translations_from_api("en", "Hello {name}", "flutter")

        self.assertEqual(translations["en"], "Hello {name}")
        self.assertEqual(translations["es"], "Hola {name}")
        self.assertEqual(request.call_count, 1)

    def test_selected_provider_is_used_by_translation_core(self):
        core = self.make_core(".")

        class ProviderManager:
            def __init__(self):
                self.calls = []

            def translate_single_with_failover(self, source, target, text):
                self.calls.append((source, target, text))
                return "Hola ___PH_0___"

        core.provider_manager = ProviderManager()
        with patch.object(TranslationCore, "FLUTTER_LANGUAGE_FILES", ["intl_en.arb", "intl_es.arb"]):
            translations = core.fetch_translations_from_api("en", "Hello {name}", "flutter")

        self.assertEqual(translations["es"], "Hola {name}")
        self.assertEqual(core.provider_manager.calls, [("en", "es", "Hello ___PH_0___")])


if __name__ == "__main__":
    unittest.main()
