"""Tests for persistent troubleshooting memory; uses temporary SQLite databases."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from pcb_analyzer.ai_agent import ask_ai_async  # noqa: E402
from pcb_analyzer.knowledge_base import KnowledgeBase, component_references  # noqa: E402
from pcb_analyzer.model import Board, Component  # noqa: E402
from pcb_analyzer.testpoints import TestPointStore  # noqa: E402


class InlineThread:
    def __init__(self, target, **_kwargs): self.target = target
    def start(self): self.target()


class TestKnowledgeBase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db_path = os.path.join(self.tempdir.name, "memory.sqlite3")
        self.kb = KnowledgeBase(self.db_path)

    def test_archives_and_retrieves_cases_by_reference_and_terms(self):
        self.kb.archive_case("U1 overheats under load", "Check regulator thermal limit.",
                             references=["U1"], component_names="U1=AMS1117",
                             suggested_tests=["Measure input and output under load"])
        self.kb.archive_case("R7 open circuit", "Inspect solder joints.", references=["R7"])
        matches = self.kb.search_cases("temperature", references=["U1"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["references"], ["U1"])
        self.assertEqual(matches[0]["status"], "unverified")
        self.assertIn("unverified", self.kb.format_relevant_cases("", ["U1"]))

    def test_component_reference_matching_uses_whole_designators(self):
        board = Board(components=[Component("U1", "regulator", "SOT", 0, 0),
                                  Component("U10", "controller", "QFN", 1, 1)])
        self.assertEqual(component_references(board, "U10 is hot"), ["U10"])

    @mock.patch("pcb_analyzer.ai_agent.threading.Thread", InlineThread)
    def test_ai_encounter_is_archived_and_retrieved_on_next_question(self):
        board = Board(components=[Component("U1", "AMS1117", "SOT-223", 0, 0)])
        client = mock.Mock(model="llama3")
        client.list_models.return_value = []
        client.generate.return_value = (
            '{"message":"Check the regulator temperature.", '
            '"suspect_components":["U1"], "suggested_tests":["Measure output ripple"]}')
        callback = mock.Mock()
        ask_ai_async(client, "U1 gets hot", board, TestPointStore(), callback,
                     knowledge_base=self.kb)
        results = self.kb.search_cases("hot", ["U1"])
        self.assertEqual(len(results), 1)
        self.assertIn("U1=AMS1117", results[0]["component_names"])
        self.assertEqual(results[0]["status"], "unverified")

        client.generate.return_value = '{"message":"Compare the measurements with datasheet limits."}'
        callback.reset_mock()
        ask_ai_async(client, "U1 still gets hot", board, TestPointStore(), callback,
                     knowledge_base=self.kb)
        sent_prompt = client.generate.call_args.args[0]
        self.assertIn("LOCAL TROUBLESHOOTING CASE ARCHIVE", sent_prompt)
        self.assertIn("Prior AI response (unverified)", sent_prompt)

    def test_chat_history_persists_only_user_and_ai_messages(self):
        self.kb.save_chat_message("You", "U1 is hot", "/tmp/board.kicad_pcb")
        self.kb.save_chat_message("AI", "Check current draw", "/tmp/board.kicad_pcb")
        with self.assertRaises(ValueError):
            self.kb.save_chat_message("System", "internal status")
        messages = self.kb.load_chat_messages()
        self.assertEqual([message["sender"] for message in messages], ["You", "AI"])
        self.assertEqual(messages[0]["board_path"], "/tmp/board.kicad_pcb")


if __name__ == "__main__":
    unittest.main()
