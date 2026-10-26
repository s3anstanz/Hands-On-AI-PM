import io
import re

from rich.console import Console

DEFAULT_ANSWER = "It predicts the next token from probabilities, one at a time."


class ScriptedIO:
    """Answers prompts by kind. `overrides[kind]` replies are used first, in order.

    The default replies drive a full run: Enter at every footer, option 1,
    'y' to yes/no, one-line answers to free text, no to the end-of-chapter
    feedback offer, an empty line to "optional" prompts, and for numbers the low
    end of the range shown.
    """

    def __init__(self, menu=("q",), width=100, overrides=None, max_calls=3000):
        self.console = Console(file=io.StringIO(), width=width, color_system=None, force_terminal=False)
        self.menu = list(menu)
        self.overrides = {kind: list(replies) for kind, replies in (overrides or {}).items()}
        self.prompts: list[tuple[str, str]] = []
        self.max_calls = max_calls
        self._in_multiline = False

    def ask(self, prompt: str, kind: str) -> str:
        self.prompts.append((kind, prompt))
        self.console.print(prompt, markup=False, highlight=False)  # a real terminal shows the prompt too
        if len(self.prompts) > self.max_calls:
            raise RuntimeError("too many prompts: is something looping?")
        if self.overrides.get(kind):
            return self.overrides[kind].pop(0)
        if kind == "menu":
            if not self.menu:
                raise EOFError
            return self.menu.pop(0)
        if kind in ("nav", "pause"):
            return ""
        if kind == "choice":
            return "1"
        if kind == "number":
            shown = re.search(r"\[(-?[\d.,]+)-(-?[\d.,]+)\]", prompt)
            return shown[1] if shown else "0.5"  # the low end, valid for whole-number and decimal prompts
        if kind == "optional":
            return ""
        if kind == "yesno":
            return "y"
        if kind == "offer":
            return "n"
        if kind == "multiline":
            self._in_multiline = not self._in_multiline
            return DEFAULT_ANSWER if self._in_multiline else ""
        raise ValueError(f"unknown prompt kind {kind!r}")

    @property
    def output(self) -> str:
        return self.console.file.getvalue()
