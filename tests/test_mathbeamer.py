import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from mathbeamer import TalkError, build, load_talk, render
from mathbeamer.cli import main

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples/lattice-points.json"


def content(title="A small example", level="elementary", **options):
    return {"title": title, "level": level, "body": [{"text": "A short line."}], **options}


class TalkTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / "talk.json"
        self.spec = {
            "title": "A test talk",
            "author": "A. Author",
            "minutes": 7,
            "sections": [{"title": "Motivation", "frames": [content(style="example")]}],
        }

    @property
    def frames(self):
        return self.spec["sections"][0]["frames"]

    def write_spec(self):
        self.source.write_text(json.dumps(self.spec), encoding="utf-8")
        return self.source

    def test_timing_excludes_figure_and_special_frames(self):
        shutil.copyfile(ROOT / "examples/triangle.pdf", self.root / "figure.pdf")
        self.frames.extend([
            {"kind": "figure", "title": "A figure", "level": "elementary", "image": "figure.pdf"},
            content("The next case", "standard"),
            content("The last case", "standard"),
        ])
        talk = load_talk(self.write_spec())
        self.assertEqual((talk.content_frames, talk.budget, talk.total_frames), (3, 3, 7))
        self.frames.append(content("Beyond the budget"))
        with self.assertRaisesRegex(TalkError, "4 content frames"):
            load_talk(self.write_spec())

    def test_opening_uses_rounded_up_third(self):
        self.spec["minutes"] = 8
        self.frames.extend([content(f"Frame {index}", "standard") for index in range(2, 5)])
        with self.assertRaisesRegex(TalkError, "Frame 2.*opening"):
            load_talk(self.write_spec())
        self.frames[1]["level"] = "elementary"
        self.assertEqual(load_talk(self.write_spec()).opening_frames, 2)

    def test_technical_limit(self):
        self.spec["minutes"] = 18
        self.frames.extend([content("An elementary case"), content("Another elementary case")])
        self.frames.extend([content(f"Detail {index}", "technical") for index in range(6)])
        with self.assertRaisesRegex(TalkError, "6 technical frames"):
            load_talk(self.write_spec())

    def test_visible_headings_count_toward_the_six_lines(self):
        self.frames[0]["body"] = [{"text": "A short line."}] * 4
        load_talk(self.write_spec())
        self.frames[0]["body"].append({"bullet": "One line too many."})
        with self.assertRaisesRegex(TalkError, "7 text lines"):
            load_talk(self.write_spec())

    def test_text_line_limit_can_be_relaxed_per_frame(self):
        self.frames[0]["body"] = [{"text": "A short line."}] * 6 + [{"equation": "1+1=2"}]
        self.frames[0]["text_line_limit"] = 8
        load_talk(self.write_spec())
        self.frames[0]["text_line_limit"] = 7
        with self.assertRaisesRegex(TalkError, "8 text lines"):
            load_talk(self.write_spec())
        self.frames[0]["text_line_limit"] = 9
        with self.assertRaisesRegex(TalkError, "integer from 6 to 8"):
            load_talk(self.write_spec())

    def test_two_equations_are_allowed_but_three_fail(self):
        self.frames[0]["body"] = [{"equation": "1+1=2"}, {"equation": "1+2=3"}]
        load_talk(self.write_spec())
        self.frames[0]["body"].append({"equation": "1+3=4"})
        with self.assertRaisesRegex(TalkError, "3 displayed equations"):
            load_talk(self.write_spec())

    def test_text_and_equations_share_a_density_budget(self):
        equations = [{"equation": "1+1=2"}, {"equation": "1+2=3"}]
        self.frames[0]["body"] = [{"text": "A short line."}] * 2 + equations
        load_talk(self.write_spec())
        self.frames[0]["body"].insert(0, {"text": "One more short line."})
        with self.assertRaisesRegex(TalkError, "too dense together"):
            load_talk(self.write_spec())

    def test_rich_text_uses_alert_and_preserves_backslashes_in_math(self):
        self.frames[0]["body"] = [
            {"text": r"Keep **only $x\leq 4$** & interpret 50%."},
            {"pause": True},
            {"equation": r"\begin{pmatrix}1&0\\0&1\end{pmatrix}"},
        ]
        tex = render(self.write_spec()).tex
        self.assertIn(r"\alert{only \(x\leq 4\)} \& interpret 50\%.", tex)
        self.assertIn(r"\pause", tex)
        self.assertIn(r"\begin{pmatrix}1&0\\0&1\end{pmatrix}", tex)

    def test_display_cannot_be_nested_in_inline_math(self):
        self.frames[0]["body"] = [{"text": r"Invalid $\[1+1=2\]$."}]
        with self.assertRaisesRegex(TalkError, "Unsupported math syntax"):
            render(self.write_spec())

    def test_figure_cannot_carry_a_content_body(self):
        self.frames[0].update(kind="figure", image="figure.pdf")
        del self.frames[0]["style"]
        with self.assertRaisesRegex(TalkError, "unknown fields: body"):
            load_talk(self.write_spec())

    def test_init_and_tex_only_bundle(self):
        starter = self.root / "starter.json"
        self.assertEqual(main(["init", str(starter)]), 0)
        self.assertEqual(render(starter).talk.content_frames, 3)
        output = self.root / "generated"
        deck = build(DEMO, output, tex_only=True)
        self.assertEqual(deck.talk.total_frames, 13)
        self.assertTrue((output / "beamerthememathbeamer.sty").is_file())
        self.assertTrue((output / "figures/figure-1.pdf").is_file())
        self.assertFalse((output / "main.pdf").exists())


@unittest.skipUnless(
    all(shutil.which(tool) for tool in ("latexmk", "pdflatex", "pdfinfo", "pdftotext")),
    "PDF tests require LaTeX and Poppler",
)
class PdfTests(unittest.TestCase):
    def test_demo_compiles_with_and_without_overlays(self):
        with TemporaryDirectory() as temporary:
            for handout, expected in ((False, 15), (True, 13)):
                with self.subTest(handout=handout):
                    output = Path(temporary) / str(handout)
                    build(DEMO, output, handout=handout)
                    pdf = output / "main.pdf"
                    info = subprocess.check_output(["pdfinfo", str(pdf)], text=True)
                    pages = next(line.split()[-1] for line in info.splitlines() if line.startswith("Pages:"))
                    self.assertEqual(int(pages), expected)
                    size = next(line.split() for line in info.splitlines() if line.startswith("Page size:"))
                    self.assertAlmostEqual(float(size[2]) / float(size[4]), 4 / 3, places=3)
                    text = subprocess.check_output(["pdftotext", "-layout", str(pdf), "-"], text=True)
                    self.assertIn("lose one point", text)
                    self.assertIn("Thank you", text)
                    self.assertEqual(text.count("Table of Contents"), 3)
                    frames = [part for part in text.split("\f") if part.strip()]
                    for frame in frames:
                        footer = frame.strip().splitlines()[-1]
                        self.assertIn("Math Beamer (Seminar)", footer)
                        self.assertIn("Lattice Points", footer)
                        self.assertIn("Nov. 18, 2026", footer)
                        self.assertRegex(footer, r"\d+\s*/\s*13\s*$")

    def test_long_title_uses_short_footer_text(self):
        data = {
            "title": "A long title about convex bodies and their asymptotic growth",
            "author": "A. Author",
            "minutes": 2,
            "sections": [{"title": "Motivation", "frames": [
                content(body=[{"text": "A short line."}] * 7, text_line_limit=8),
            ]}],
        }
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "talk.json"
            source.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(TalkError, "short_title"):
                build(source, root / "output")
            data["short_title"] = "Convex Bodies"
            source.write_text(json.dumps(data), encoding="utf-8")
            build(source, root / "output")
            self.assertTrue((root / "output/main.pdf").is_file())

    def test_pdf_build_rejects_a_line_that_cannot_fit(self):
        data = {
            "title": "A test talk",
            "author": "A. Author",
            "minutes": 2,
            "sections": [{"title": "Motivation", "frames": [
                content(body=[{"text": "A sentence that cannot fit. " * 12}]),
            ]}],
        }
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "talk.json"
            source.write_text(json.dumps(data), encoding="utf-8")
            render(source)
            with self.assertRaisesRegex(TalkError, "Line too wide"):
                build(source, root / "output")
            self.assertFalse((root / "output/main.tex").exists())


if __name__ == "__main__":
    unittest.main()
