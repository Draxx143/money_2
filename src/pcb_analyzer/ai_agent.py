"""Local AI agent integration (Ollama HTTP API) with structured output."""
import json
import re
import threading
import urllib.request
import urllib.error
from typing import Callable, Optional

from .diagnostics import evaluate_testpoint


class OllamaError(Exception):
    """Transport or API response failure from Ollama."""


class OllamaClient:
    def __init__(self, host="http://127.0.0.1:11434", model="llama3"):
        self.host = host.rstrip("/")
        self.model = model

    def list_models(self) -> list:
        """Returns list of locally available model names."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def generate(self, prompt: str, system: str = "") -> str:
        """Send a synchronous request (normally called in a worker thread)."""
        payload = {"model": self.model, "prompt": prompt, "system": system,
                   "stream": False, "options": {"temperature": 0.1}}
        req = urllib.request.Request(
            f"{self.host}/api/generate", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                message = json.loads(body).get("error", body)
            except (ValueError, AttributeError):
                message = body
            raise OllamaError(f"Ollama HTTP {exc.code}: {message}") from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise OllamaError(f"Cannot get a valid response from Ollama: {exc}") from exc
        if not isinstance(result, dict):
            raise OllamaError("Ollama returned an invalid response")
        if result.get("error"):
            raise OllamaError(str(result["error"]))
        if not isinstance(result.get("response"), str):
            raise OllamaError("Ollama response has no text")
        return result["response"]



def build_context(board, store) -> str:
    """Creates a text summary of the board and measurements for the AI."""
    lines = []
    if board:
        lines.append("--- BOARD COMPONENTS ---")
        for c in board.components:
            lines.append(f"{c.reference}: {c.value} ({c.footprint})")
    else:
        lines.append("No board loaded.")

    lines.append("\n--- TEST POINTS & MEASUREMENTS ---")
    if len(store) == 0:
        lines.append("No test points recorded.")
    else:
        for tp in store:
            status, _ = evaluate_testpoint(tp)
            lines.append(
                f"[{tp.label}] Ref:{tp.reference} Pad:{tp.pad_number} "
                f"Expected:{tp.expected_value}{tp.unit} Actual:{tp.actual_value}{tp.unit} "
                f"Status:{status}"
            )
    return "\n".join(lines)


SYSTEM_PROMPT = """You are an expert electronics repair technician AI.
You are diagnosing a PCB based on the provided context.
You must reply with valid JSON only, no markdown, no conversational text.

CRITICAL INSTRUCTIONS:
1. LANGUAGE: You MUST reply in the EXACT SAME LANGUAGE that the user used to ask their question. If they ask in English, reply in English. If they ask in Persian (Farsi), reply in Persian.
2. JSON KEYS: The JSON keys MUST ALWAYS BE IN ENGLISH exactly as shown below.
3. COMPONENT REFERENCES: Component references (like U1, R5) and units (V, A, ohm) MUST remain in English.

Schema:
{
  "message": "Your explanation/answer here in the user's language...",
  "suspect_components": ["U1", "R5"],
  "suggested_tests": ["Test suggestion 1 in user's language", "Test suggestion 2"]
}
If no component is suspect, return an empty array for suspect_components.
Keep the message concise, technical, and in the user's language.
"""


def parse_ai_response(raw: str) -> dict:
    """Normalize model JSON, allowing fences and surrounding explanatory text."""
    text = raw.strip() if isinstance(raw, str) else str(raw)
    candidates = []
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())
    candidates.append(text)
    # Extract the first balanced object without being confused by braces in strings.
    start = text.find("{")
    if start >= 0:
        depth, quoted, escaped = 0, False, False
        for pos in range(start, len(text)):
            char = text[pos]
            if quoted:
                if escaped: escaped = False
                elif char == "\\": escaped = True
                elif char == '"': quoted = False
            elif char == '"': quoted = True
            elif char == "{": depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:pos + 1])
                    break
    data = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            break
        except (json.JSONDecodeError, TypeError):
            continue
    if not isinstance(data, dict):
        raise ValueError("AI returned invalid JSON: " + text[:2000])

    def as_list(value):
        values = value if isinstance(value, list) else ([] if value is None else [value])
        result = []
        for item in values:
            if isinstance(item, (dict, list)):
                item = json.dumps(item, ensure_ascii=False, sort_keys=True)
            item = str(item).strip()
            if item:
                result.append(item)
        return result

    message = data.get("message", "")
    if not isinstance(message, str):
        message = str(message)
    return {"message": message, "suspect_components": as_list(data.get("suspect_components")),
            "suggested_tests": as_list(data.get("suggested_tests"))}


def ask_ai_async(client: OllamaClient, user_prompt: str, board, store, callback: Callable):
    """Run AI query in a worker and invoke callback exactly once."""
    def worker():
        try:
            context = build_context(board, store)
            raw = client.generate(f"{context}\n\nUser Symptom/Question:\n{user_prompt}", SYSTEM_PROMPT)
            result = {"data": parse_ai_response(raw)}
        except (OllamaError, ValueError) as exc:
            result = {"error": str(exc)}
        except Exception as exc:  # last-resort boundary for worker thread
            result = {"error": f"AI request failed: {exc}"}
        callback(result)

    threading.Thread(target=worker, daemon=True).start()
