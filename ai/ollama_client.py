"""Old name kept so existing imports keep working: the model client now
lives in ai/llm.py (the only file that talks to the LLM provider)."""

from ai.llm import LLM as OllamaClient  # noqa: F401
