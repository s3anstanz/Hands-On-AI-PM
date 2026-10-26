"""Optional features that call Claude: official token counts, the real
temperature run, and grading. Off unless a credential is found; every failure
falls back to the offline path with a short reason.
"""

import importlib.util
import json
import os
from dataclasses import dataclass
from pathlib import Path

import costs
import pricing

GRADE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"item": {"type": "string"}, "met": {"type": "boolean"}, "why": {"type": "string"}},
                "required": ["item", "met", "why"],
                "additionalProperties": False,
            },
        },
        "feedback": {"type": "string"},
    },
    "required": ["items", "feedback"],
    "additionalProperties": False,
}

GRADE_SYSTEM = (
    "You grade a product manager's practice answer to a question about building with LLMs. "
    "For each checklist item, in order, decide strictly whether the answer clearly covers it. "
    "In `why`, quote or paraphrase the part of the answer that covers it, or say what is missing. "
    "`feedback` is one sentence: the single most useful improvement."
)

TEMPERATURE_SYSTEM = "Complete the user's sentence with exactly one word. Reply with only that word."


@dataclass(frozen=True)
class LiveStatus:
    available: bool
    source: str  # how the credential was found, or why live mode is off


@dataclass(frozen=True)
class GradeItem:
    item: str
    met: bool
    why: str


@dataclass(frozen=True)
class GradeResult:
    items: tuple[GradeItem, ...]
    feedback: str

    @property
    def met_count(self) -> int:
        return sum(item.met for item in self.items)


def _config_dir(env) -> Path:
    if env.get("ANTHROPIC_CONFIG_DIR"):
        return Path(env["ANTHROPIC_CONFIG_DIR"])
    return Path.home() / ".config" / "anthropic"


def detect(env=None, offline: bool = False, sdk_installed: bool | None = None) -> LiveStatus:
    """Decide live mode without any network call."""
    env = os.environ if env is None else env
    if offline:
        return LiveStatus(False, "--offline")
    config_dir = _config_dir(env)
    if env.get("ANTHROPIC_API_KEY"):
        source = "ANTHROPIC_API_KEY"
    elif env.get("ANTHROPIC_AUTH_TOKEN"):
        source = "ANTHROPIC_AUTH_TOKEN"
    elif (
        env.get("ANTHROPIC_PROFILE")
        or (config_dir / "active_config").exists()
        or (config_dir / "configs" / "default.json").exists()
    ):
        source = "ant profile"
    else:
        return LiveStatus(False, "no API key found")
    installed = importlib.util.find_spec("anthropic") is not None if sdk_installed is None else sdk_installed
    if not installed:
        return LiveStatus(False, "anthropic package not installed: pip install -r requirements-live.txt")
    return LiveStatus(True, source)


def friendly_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    if status == 401:
        return "the API key was rejected"
    if status == 403:
        return "this key doesn't have access to that model"
    if status == 404:
        return "that model isn't available (it may have been retired)"
    if status == 429:
        return "rate limited; try again in a minute"
    if isinstance(status, int) and status >= 500:
        return "Anthropic's API had a temporary problem"
    name = type(exc).__name__
    if "Connection" in name or "Timeout" in name:
        return "couldn't reach the API (no network?)"
    return f"{name}: {exc}"


def _first_text(response) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise ValueError("response had no text block")


class LiveSession:
    def __init__(self, status: LiveStatus, client=None) -> None:
        self.status = status
        self._client = client
        self.spent = 0.0
        self.last_error = ""

    def _get_client(self):
        if self._client is None:
            import anthropic  # optional dependency: only imported in live mode

            self._client = anthropic.Anthropic(max_retries=1, timeout=30.0)
        return self._client

    def _charge(self, api_id: str, usage) -> None:
        model = pricing.by_api_id(api_id)
        self.spent += costs.request_cost(
            model, costs.Usage(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)
        ).total

    def count_tokens(self, text: str, model_id: str) -> int | None:
        try:
            result = self._get_client().messages.count_tokens(
                model=model_id, messages=[{"role": "user", "content": text}]
            )
            return result.input_tokens
        except Exception as exc:  # any API/network failure → offline estimate
            self.last_error = friendly_error(exc)
            return None

    def temperature_run(
        self, prompt: str, temperature: float, n: int, model_id: str = pricing.LIVE_TEMPERATURE_MODEL
    ) -> list[str]:
        """The answers, in order. Fewer than `n` means a call failed: the ones already paid for are kept and
        `last_error` says why (it is empty after a full run)."""
        if not pricing.by_api_id(model_id).accepts_temperature:
            raise ValueError(f"{model_id} rejects custom temperature (spec §10.1)")
        self.last_error = ""
        answers: list[str] = []
        try:
            client = self._get_client()
            for _ in range(n):
                response = client.messages.create(
                    model=model_id,
                    max_tokens=5,
                    system=TEMPERATURE_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                    # SDK v1.0+ removed `temperature` from the signature; older models accept it in the body.
                    extra_body={"temperature": temperature},
                )
                self._charge(model_id, response.usage)
                answers.append(_first_text(response).strip())
        except Exception as exc:  # any API/network failure → keep what came back
            self.last_error = friendly_error(exc)
        return answers

    def grade(self, question: str, checklist: tuple[str, ...], answer: str) -> GradeResult | None:
        numbered = "\n".join(f"{i}. {item}" for i, item in enumerate(checklist, 1))
        prompt = f"Question: {question}\n\nChecklist:\n{numbered}\n\nPM's answer:\n{answer}"
        try:
            response = self._get_client().messages.create(
                model=pricing.GRADER_MODEL,
                max_tokens=1500,
                system=GRADE_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_config={"format": {"type": "json_schema", "schema": GRADE_SCHEMA}},
            )
            self._charge(pricing.GRADER_MODEL, response.usage)
            payload = json.loads(_first_text(response))
            items = tuple(GradeItem(str(x["item"]), bool(x["met"]), str(x["why"])) for x in payload["items"])
            if len(items) != len(checklist):
                raise ValueError(f"expected {len(checklist)} graded items, got {len(items)}")
            return GradeResult(items, str(payload["feedback"]))
        except Exception as exc:  # any API/parse failure → self-score only
            self.last_error = friendly_error(exc)
            return None
