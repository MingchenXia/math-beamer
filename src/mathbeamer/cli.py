"""Command-line entry point."""

import argparse
from pathlib import Path
import sys

from .latex import ASSETS, build, render
from .model import MAX_TECHNICAL, TalkError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate English Beamer talks in mathematics.")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="write an editable starter talk")
    init.add_argument("path", nargs="?", type=Path, default=Path("talk.json"))

    check = commands.add_parser("check", help="check the talk structure and LaTeX math markup")
    check.add_argument("source", type=Path)

    compile_talk = commands.add_parser("build", help="generate a self-contained LaTeX project and PDF")
    compile_talk.add_argument("source", type=Path)
    compile_talk.add_argument("-o", "--output", type=Path, default=Path("build"))
    compile_talk.add_argument("--tex-only", action="store_true", help="write sources without running TeX")
    compile_talk.add_argument("--handout", action="store_true", help="collapse pauses to one PDF page per frame")

    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            with args.path.open("x", encoding="utf-8") as destination:
                destination.write(ASSETS.joinpath("starter.json").read_text(encoding="utf-8"))
            print(f"Wrote {args.path}")
            return 0

        if args.command == "check":
            deck = render(args.source)
        else:
            deck = build(args.source, args.output, handout=args.handout, tex_only=args.tex_only)
            print(f"Wrote {args.output / 'main.tex'}")
            if not args.tex_only:
                print(f"Wrote {args.output / 'main.pdf'}")

        talk = deck.talk
        print(f"{talk.content_frames}/{talk.budget} content frames, {talk.total_frames} total frames, "
              f"{talk.opening_frames} elementary opening frames, "
              f"{talk.technical_frames}/{MAX_TECHNICAL} technical frames.")
        for warning in talk.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        return 0
    except (TalkError, OSError) as error:
        print(f"math-beamer: {error}", file=sys.stderr)
        return 1
