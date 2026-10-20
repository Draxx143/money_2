"""Regression tests for JSON-only Ollama response handling (no network)."""
import os
import sys
import unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from pcb_analyzer.ai_agent import OllamaClient, OllamaError, parse_ai_response, ask_ai_async  # noqa: E402
from pcb_analyzer.testpoints import TestPointStore  # noqa: E402

class InlineThread:
    def __init__(self, target, **_kwargs): self.target = target
    def start(self): self.target()

class TestAIResponse(unittest.TestCase):
    def test_parse_plain_fenced_prose_and_scalar_lists(self):
        for raw in ('{"message":"ok"}', '```json\n{"message":"ok"}\n```',
                    'Answer: {"message":"ok"} thanks'):
            self.assertEqual(parse_ai_response(raw), {"message":"ok", "suspect_components":[], "suggested_tests":[]})
        result = parse_ai_response('{"message":2,"suggested_tests":{"probe":"A"},"suspect_components":7}')
        self.assertEqual(result["message"], "2")
        self.assertEqual(result["suspect_components"], ["7"])
        self.assertEqual(result["suggested_tests"], ['{"probe": "A"}'])

    def test_invalid_empty_list_and_string_payloads_raise(self):
        for raw in ("", "not json", "[]", '"string"'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "AI returned invalid JSON"):
                parse_ai_response(raw)

    @mock.patch("pcb_analyzer.ai_agent.threading.Thread", InlineThread)
    def test_callback_called_exactly_once_for_success_and_exception(self):
        callback = mock.Mock()
        client = mock.Mock()
        client.generate.return_value = '{"message":"ok"}'
        ask_ai_async(client, "hi", None, TestPointStore(), callback)
        callback.assert_called_once()
        callback.reset_mock()
        client.generate.side_effect = TimeoutError("late")
        ask_ai_async(client, "hi", None, TestPointStore(), callback)
        callback.assert_called_once()
        self.assertIn("late", callback.call_args.args[0]["error"])

    @mock.patch("pcb_analyzer.ai_agent.urllib.request.urlopen", side_effect=OSError("refused"))
    def test_generate_raises_typed_transport_exception(self, _urlopen):
        with self.assertRaises(OllamaError): OllamaClient().generate("question")
