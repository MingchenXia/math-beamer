"""The input format and the rules shared by the CLI and the Python API."""

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Literal

Style = Literal["plain", "theorem", "example", "question"]
Level = Literal["elementary", "standard", "technical"]
STYLES = ("plain", "theorem", "example", "question")
LEVELS = ("elementary", "standard", "technical")
TEXT_ITEMS = ("text", "bullet")
MAX_TEXT_LINES = 6
MAX_EQUATIONS = 2
MAX_TECHNICAL = 5
MAX_LAYOUT_ROWS = 8
IMAGE_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg")


class TalkError(ValueError):
    """An invalid talk specification or a build error."""


@dataclass(frozen=True)
class Item:
    kind: str
    value: str


@dataclass(frozen=True)
class Frame:
    title: str
    level: Level
    items: tuple[Item, ...] = ()
    style: Style = "plain"
    image: Path | None = None
    caption: str = ""
    notes: str = ""


@dataclass(frozen=True)
class Section:
    title: str
    frames: tuple[Frame, ...]


@dataclass(frozen=True)
class Talk:
    title: str
    author: str
    affiliation: str
    date: str
    outline: bool
    sections: tuple[Section, ...]
    content_frames: int
    budget: int
    opening_frames: int
    technical_frames: int
    warnings: tuple[str, ...]

    @property
    def total_frames(self) -> int:
        return 2 + int(self.outline) + sum(len(section.frames) for section in self.sections)


def _object(value, where, required, optional=()):
    if not isinstance(value, dict):
        raise TalkError(f"{where} must be an object")
    missing = sorted(set(required) - value.keys())
    unknown = sorted(value.keys() - set(required) - set(optional))
    if missing:
        raise TalkError(f"{where} is missing {', '.join(missing)}")
    if unknown:
        raise TalkError(f"{where} has unknown fields: {', '.join(unknown)}")
    return value


def _list(value, where):
    if not isinstance(value, list) or not value:
        raise TalkError(f"{where} must be a nonempty array")
    return value


def _line(value, where):
    if not isinstance(value, str) or not value.strip() or len(value.splitlines()) != 1:
        raise TalkError(f"{where} must be one nonempty line")
    if any(character.isspace() and character != " " for character in value):
        raise TalkError(f"{where} must use ordinary spaces")
    return value.strip()


def _choice(value, choices, where):
    if value not in choices:
        raise TalkError(f"{where} must be one of {', '.join(choices)}")
    return value


def _item(raw, where):
    if not isinstance(raw, dict) or len(raw) != 1:
        raise TalkError(f"{where} must contain exactly one item")
    kind, value = next(iter(raw.items()))
    if kind == "pause":
        if value is not True:
            raise TalkError(f"{where}.pause must be true")
        return Item(kind, "")
    if kind not in (*TEXT_ITEMS, "equation"):
        raise TalkError(f"{where} must be text, bullet, equation, or pause")
    return Item(kind, _line(value, f"{where}.{kind}"))


def _frame(raw, where, directory):
    if not isinstance(raw, dict):
        raise TalkError(f"{where} must be an object")
    kind = _choice(raw.get("kind", "content"), ("content", "figure"), f"{where}.kind")
    required = ("title", "level", "image" if kind == "figure" else "body")
    optional = ("kind", "notes", "caption" if kind == "figure" else "style")
    _object(raw, where, required, optional)
    title = _line(raw["title"], f"{where}.title")
    level = _choice(raw["level"], LEVELS, f"{where}.level")
    notes = _line(raw["notes"], f"{where}.notes") if "notes" in raw else ""
    label = f"Frame {title!r}"

    if kind == "figure":
        path = Path(_line(raw["image"], f"{label} image"))
        if path.is_absolute():
            raise TalkError(f"{label}: image must be a path relative to the talk file")
        path = (directory / path).resolve()
        if path.suffix.lower() not in IMAGE_SUFFIXES or not path.is_file():
            raise TalkError(f"{label}: expected an existing PDF, PNG, or JPEG image")
        caption = _line(raw["caption"], f"{label} caption") if "caption" in raw else ""
        return Frame(title, level, image=path, caption=caption, notes=notes)

    style = _choice(raw.get("style", "plain"), STYLES, f"{label} style")
    items = tuple(
        _item(item, f"{label} body item {index}")
        for index, item in enumerate(_list(raw["body"], f"{label} body"), 1)
    )
    pauses = [index for index, item in enumerate(items) if item.kind == "pause"]
    if len(pauses) > 1 or (pauses and pauses[0] in (0, len(items) - 1)):
        raise TalkError(f"{label}: use at most one pause, between visible items")
    text_lines = 1 + (style != "plain") + sum(item.kind in TEXT_ITEMS for item in items)
    equations = sum(item.kind == "equation" for item in items)
    if text_lines > MAX_TEXT_LINES:
        raise TalkError(f"{label}: {text_lines} text lines including headings (limit {MAX_TEXT_LINES})")
    if equations > MAX_EQUATIONS:
        raise TalkError(f"{label}: {equations} displayed equations (limit {MAX_EQUATIONS})")
    if text_lines + 2 * equations > MAX_LAYOUT_ROWS:
        raise TalkError(f"{label}: text and displays are too dense together. Move an item to another frame.")
    return Frame(title, level, items=items, style=style, notes=notes)


def _unique_object(pairs):
    values = {}
    for key, value in pairs:
        if key in values:
            raise TalkError(f"Repeated JSON key {key!r}")
        values[key] = value
    return values


def load_talk(source: str | Path) -> Talk:
    """Read a JSON talk and enforce its frame budget and structure."""
    source = Path(source).resolve()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, ValueError) as error:
        raise TalkError(f"{source}: {error}") from error

    _object(raw, "Talk", ("title", "author", "minutes", "sections"), ("affiliation", "date", "outline"))
    minutes = raw["minutes"]
    if (type(minutes) not in (int, float) or minutes <= 0
            or (isinstance(minutes, float) and not math.isfinite(minutes))):
        raise TalkError("minutes must be a positive, finite number")
    outline = raw.get("outline", True)
    if type(outline) is not bool:
        raise TalkError("outline must be true or false")

    sections = []
    for index, section in enumerate(_list(raw["sections"], "sections"), 1):
        where = f"Section {index}"
        _object(section, where, ("title", "frames"))
        frames = tuple(
            _frame(frame, f"{where}, frame {number}", source.parent)
            for number, frame in enumerate(_list(section["frames"], f"{where}.frames"), 1)
        )
        sections.append(Section(_line(section["title"], f"{where}.title"), frames))

    if outline and 1 + len(sections) > MAX_TEXT_LINES:
        raise TalkError(f"Outline has more than {MAX_TEXT_LINES - 1} entries")

    frames = [frame for section in sections for frame in section.frames]
    content = [frame for frame in frames if frame.image is None]
    budget = int(minutes // 2)
    count = len(content)
    if not 1 <= count <= budget:
        raise TalkError(f"{count} content frames for {minutes} minutes (expected 1 to {budget})")
    technical = sum(frame.level == "technical" for frame in frames)
    if technical > MAX_TECHNICAL:
        raise TalkError(f"{technical} technical frames (limit {MAX_TECHNICAL})")

    opening = (count + 2) // 3
    early = []
    for frame in frames:
        if frame.level != "elementary":
            raise TalkError(f"Frame {frame.title!r} is in the opening and must be elementary")
        if frame.image is None:
            early.append(frame)
            if len(early) == opening:
                break

    warnings = []
    if not any(frame.style == "example" for frame in early):
        warnings.append("Add a worked example to the elementary opening.")
    metadata = {
        field: _line(raw[field], field) if field in raw else ""
        for field in ("title", "author", "affiliation", "date")
    }
    return Talk(
        **metadata, outline=outline, sections=tuple(sections), content_frames=count,
        budget=budget, opening_frames=opening, technical_frames=technical, warnings=tuple(warnings),
    )
