"""AI quality check evaluation script for Arun question router.

Runs 16 varied questions through the router (rules first, then Ollama fallback),
measures latency, prints resolution method (rules, AI, clarification), and
provides a summary count.

Usage:
    python tools/ai_eval.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.ai_gateway import OllamaGateway
from backend.config import load_config
from backend.db import open_db
from backend.router.intent import validate_intent
from backend.router.router import CLARIFICATION, QuestionRouter
from backend.router.rules import match_rules
from backend.services.tidy_service import TidyService

EVAL_QUESTIONS = [
    # Required tricky questions
    "was I wasting more time on videos than normal yesterday?",
    "is instagram eating my day",
    "did I overdo reels this week",
    "organise my downloads",
    # Rule-based usage queries
    "how much youtube did I watch today",
    "how much time spent on coding yesterday",
    "compare youtube today vs yesterday",
    # Rule-based productivity queries
    "what app did I use the most today",
    "how much screen time today",
    "what was my longest session today",
    "when was I most active today",
    # Rule-based water queries
    "how much water did I drink today",
    "i just drank a glass of water",
    "when was my last water reminder",
    # Tidy variant
    "clean my desktop",
    # Out of scope questions (should clarify)
    "what is the meaning of life",
]


def run_eval() -> None:
    cfg = load_config()
    db = open_db(cfg)
    gateway = OllamaGateway(db, cfg) if cfg.get("ai", {}).get("enabled") else None
    tidy_svc = TidyService(db, cfg)
    router = QuestionRouter(db, cfg, ai_gateway=gateway, tidy_service=tidy_svc)

    print("=" * 80)
    print(f"ARUN ROUTER EVALUATION ({len(EVAL_QUESTIONS)} questions)")
    model = cfg.get("ai", {}).get("model", "none")
    ai_enabled = cfg.get("ai", {}).get("enabled", False)
    print(f"AI Enabled: {ai_enabled} | Model: {model}")
    print("=" * 80)
    print(f"{'#':<3} {'Question':<45} {'Resolved By':<14} {'Intent':<18} {'Latency':<8}")
    print("-" * 80)

    counts = {"rules": 0, "AI": 0, "clarification": 0}
    total_latency_ms = 0.0

    for i, q in enumerate(EVAL_QUESTIONS, 1):
        t0 = time.perf_counter()
        # 1. Determine how router classifies it
        rule_raw = match_rules(q, cfg)
        rule_valid = validate_intent(rule_raw, cfg)

        if rule_valid is not None:
            resolved_by = "rules"
            intent_name = rule_valid["intent"]
            resp = router.ask(q)
        else:
            if gateway is not None:
                ai_raw = gateway.parse_intent(q)
                ai_valid = validate_intent(ai_raw, cfg)
                if ai_valid is not None and ai_valid["intent"] != "unknown":
                    resolved_by = "AI"
                    intent_name = ai_valid["intent"]
                    resp = router.execute(ai_valid)
                else:
                    resolved_by = "clarification"
                    intent_name = (ai_valid or {}).get("intent", "none")
                    resp = {"text": CLARIFICATION}
            else:
                resolved_by = "clarification"
                intent_name = "none"
                resp = {"text": CLARIFICATION}

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        total_latency_ms += elapsed_ms
        counts[resolved_by] += 1

        q_disp = (q[:42] + "...") if len(q) > 45 else q
        print(f"{i:<3} {q_disp:<45} {resolved_by:<14} {intent_name:<18} {elapsed_ms:>6.1f}ms")

    print("=" * 80)
    avg_latency = total_latency_ms / len(EVAL_QUESTIONS) if EVAL_QUESTIONS else 0.0
    print(
        f"SUMMARY: Rules: {counts['rules']} | AI: {counts['AI']} | "
        f"Clarification: {counts['clarification']} | Total: {len(EVAL_QUESTIONS)} | "
        f"Avg Latency: {avg_latency:.1f}ms"
    )
    print("=" * 80)

    db.close()


if __name__ == "__main__":
    run_eval()
