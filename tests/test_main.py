"""API contracts/failure paths, without network requests or real credentials."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import main


def ai_payload():
    scenes = main.offline_script("How do volcanoes erupt?")
    return {"scenes": [main.asdict(scene) for scene in scenes]}


class EnvironmentTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENROUTER_MODEL": "shell/model"}, clear=True)
    def test_dotenv_loads_known_values_without_overwriting_shell_or_executing_text(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / ".env"
            path.write_text('# comment\nOPENROUTER_API_KEY="test-placeholder"\n'
                            'OPENROUTER_MODEL=file/model\nUNRELATED=ignored\n'
                            'AUTOSHORTS_VOICE=$(touch should-never-run)\n')
            main.load_environment(path)
        self.assertEqual(os.environ["OPENROUTER_API_KEY"], "test-placeholder")
        self.assertEqual(os.environ["OPENROUTER_MODEL"], "shell/model")
        self.assertNotIn("UNRELATED", os.environ)
        self.assertEqual(os.environ["AUTOSHORTS_VOICE"], "$(touch should-never-run)")


class ScriptTests(unittest.TestCase):
    def test_all_offline_scripts_and_visuals_are_valid(self):
        for key in main.FALLBACKS:
            topic = next(iter(main.ALIASES[key]))
            scenes = main.offline_script(topic)
            self.assertEqual(scenes, main.validate_script({"scenes": [main.asdict(s) for s in scenes]}))
        self.assertNotEqual(main.offline_script("gravity"), main.offline_script("photosynthesis"))

    @patch.dict(os.environ, {}, clear=True)
    def test_unknown_offline_topic_never_gets_generic_script(self):
        with self.assertRaisesRegex(ValueError, "No offline script"):
            main.make_script("How do solar panels work?", False)

    def test_missing_or_repeated_visual_guidance_rejected(self):
        payload = ai_payload()
        del payload["scenes"][0]["visual_description"]
        with self.assertRaisesRegex(ValueError, "visual_description"):
            main.validate_script(payload)
        payload = ai_payload()
        for scene in payload["scenes"]:
            scene["image_keywords"] = "generic nature"
        with self.assertRaisesRegex(ValueError, "distinct image searches"):
            main.validate_script(payload)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-placeholder"}, clear=True)
    def test_arbitrary_topic_is_sent_to_ai_and_response_used(self):
        # A simulated API answer for a subject absent from the offline library.
        records = [
            ("Sunlight to electricity", "Panels convert light into electrical energy.",
             "Solar panels turn sunlight into electricity using the photovoltaic effect. Their cells absorb light and release electrical charges inside a semiconductor.",
             "Solar panels receiving sunlight on a rooftop", "solar panels rooftop"),
            ("Moving charges", "An electric field guides the flow.",
             "A built-in electric field guides those charges in one direction. Connecting a circuit lets them flow as an electric current.",
             "Close view of solar cells and panel wiring", "solar cell closeup"),
            ("Making power usable", "An inverter converts direct current.",
             "Panels produce direct current. An inverter changes it into alternating current, which powers most household appliances and can feed the grid.",
             "A solar installation with an electrical inverter", "solar inverter installation"),
            ("Changing output", "Weather and shade affect production.",
             "Output depends on sunlight, shade, temperature, and panel orientation. Batteries can store extra energy for use when sunlight is unavailable later.",
             "Clouds over a solar farm", "solar farm clouds"),
        ]
        payload = {"scenes": [main.asdict(main.Scene(*record)) for record in records]}
        create = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(payload)))]))
        fake_sdk = SimpleNamespace(OpenAI=Mock(return_value=SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)))))
        with patch.dict("sys.modules", {"openai": fake_sdk}):
            script = main.make_script("How do solar panels work?", False)
        self.assertTrue(script.source.startswith("openai:"))
        self.assertEqual(create.call_args.kwargs["messages"][1]["content"],
                         "How do solar panels work?")
        self.assertEqual(len(script.scenes), 4)
        self.assertIn("photovoltaic", script.scenes[0].narration)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-placeholder"}, clear=True)
    def test_ai_outage_falls_back_only_for_known_topic_without_leaking_details(self):
        fake_sdk = SimpleNamespace(OpenAI=Mock(side_effect=RuntimeError("secret request details")))
        errors = io.StringIO()
        with patch.dict("sys.modules", {"openai": fake_sdk}), contextlib.redirect_stderr(errors):
            self.assertEqual(main.make_script("gravity", False).source, "curated_offline")
            with self.assertRaises(ValueError):
                main.make_script("A topic outside the library", False)
        self.assertNotIn("secret request details", errors.getvalue())

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "router-test-placeholder",
                             "OPENROUTER_MODEL": "openai/gpt-4o-mini"}, clear=True)
    def test_openrouter_auto_selection_uses_correct_endpoint_key_and_model(self):
        create = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(ai_payload())))]))
        constructor = Mock(return_value=SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
        with patch.dict("sys.modules", {"openai": SimpleNamespace(OpenAI=constructor)}):
            script = main.make_script("How do volcanoes erupt?", False)
        self.assertEqual(script.source, "openrouter:openai/gpt-4o-mini")
        self.assertEqual(constructor.call_args.kwargs["base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(constructor.call_args.kwargs["api_key"], "router-test-placeholder")
        self.assertEqual(create.call_args.kwargs["model"], "openai/gpt-4o-mini")
        self.assertTrue(create.call_args.kwargs["extra_body"]["provider"]["require_parameters"])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "openai-test-placeholder"}, clear=True)
    def test_explicit_openrouter_never_uses_openai_key(self):
        constructor = Mock()
        with patch.dict("sys.modules", {"openai": SimpleNamespace(OpenAI=constructor)}):
            with self.assertRaisesRegex(ValueError, "No offline script"):
                main.make_script("How do solar panels work?", False, "openrouter")
        constructor.assert_not_called()


class VisualTests(unittest.TestCase):
    def test_pexels_download_records_credits_and_does_not_forward_key(self):
        scene = main.offline_script("gravity")[0]
        photo = {"id": 123, "src": {"large2x": "https://images.pexels.com/example.jpg"},
                 "photographer": "Example Artist", "url": "https://www.pexels.com/photo/123/",
                 "photographer_url": "https://www.pexels.com/@example"}
        jpeg = io.BytesIO()
        main.Image.new("RGB", (100, 200), "blue").save(jpeg, format="JPEG")
        with tempfile.TemporaryDirectory() as work, patch.object(main, "fetch_bytes", side_effect=[
                json.dumps({"photos": [photo]}).encode(), jpeg.getvalue()]) as fetch:
            used = set()
            visual = main.get_visual(scene, Path(work) / "photo.png", "test-only-placeholder", used)
            self.assertEqual(visual.source, "pexels")
            self.assertEqual(visual.photographer, "Example Artist")
            self.assertEqual(used, {123})
            self.assertEqual(fetch.call_args_list[0].args[1], {"Authorization": "test-only-placeholder"})
            self.assertEqual(len(fetch.call_args_list[1].args), 1)

    def test_image_outage_empty_results_and_invalid_images_use_cards(self):
        scene = main.offline_script("gravity")[0]
        cases = [HTTPError("https://api.pexels.com", 429, "rate limited", {}, None),
                 b'{"photos": []}',
                 b'{"photos": [{"id": 1, "src": {"large": "https://images.pexels.com/a"}}]}']
        for result in cases:
            with tempfile.TemporaryDirectory() as work, patch.object(main, "fetch_bytes") as fetch:
                if isinstance(result, Exception):
                    fetch.side_effect = result
                else:
                    fetch.return_value = result  # JSON is intentionally not a valid image.
                visual = main.get_visual(scene, Path(work) / "background.png", "test-only-placeholder", set())
                self.assertEqual(visual.source, "text_card")
                self.assertTrue(visual.path.exists())

    def test_text_card_backgrounds_differ_across_topics(self):
        with tempfile.TemporaryDirectory() as work:
            paths = [Path(work) / (name + ".png") for name in ("sky", "volcano")]
            main.get_visual(main.offline_script("Why is the sky blue?")[0], paths[0], None, set())
            main.get_visual(main.offline_script("How do volcanoes erupt?")[0], paths[1], None, set())
            self.assertNotEqual(paths[0].read_bytes(), paths[1].read_bytes())


if __name__ == "__main__":
    unittest.main()
