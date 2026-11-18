"""Render a validated talk and compile it with latexmk."""

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from .model import Frame, Talk, TalkError, load_talk

ASSETS = files(__package__).joinpath("assets")
THEME = "beamerthememathbeamer.sty"
_ESCAPE = {
    key: "\\" + key for key in "#$%&_{}"
} | {"\\": r"\textbackslash{}", "^": r"\textasciicircum{}", "~": r"\textasciitilde{}"}
_INLINE = re.compile(r"\$([^$]+)\$|\*\*(.+?)\*\*")
_MATH_TOKENS = re.compile(r"\\(begin|end)\s*\{([a-zA-Z*]+)\}|\\[a-zA-Z]+|\\.|[{}%$#&]")
_MATH_ENVIRONMENTS = ("matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix", "smallmatrix", "cases")
_BLOCKS = {"example": ("exampleblock", "Example"), "theorem": ("block", "Theorem"),
           "question": ("alertblock", "Question")}
_FORBIDDEN_MATH = {
    r"\begin", r"\end", r"\(", r"\)", r"\[", r"\]", r"\emph", r"\alert", r"\pause",
    r"\only", r"\uncover", r"\visible", r"\onslide", r"\newline", r"\linebreak", r"\par",
    r"\input", r"\include", r"\includegraphics", r"\def", r"\gdef", r"\newcommand",
    r"\renewcommand", r"\catcode", r"\write", r"\read", r"\openout", r"\special", r"\csname",
}


@dataclass(frozen=True)
class Deck:
    """The generated source, its figures, and the validated talk statistics."""

    talk: Talk
    tex: str
    figures: tuple[tuple[str, Path], ...]


def _escape(text):
    return "".join(_ESCAPE.get(char, char) for char in text)


def _math(source):
    depth = 0
    environments = []
    for match in _MATH_TOKENS.finditer(source):
        token = match[0]
        if match[1] == "begin" and match[2] in _MATH_ENVIRONMENTS:
            environments.append(match[2])
        elif match[1] == "end" and environments and match[2] == environments[-1]:
            environments.pop()
        elif match[1] or token in _FORBIDDEN_MATH or token in ("$", "%", "#"):
            raise TalkError(f"Unsupported math syntax: {token}")
        elif token in (r"\\", "&") and not environments:
            raise TalkError("Put each display on its own equation entry. Use & or \\\\ inside matrices or cases.")
        elif token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
            if depth < 0:
                raise TalkError("Unbalanced braces in math")
    if depth or environments:
        raise TalkError("Unbalanced braces or environment in math")
    return source


def _plain_fragment(text):
    if "$" in text or "**" in text:
        raise TalkError("Unpaired inline math ($...$) or emphasis (**...**)")
    return _escape(text)


def _rich(text, allow_emphasis=True):
    pieces = []
    cursor = 0
    pattern = _INLINE if allow_emphasis else re.compile(r"\$([^$]+)\$")
    for match in pattern.finditer(text):
        pieces.append(_plain_fragment(text[cursor:match.start()]))
        if match[1] is not None:
            pieces.append(r"\(" + _math(match[1]) + r"\)")
        else:
            pieces.append(r"\alert{" + _rich(match[2], allow_emphasis=False) + "}")
        cursor = match.end()
    pieces.append(_plain_fragment(text[cursor:]))
    return "".join(pieces)


def _frame_tex(frame: Frame, figure: str | None) -> list[str]:
    lines = [r"\begin{frame}{" + _rich(frame.title) + "}"]
    if figure:
        lines.extend([
            r"\centering",
            r"\includegraphics[width=.95\linewidth,height=.65\textheight,keepaspectratio]{" + figure + "}",
        ])
        if frame.caption:
            lines.append(r"{\centering\small\MathBeamerLine{" + _rich(frame.caption) + r"}\par}")
    else:
        if frame.style in _BLOCKS:
            environment, label = _BLOCKS[frame.style]
            lines.append(r"\begin{" + environment + "}{" + label + "}")
        commands = {"text": "Line", "bullet": "Bullet", "equation": "Equation"}
        for item in frame.items:
            if item.kind == "pause":
                lines.append(r"\pause")
            else:
                value = _math(item.value) if item.kind == "equation" else _rich(item.value)
                lines.append(r"\MathBeamer" + commands[item.kind] + "{" + value + "}")
        if frame.style in _BLOCKS:
            lines.append(r"\end{" + environment + "}")
    if frame.notes:
        lines.append(r"\note{" + _rich(frame.notes) + "}")
    lines.append(r"\end{frame}")
    return lines


def _metadata(command, full, short):
    optional = "[{" + _escape(short) + "}]" if short else ""
    return "\\" + command + optional + "{" + _escape(full) + "}"


def render(source: str | Path, *, handout: bool = False) -> Deck:
    """Generate Beamer source from a structured talk without running TeX."""
    talk = load_talk(source)
    options = "[handout]" if handout else ""
    lines = [
        r"\documentclass" + options + "{beamer}",
        r"\usetheme{mathbeamer}",
        _metadata("title", talk.title, talk.short_title),
        _metadata("author", talk.author, talk.short_author),
        _metadata("institute", talk.affiliation, talk.short_affiliation),
        _metadata("date", talk.date, talk.short_date),
        "",
        r"\begin{document}",
        r"\begin{frame}",
        r"\titlepage",
        r"\end{frame}",
        "",
    ]
    figures = []
    for section in talk.sections:
        lines.extend([r"\section{" + _escape(section.title) + "}", ""])
        if talk.outline:
            lines.extend([
                r"\begin{frame}{Table of Contents}",
                r"\tableofcontents[currentsection]",
                r"\end{frame}",
                "",
            ])
        for frame in section.frames:
            figure = None
            if frame.image is not None:
                figure = f"figures/figure-{len(figures) + 1}{frame.image.suffix.lower()}"
                figures.append((figure, frame.image))
            try:
                lines.extend(_frame_tex(frame, figure))
            except TalkError as error:
                raise TalkError(f"Frame {frame.title!r}: {error}") from error
            lines.append("")
    lines.extend([
        r"\begin{frame}",
        r"\centering",
        r"{\fontsize{32}{38}\selectfont\bfseries Thank you!\par}",
        r"\end{frame}",
        r"\end{document}",
        "",
    ])
    return Deck(talk, "\n".join(lines), tuple(figures))


def _compile(directory):
    if not shutil.which("latexmk") or not shutil.which("pdflatex"):
        raise TalkError("PDF generation needs latexmk and pdflatex. Use build --tex-only for LaTeX sources.")
    try:
        result = subprocess.run(
            ["latexmk", "-norc", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
             "-pdflatex=pdflatex -no-shell-escape %O %S", "main.tex"],
            cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            errors="replace", timeout=120, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise TalkError("LaTeX compilation exceeded 120 seconds") from error
    if result.returncode:
        recent_output = "\n".join(result.stdout.splitlines()[-35:])
        raise TalkError("LaTeX compilation failed:\n" + recent_output)
    log = (directory / "main.log").read_text(encoding="utf-8", errors="replace")
    overflows = [line.strip() for line in log.splitlines() if line.startswith(("Overfull \\hbox", "Overfull \\vbox"))]
    if overflows:
        raise TalkError("LaTeX detected content overflow:\n" + "\n".join(overflows))


def build(source: str | Path, destination: str | Path, *, handout=False, tex_only=False) -> Deck:
    """Generate a portable source bundle and optionally compile its PDF."""
    deck = render(source, handout=handout)
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".math-beamer-", dir=destination) as temporary:
        staged = Path(temporary)
        (staged / "main.tex").write_text(deck.tex, encoding="utf-8")
        (staged / THEME).write_bytes(ASSETS.joinpath(THEME).read_bytes())
        generated = ["main.tex", THEME]
        for name, source_image in deck.figures:
            copied = staged / name
            copied.parent.mkdir(exist_ok=True)
            shutil.copyfile(source_image, copied)
            generated.append(name)
        if not tex_only:
            _compile(staged)
            generated.append("main.pdf")
        for name in generated:
            target = destination / name
            target.parent.mkdir(exist_ok=True)
            (staged / name).replace(target)
    return deck
