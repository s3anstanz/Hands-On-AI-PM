"""Check live mode against the real Anthropic API, with your own key.

Run `python live_check.py` (needs `pip install -r requirements-live.txt` and
ANTHROPIC_API_KEY or another credential live.detect() recognizes). It never runs
in CI. Steps:

1. Counts tokens on every model live mode uses. Free, and it proves each model id
   still exists (a retired model fails here).
2. Asks before one real grading call (cost shown first) and checks the
   structured result parses.
"""

import sys
from collections.abc import Callable

import live
import pricing

SAMPLE_QUESTION = "Explain how an LLM generates text."
SAMPLE_CHECKLIST = (
    "Says it predicts one token at a time",
    "Says it picks from a probability distribution",
)
SAMPLE_ANSWER = (
    "It predicts the next token from a probability distribution over its vocabulary, "
    "picks one, appends it, and repeats one token at a time until the answer is done."
)
LIVE_MODELS = (pricing.GRADER_MODEL, pricing.LIVE_TEMPERATURE_MODEL)


def run(status: live.LiveStatus, session, confirm: Callable[[str], bool]) -> int:
    if not status.available or session is None:
        print(f"Live mode is off: {status.source}.")
        return 1
    print(f"Credential: {status.source}")
    for model_id in LIVE_MODELS:
        count = session.count_tokens(SAMPLE_ANSWER, model_id)
        if count is None:
            print(f"FAIL  {model_id}: {session.last_error}")
            return 1
        print(f"OK    {model_id}: count_tokens = {count} (free)")
    if not confirm(f"Run one real grading call on {pricing.GRADER_MODEL}? (~{pricing.GRADE_COST_HINT})"):
        print("Grading skipped. Model checks passed.")
        return 0
    result = session.grade(SAMPLE_QUESTION, SAMPLE_CHECKLIST, SAMPLE_ANSWER)
    if result is None:
        print(f"FAIL  grading: {session.last_error}")
        return 1
    print(f"OK    grading: {result.met_count}/{len(SAMPLE_CHECKLIST)} met. Feedback: {result.feedback}")
    print(f"All live checks passed. Session spent ${session.spent:.4f}.")
    return 0


def _confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


def main() -> int:
    status = live.detect()
    session = live.LiveSession(status) if status.available else None
    try:
        return run(status, session, _confirm)
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
