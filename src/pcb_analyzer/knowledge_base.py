"""Local searchable archive of AI-assisted component troubleshooting cases.

Archived AI responses are explicitly marked unverified: retrieval is useful context,
not evidence that an earlier model diagnosis was correct.
"""
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Iterable, List, Optional


def default_knowledge_path() -> str:
    """Return a per-user persistent database path without requiring extra packages."""
    root = os.environ.get("XDG_DATA_HOME") or os.path.join(Path.home(), ".local", "share")
    return os.path.join(root, "pcb-analyzer", "knowledge.sqlite3")


def component_references(board, *texts: str, suspects: Iterable[str] = ()) -> List[str]:
    """Find exact board reference designators mentioned in the conversation/answer."""
    if not board:
        return []
    haystack = "\n".join(str(text or "") for text in texts).casefold()
    found = set()
    suspect_set = {str(ref).casefold() for ref in suspects}
    for component in board.components:
        ref = str(component.reference or "")
        if not ref:
            continue
        # Require non-alphanumeric boundaries so e.g. U1 doesn't match U10.
        if ref.casefold() in suspect_set or re.search(
                r"(?<![\w])" + re.escape(ref) + r"(?![\w])", haystack, re.I):
            found.add(ref)
    return sorted(found, key=str.casefold)


class KnowledgeBase:
    """SQLite-backed case archive and lightweight local retrieval."""

    def __init__(self, path: Optional[str] = None):
        self.path = os.path.abspath(os.path.expanduser(path or default_knowledge_path()))
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS troubleshooting_cases (
                id INTEGER PRIMARY KEY,
                created_at REAL NOT NULL,
                references_json TEXT NOT NULL,
                component_names TEXT NOT NULL,
                problem TEXT NOT NULL,
                response TEXT NOT NULL,
                suggested_tests_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'unverified'
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS cases_created ON troubleshooting_cases(created_at)")
            db.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY,
                created_at REAL NOT NULL,
                board_path TEXT NOT NULL DEFAULT '',
                sender TEXT NOT NULL,
                content TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS chat_created ON chat_messages(id)")

    def save_chat_message(self, sender: str, content: str, board_path: str = "") -> int:
        """Persist only user/assistant conversation messages, not transient UI status."""
        if sender not in ("You", "AI"):
            raise ValueError("Only You and AI messages can be saved")
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO chat_messages(created_at, board_path, sender, content) VALUES (?, ?, ?, ?)",
                (time.time(), str(board_path or ""), sender, str(content)))
            return int(cursor.lastrowid)

    def load_chat_messages(self, limit: int = 500):
        """Load recent conversation messages in chronological order."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT sender, content, board_path FROM chat_messages ORDER BY id DESC LIMIT ?",
                (max(0, int(limit)),)).fetchall()
        return [{"sender": row["sender"], "content": row["content"],
                 "board_path": row["board_path"]} for row in reversed(rows)]

    def clear_chat_history(self):
        with self._connect() as db:
            db.execute("DELETE FROM chat_messages")

    def archive_case(self, problem: str, response: str, references: Iterable[str] = (),
                     component_names: str = "", suggested_tests: Iterable[str] = (),
                     status: str = "unverified") -> int:
        """Store a case; callers should not label model-generated findings verified."""
        refs = sorted({str(ref).strip() for ref in references if str(ref).strip()}, key=str.casefold)
        tests = [str(test).strip() for test in suggested_tests if str(test).strip()]
        with self._connect() as db:
            cursor = db.execute(
                """INSERT INTO troubleshooting_cases
                   (created_at, references_json, component_names, problem, response,
                    suggested_tests_json, status) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (time.time(), json.dumps(refs, ensure_ascii=False), str(component_names),
                 str(problem), str(response), json.dumps(tests, ensure_ascii=False),
                 "verified" if status == "verified" else "unverified"))
            return int(cursor.lastrowid)

    def search_cases(self, query: str = "", references: Iterable[str] = (), limit: int = 5):
        """Return recent cases with matching designators or meaningful query terms."""
        refs = {str(ref).casefold() for ref in references if str(ref).strip()}
        terms = {term.casefold() for term in re.findall(r"[\w-]+", query, flags=re.UNICODE)
                 if len(term) > 1}
        with self._connect() as db:
            rows = db.execute("SELECT * FROM troubleshooting_cases ORDER BY created_at DESC LIMIT 1000").fetchall()
        ranked = []
        for row in rows:
            row_refs = {str(ref).casefold() for ref in json.loads(row["references_json"])}
            corpus = " ".join((row["component_names"], row["problem"], row["response"],
                               " ".join(json.loads(row["suggested_tests_json"]))))
            corpus_terms = {term.casefold() for term in re.findall(r"[\w-]+", corpus, flags=re.UNICODE)}
            shared_refs = len(refs & row_refs)
            shared_terms = len(terms & corpus_terms)
            score = shared_refs * 10 + shared_terms
            if score:
                ranked.append((score, row["created_at"], row))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [self._row_to_case(row) for _, _, row in ranked[:max(0, int(limit))]]

    @staticmethod
    def _row_to_case(row):
        return {"id": row["id"], "created_at": row["created_at"],
                "references": json.loads(row["references_json"]),
                "component_names": row["component_names"], "problem": row["problem"],
                "response": row["response"],
                "suggested_tests": json.loads(row["suggested_tests_json"]),
                "status": row["status"]}

    def format_relevant_cases(self, query: str = "", references: Iterable[str] = (), limit: int = 5):
        cases = self.search_cases(query, references, limit)
        if not cases:
            return "No previous archived troubleshooting cases matched."
        blocks = ["--- LOCAL TROUBLESHOOTING CASE ARCHIVE (AI-GENERATED CASES ARE UNVERIFIED) ---"]
        for case in cases:
            refs = ", ".join(case["references"]) or "unspecified"
            blocks.append(
                f"Case #{case['id']} [{case['status']}] components={refs}; "
                f"parts={case['component_names'] or 'unspecified'}\n"
                f"Problem: {case['problem']}\nPrior AI response (unverified): {case['response']}\n"
                f"Prior tests: {'; '.join(case['suggested_tests']) or 'none'}")
        blocks.append("Treat archived model answers as unverified leads, not established facts. "
                      "Re-check component ratings and current board measurements.")
        return "\n".join(blocks)
