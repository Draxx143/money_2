"""Local AI agent integration (Ollama HTTP API) with structured output."""
import json
import threading
import urllib.request
import urllib.error
from typing import Callable, Optional

from .diagnostics import evaluate_testpoint


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
        """Sends a synchronous request (must be run in a thread)."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": 0.1} # low temp for engineering
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("response", "")
        except urllib.error.URLError as e:
            return f"ERROR: Cannot connect to Ollama. Is it running?\nDetails: {e}"
        except Exception as e:
            return f"ERROR: {e}"


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


def ask_ai_async(client: OllamaClient, user_prompt: str, board, store, callback: Callable):
    """Runs the AI query in a background thread and calls callback(result_dict)."""
    def worker():
        context = build_context(board, store)
        full_prompt = f"{context}\n\nUser Symptom/Question:\n{user_prompt}"
        raw_response = client.generate(full_prompt, SYSTEM_PROMPT)

        if raw_response.startswith("ERROR:"):
            callback({"error": raw_response})
            return

        try:
            # Extract JSON even if the model wrapped it in markdown blocks
            clean_json = raw_response
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0]
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0]

            data = json.loads(clean_json.strip())
            callback({"data": data})
        except json.JSONDecodeError:
            # Fallback: model failed to produce JSON
            callback({"error": f"AI returned invalid JSON:\n\n{raw_response}"})

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
