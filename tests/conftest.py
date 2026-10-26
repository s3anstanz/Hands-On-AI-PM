import webbrowser

import pytest

import feedback
import progress


@pytest.fixture(autouse=True)
def isolate_from_real_credentials(monkeypatch, tmp_path):
    """Tests never see a real Anthropic credential, so nothing can bill Sean."""
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path / "anthropic-config"))


@pytest.fixture(autouse=True)
def isolate_progress_file(monkeypatch, tmp_path):
    """Tests never touch ~/.config/hands-on-ai-pm/progress.json."""
    monkeypatch.setattr(progress, "PROGRESS_PATH", tmp_path / "progress.json")


@pytest.fixture(autouse=True)
def isolate_feedback_notes(monkeypatch, tmp_path):
    """Tests never touch ~/.config/hands-on-ai-pm/feedback/."""
    monkeypatch.setattr(feedback, "FEEDBACK_DIR", tmp_path / "feedback")


class FakeBrowser:
    def __init__(self) -> None:
        self.opened: list[str] = []
        self.works = True

    def open(self, url: str) -> bool:
        self.opened.append(url)
        return self.works


@pytest.fixture(autouse=True)
def browser(monkeypatch):
    """Tests never open a real browser. Request `browser` to see what would have opened."""
    fake = FakeBrowser()
    monkeypatch.setattr(webbrowser, "open", fake.open)
    return fake
