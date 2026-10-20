"""Regression tests for JSON-only Ollama response handling (no network)."""
import os
import sys
import unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from pcb_analyzer.ai_agent import OllamaClient, OllamaError, parse_ai_response, ask_ai_async  # noqa: E402
from pcb_analyzer.testpoints import TestPointStore, TestPoint  # noqa: E402
from pcb_analyzer.model import Board, Component  # noqa: E402
from pcb_analyzer.ai_agent import build_context, format_ai_reply  # noqa: E402

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
        client.list_models.return_value = []
        client.generate.return_value = '{"message":"ok"}'
        ask_ai_async(client, "hi", None, TestPointStore(), callback)
        callback.assert_called_once()
        self.assertIn("data", callback.call_args.args[0])
        callback.reset_mock()
        client.list_models.return_value = []
        client.generate.side_effect = TimeoutError("late")
        ask_ai_async(client, "hi", None, TestPointStore(), callback)
        callback.assert_called_once()
        self.assertIn("late", callback.call_args.args[0]["error"])

    def test_reply_format_contains_only_answer_and_tests(self):
        reply = format_ai_reply({"message": "پاسخ", "suggested_tests": ["اندازه‌گیری ولتاژ"]})
        self.assertEqual(reply, "پاسخ\n\n• اندازه‌گیری ولتاژ")
        self.assertNotIn("Suggested Tests", reply)

    @mock.patch("pcb_analyzer.ai_agent.threading.Thread", InlineThread)
    def test_persian_prompt_explicitly_requires_persian_response(self):
        client = mock.Mock()
        client.list_models.return_value = []
        client.generate.return_value = '{"message":"پاسخ"}'
        callback = mock.Mock()
        ask_ai_async(client, "سلام، چرا LED روشن نمی‌شود؟", None, TestPointStore(), callback)
        system_prompt = client.generate.call_args.args[1]
        self.assertIn("Persian (Farsi)", system_prompt)
        self.assertIn("فقط به زبان فارسی", system_prompt)

    def test_context_keeps_testpoints_without_board(self):
        store = TestPointStore()
        store.add(TestPoint(label="orphan", expected_value="5", actual_value="0"))
        self.assertIn("Status:Fail", build_context(None, store))

    def test_host_validation_and_context_truncation_priority(self):
        with self.assertRaises(ValueError): OllamaClient(host="localhost:11434")
        client = OllamaClient(host="https://example.test/")
        self.assertEqual(client.host, "https://example.test")
        board = Board(components=[Component("U1", "chip", "fp", 0, 0),
                                  Component("R1", "res", "fp", 1, 1)])
        store = TestPointStore()
        store.add(TestPoint(label="bad", reference="R1", expected_value="5", actual_value="0", tolerance="1"))
        context = build_context(board, store, max_chars=190)
        self.assertIn("Status:Fail", context)
        self.assertIn("components omitted", context)

    @mock.patch("pcb_analyzer.ai_agent.threading.Thread", InlineThread)
    def test_model_fallback_is_reported(self):
        client = mock.Mock(model="missing")
        client.list_models.return_value = ["available"]
        client.generate.return_value = '{"message":"ready"}'
        callback = mock.Mock()
        ask_ai_async(client, "hello", None, TestPointStore(), callback)
        self.assertEqual(client.model, "available")
        self.assertIn("using available", callback.call_args.args[0]["warning"])

    @mock.patch("pcb_analyzer.ai_agent.urllib.request.urlopen")
    def test_generate_sends_json_mode_context_and_timeout(self, urlopen):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def read(self): return b'{"response":"ok"}'
        urlopen.return_value = Response()
        client = OllamaClient(timeout=17, num_ctx=8192)
        self.assertEqual(client.generate("prompt"), "ok")
        request = urlopen.call_args.args[0]
        import json
        payload = json.loads(request.data)
        self.assertEqual(payload["format"], "json")
        self.assertEqual(payload["options"]["num_ctx"], 8192)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 17)

    @mock.patch("pcb_analyzer.ai_agent.urllib.request.urlopen", side_effect=OSError("refused"))
    def test_generate_raises_typed_transport_exception(self, _urlopen):
        with self.assertRaises(OllamaError): OllamaClient().generate("question")
