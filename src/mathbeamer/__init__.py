"""Generate and validate structured LaTeX Beamer talks."""

from .latex import Deck, build, render
from .model import Talk, TalkError, load_talk

__all__ = ["Deck", "Talk", "TalkError", "build", "load_talk", "render"]
