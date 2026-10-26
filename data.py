"""Load and validate the hand-editable TOML files in data/.

Every problem raises DataError naming the file and the entry, so a typo in a
data file produces one readable line instead of a traceback.
"""

import math
import random
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
MIN_PROMPTS = 30
MIN_CANDIDATES = 3
MIN_HALLUCINATIONS = 5
HALLUCINATION_TAGS = ("general", "product", "medical")
MIN_SCENARIOS = 6
DOMAINS = ("general", "medical", "legal")
LATENCIES = ("interactive", "background")
MIN_SCENARIO_FOLLOWUPS = 3
SCENARIO_RANGES = ("users", "requests_per_user", "input_tokens", "output_tokens", "system_tokens", "docs_tokens")
KEBAB = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
FIGURE = re.compile(r"\{([a-z_]+)\}")  # {output_times} in rubric text: a figure the chapter computes


class DataError(ValueError):
    """A data file is malformed. The message says which file and entry."""


@dataclass(frozen=True)
class PromptTable:
    text: str
    tag: str
    weights: dict[str, float]
    continuation: tuple[dict[str, float], ...] = ()


@dataclass(frozen=True)
class FollowUp:
    question: str
    strong: str


@dataclass(frozen=True)
class ChapterRubric:
    question: str
    checklist: tuple[str, ...]
    followups: tuple[FollowUp, ...]
    hint: str  # short cues shown when the user types h at the answer
    sample_answer: str  # shown after grading

    def _texts(self) -> list[str]:
        followups = (text for f in self.followups for text in (f.question, f.strong))
        return [self.question, *self.checklist, *followups, self.hint, self.sample_answer]

    def figure_names(self) -> set[str]:
        """The {name} placeholders in this rubric. Each one is a figure its chapter computes from pricing.py."""
        return {name for text in self._texts() for name in FIGURE.findall(text)}

    def filled(self, figures: Mapping[str, str]) -> "ChapterRubric":
        """This rubric with each {name} replaced by the chapter's figure, so prices stay in pricing.py."""

        def fill(text: str) -> str:
            return FIGURE.sub(lambda m: figures.get(m[1], m[0]), text)

        return replace(
            self,
            question=fill(self.question),
            checklist=tuple(fill(item) for item in self.checklist),
            followups=tuple(FollowUp(fill(f.question), fill(f.strong)) for f in self.followups),
            hint=fill(self.hint),
            sample_answer=fill(self.sample_answer),
        )


@dataclass(frozen=True)
class GlossaryTerm:
    term: str
    definition: str
    chapter: str


@dataclass(frozen=True)
class Hallucination:
    """A prompt whose most likely answer is wrong until the prompt gets the fact (Chapter 4)."""

    prompt: str
    tag: str  # one of HALLUCINATION_TAGS
    answer: str  # the right answer: a candidate in both tables, on top only with context
    without: dict[str, float]  # odds with no context: a wrong answer on top
    context: str  # the line added to the prompt
    with_context: dict[str, float]  # odds once the context is in the prompt


@dataclass(frozen=True)
class Workload:
    """One run's usage numbers for a scenario. Token counts are per request."""

    users: int  # daily active users
    requests_per_user: int  # per user per day
    input_tokens: int  # system prompt + history + question
    output_tokens: int
    system_tokens: int  # the fixed, cacheable start of input_tokens
    docs_tokens: int  # all the reference material, if it were pasted in

    @property
    def requests_per_day(self) -> int:
        return self.users * self.requests_per_user


def two_figures(value: float) -> int:
    """12,345 -> 12,000: random draws read as estimates, not measurements."""
    whole = max(1, round(value))
    return round(whole, 2 - len(str(whole))) if whole >= 100 else whole


def _log_uniform(rng: random.Random, low: int, high: int) -> float:
    return math.exp(rng.uniform(math.log(low), math.log(high)))


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    pitch: str
    users: tuple[int, int]  # [low, high] ranges, drawn fresh each run
    requests_per_user: tuple[int, int]
    input_tokens: tuple[int, int]
    output_tokens: tuple[int, int]
    system_tokens: tuple[int, int]
    docs_tokens: tuple[int, int]
    # Chapter 8 (the loader requires all four; the defaults keep hand-built test scenarios short)
    domain: str = "general"  # "general" | "medical" | "legal"
    needs_facts: bool = True  # does a good answer depend on facts the model has to be given?
    latency: str = "interactive"  # "interactive" (someone is waiting) | "background"
    followups: tuple[FollowUp, ...] = ()

    def draw(self, rng: random.Random) -> Workload:
        """This run's numbers. Users and documents span orders of magnitude, so they're drawn on a log scale."""
        users = two_figures(_log_uniform(rng, *self.users))
        requests_per_user = rng.randint(*self.requests_per_user)
        input_tokens = two_figures(rng.uniform(*self.input_tokens))
        output_tokens = two_figures(rng.uniform(*self.output_tokens))
        system_tokens = min(input_tokens, two_figures(rng.uniform(*self.system_tokens)))
        docs_tokens = two_figures(_log_uniform(rng, *self.docs_tokens))
        return Workload(users, requests_per_user, input_tokens, output_tokens, system_tokens, docs_tokens)


@dataclass(frozen=True)
class Bundle:
    prompts: list[PromptTable]
    rubrics: dict[str, ChapterRubric]
    glossary: list[GlossaryTerm]
    hallucinations: list[Hallucination] = field(default_factory=list)
    scenarios: list[Scenario] = field(default_factory=list)


def _read(name: str, data_dir: Path) -> dict:
    path = data_dir / name
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        raise DataError(f"{name}: file not found in {data_dir}") from None
    except tomllib.TOMLDecodeError as exc:
        raise DataError(f"{name}: not valid TOML ({exc})") from None
    except UnicodeDecodeError:
        raise DataError(f"{name}: not valid UTF-8 text") from None


def _text(name: str, where: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataError(f"{name}: {where} is missing text")
    return value.strip()


def _weights(name: str, where: str, table: object) -> dict[str, float]:
    if not isinstance(table, dict) or len(table) < MIN_CANDIDATES:
        raise DataError(f"{name}: {where} needs at least {MIN_CANDIDATES} candidates")
    for word, weight in table.items():
        if not word.strip():
            raise DataError(f"{name}: {where} has a blank candidate")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0 < weight < math.inf:
            raise DataError(f"{name}: {where}: weight for {word!r} must be a positive number")
        try:
            float(weight)
        except OverflowError:
            raise DataError(f"{name}: {where}: weight for {word!r} is too large; use a smaller number") from None
    if not math.isfinite(sum(table.values())):
        raise DataError(f"{name}: {where}: weights are too large to add up; use smaller numbers")
    return {word: float(weight) for word, weight in table.items()}


def _unique_top(name: str, where: str, weights: dict[str, float]) -> None:
    ranked = sorted(weights.values(), reverse=True)
    if ranked[0] == ranked[1]:
        raise DataError(f"{name}: {where} needs one clear top candidate; two share the highest weight")


def load_prompts(data_dir: Path = DATA_DIR) -> list[PromptTable]:
    name = "prompts.toml"
    prompts: list[PromptTable] = []
    seen: set[str] = set()
    entries = _read(name, data_dir).get("prompt", [])
    if not isinstance(entries, list):
        raise DataError(f"{name}: 'prompt' must be a list of [[prompt]] tables")
    for i, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise DataError(f"{name}: prompt #{i} must be a [[prompt]] table")
        raw_text = entry.get("text")
        label = raw_text.strip() if isinstance(raw_text, str) and raw_text.strip() else "no text"
        where = f"prompt #{i} ({label})"
        text = _text(name, where, raw_text)
        if text in seen:
            raise DataError(f"{name}: {where} is a duplicate")
        seen.add(text)
        weights = _weights(name, where, entry.get("tokens"))
        steps = entry.get("continuation", [])
        if not isinstance(steps, list):
            raise DataError(f"{name}: {where} continuation must be a list of tables")
        chain = [_weights(name, f"{where} continuation step {j}", step) for j, step in enumerate(steps, start=1)]
        _unique_top(name, where, weights)  # Chapter 1 picks the winner; Chapter 3 asks about "the" top word
        for j, step in enumerate(chain, start=1):
            _unique_top(name, f"{where} continuation step {j}", step)
        prompts.append(PromptTable(text, str(entry.get("tag", "")), weights, tuple(chain)))
    if len(prompts) < MIN_PROMPTS:
        raise DataError(f"{name}: needs at least {MIN_PROMPTS} prompts, found {len(prompts)}")
    if not any(p.continuation for p in prompts):
        raise DataError(f"{name}: needs at least one prompt with a continuation chain (Chapter 1's demo uses them)")
    return prompts


def _followups(name: str, where: str, raw: object, minimum: int) -> tuple[FollowUp, ...]:
    if not isinstance(raw, list) or len(raw) < minimum:
        raise DataError(f"{name}: {where} needs at least {minimum} follow-ups")
    followups = []
    for k, followup in enumerate(raw, 1):
        if not isinstance(followup, dict):
            raise DataError(f"{name}: {where} follow-up {k} must be a table")
        followups.append(
            FollowUp(
                _text(name, f"{where} follow-up {k} question", followup.get("question")),
                _text(name, f"{where} follow-up {k} strong", followup.get("strong")),
            )
        )
    return tuple(followups)


def load_rubrics(data_dir: Path = DATA_DIR) -> dict[str, ChapterRubric]:
    name = "checklists.toml"
    rubrics: dict[str, ChapterRubric] = {}
    chapters = _read(name, data_dir).get("chapter", {})
    if not isinstance(chapters, dict):
        raise DataError(f"{name}: 'chapter' must be a table")
    for chapter_id, entry in chapters.items():
        where = f"chapter {chapter_id}"
        if not isinstance(entry, dict):
            raise DataError(f"{name}: {where} must be a table")
        question = _text(name, f"{where} question", entry.get("question"))
        items = entry.get("checklist", [])
        if not isinstance(items, list) or len(items) < 3:
            raise DataError(f"{name}: {where} needs at least 3 checklist items")
        checklist = tuple(_text(name, f"{where} checklist item {k}", item) for k, item in enumerate(items, 1))
        followups = _followups(name, where, entry.get("followup", []), 2)
        hint = _text(name, f"{where} hint", entry.get("hint"))
        sample_answer = _text(name, f"{where} sample answer", entry.get("sample_answer"))
        rubrics[str(chapter_id)] = ChapterRubric(question, checklist, followups, hint, sample_answer)
    return rubrics


def load_glossary(data_dir: Path = DATA_DIR) -> list[GlossaryTerm]:
    name = "glossary.toml"
    terms: list[GlossaryTerm] = []
    seen: set[str] = set()
    entries = _read(name, data_dir).get("term", [])
    if not isinstance(entries, list):
        raise DataError(f"{name}: 'term' must be a list of [[term]] tables")
    for i, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise DataError(f"{name}: term #{i} must be a [[term]] table")
        term = _text(name, f"term #{i}", entry.get("term"))
        if term.lower() in seen:
            raise DataError(f"{name}: duplicate term {term.lower()!r}")
        seen.add(term.lower())
        terms.append(
            GlossaryTerm(
                term,
                _text(name, f"term #{i} ({term}) definition", entry.get("definition")),
                _text(name, f"term #{i} ({term}) chapter", entry.get("chapter")),
            )
        )
    return terms


def _top(weights: dict[str, float]) -> str | None:
    """The single most likely candidate, or None on a tie for the top."""
    ranked = sorted(weights, key=lambda word: weights[word], reverse=True)
    return None if weights[ranked[0]] == weights[ranked[1]] else ranked[0]


def load_hallucinations(data_dir: Path = DATA_DIR) -> list[Hallucination]:
    name = "hallucination.toml"
    cases: list[Hallucination] = []
    seen: set[str] = set()
    entries = _read(name, data_dir).get("case", [])
    if not isinstance(entries, list):
        raise DataError(f"{name}: 'case' must be a list of [[case]] tables")
    for i, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise DataError(f"{name}: case #{i} must be a [[case]] table")
        raw_prompt = entry.get("prompt")
        label = raw_prompt.strip() if isinstance(raw_prompt, str) and raw_prompt.strip() else "no prompt"
        where = f"case #{i} ({label})"
        prompt = _text(name, f"{where} prompt", raw_prompt)
        if prompt in seen:
            raise DataError(f"{name}: {where} is a duplicate")
        seen.add(prompt)
        tag = entry.get("tag")
        if tag not in HALLUCINATION_TAGS:
            raise DataError(f"{name}: {where} tag must be one of {', '.join(HALLUCINATION_TAGS)}")
        answer = _text(name, f"{where} answer", entry.get("answer"))
        without = _weights(name, f"{where} without", entry.get("without"))
        context = _text(name, f"{where} context", entry.get("context"))
        with_context = _weights(name, f"{where} with_context", entry.get("with_context"))
        for table_name, table in (("without", without), ("with_context", with_context)):
            if answer not in table:
                raise DataError(f"{name}: {where} answer {answer!r} must be one of the {table_name} candidates")
            if _top(table) is None:
                raise DataError(f"{name}: {where} {table_name} has a tie for the top candidate")
        if _top(without) == answer:
            raise DataError(f"{name}: {where} without context, a wrong answer must be the most likely")
        if _top(with_context) != answer:
            raise DataError(f"{name}: {where} with context, the right answer must be the most likely")
        if with_context[answer] / sum(with_context.values()) < 0.5:
            # Chapter 4 says adding the fact cuts mistakes sharply; a narrow first place wouldn't show that.
            raise DataError(f"{name}: {where} with context, the right answer needs at least half the odds")
        cases.append(Hallucination(prompt, str(tag), answer, without, context, with_context))
    if len(cases) < MIN_HALLUCINATIONS:
        raise DataError(f"{name}: needs at least {MIN_HALLUCINATIONS} cases, found {len(cases)}")
    if not any(c.tag == "medical" for c in cases) or all(c.tag == "medical" for c in cases):
        raise DataError(f"{name}: needs at least one medical case and one other case (Chapter 4 uses both)")
    return cases


def _range(name: str, where: str, value: object) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in value)
        or value[0] > value[1]
    ):
        raise DataError(f"{name}: {where} must be [low, high]: two positive whole numbers, low first")
    return (value[0], value[1])


def _one_of(name: str, where: str, value: object, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise DataError(f"{name}: {where} must be one of: {', '.join(allowed)}")
    return str(value)


def _needs_facts(name: str, where: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise DataError(f"{name}: {where} needs_facts must be true or false")
    return value


def load_scenarios(data_dir: Path = DATA_DIR) -> list[Scenario]:
    name = "scenarios.toml"
    scenarios: list[Scenario] = []
    seen: set[str] = set()
    entries = _read(name, data_dir).get("scenario", [])
    if not isinstance(entries, list):
        raise DataError(f"{name}: 'scenario' must be a list of [[scenario]] tables")
    for i, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise DataError(f"{name}: scenario #{i} must be a [[scenario]] table")
        raw_id = entry.get("id")
        where = f"scenario #{i} ({raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else 'no id'})"
        scenario_id = _text(name, f"{where} id", raw_id)
        if not KEBAB.fullmatch(scenario_id):
            raise DataError(f"{name}: {where} id must be lowercase words joined by hyphens, like support-bot")
        if scenario_id in seen:
            raise DataError(f"{name}: {where} is a duplicate id")
        seen.add(scenario_id)
        ranges = {key: _range(name, f"{where} {key}", entry.get(key)) for key in SCENARIO_RANGES}
        if ranges["system_tokens"][1] > ranges["input_tokens"][1]:
            raise DataError(
                f"{name}: {where} system_tokens can't go above input_tokens: the system prompt is part of the input"
            )
        scenarios.append(
            Scenario(
                id=scenario_id,
                name=_text(name, f"{where} name", entry.get("name")),
                pitch=_text(name, f"{where} pitch", entry.get("pitch")),
                users=ranges["users"],
                requests_per_user=ranges["requests_per_user"],
                input_tokens=ranges["input_tokens"],
                output_tokens=ranges["output_tokens"],
                system_tokens=ranges["system_tokens"],
                docs_tokens=ranges["docs_tokens"],
                domain=_one_of(name, f"{where} domain", entry.get("domain"), DOMAINS),
                needs_facts=_needs_facts(name, where, entry.get("needs_facts")),
                latency=_one_of(name, f"{where} latency", entry.get("latency"), LATENCIES),
                followups=_followups(name, where, entry.get("followup", []), MIN_SCENARIO_FOLLOWUPS),
            )
        )
    if len(scenarios) < MIN_SCENARIOS:
        raise DataError(f"{name}: needs at least {MIN_SCENARIOS} scenarios, found {len(scenarios)}")
    return scenarios


def load_all(data_dir: Path = DATA_DIR) -> Bundle:
    return Bundle(
        prompts=load_prompts(data_dir),
        rubrics=load_rubrics(data_dir),
        glossary=load_glossary(data_dir),
        hallucinations=load_hallucinations(data_dir),
        scenarios=load_scenarios(data_dir),
    )
