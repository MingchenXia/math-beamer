# Math Beamer

Math Beamer turns a structured English mathematics talk into an editable LaTeX Beamer project and PDF. It includes a 16:9 Madrid-based theme with distinct colors for examples, questions, and emphasis.

## Quick start

Use Python 3.10 or newer. For PDF output, install `pdflatex` and `latexmk` with a TeX distribution that includes Beamer, Babel English, and Latin Modern. On Debian or Ubuntu, the relevant packages are `latexmk lmodern texlive-latex-recommended texlive-pictures`.

```sh
git clone https://github.com/MingchenXia/math-beamer.git
cd math-beamer
python -m pip install .
math-beamer init talk.json
math-beamer check talk.json
math-beamer build talk.json
```

Edit `talk.json` to supply your English text, formulas, and figures. `build` writes `build/main.tex`, the theme, referenced figures, and `build/main.pdf`. With `--tex-only`, you can generate the source project without installing TeX. To use it on Overleaf, upload the generated files together, keep the `figures/` directory, and select pdfLaTeX.

Try the [14-minute lattice-point talk](examples/lattice-points.json). It has seven content frames, one figure, one outline, a title, and a closing frame. The two pauses add two PDF pages during projection. Use a separate directory for the handout.

```sh
math-beamer build examples/lattice-points.json -o build/slides
math-beamer build examples/lattice-points.json --handout -o build/handout
```

## Write a talk

The top-level fields are `title`, `author`, `minutes`, and `sections`. You can also set `affiliation`, `date`, and `outline` (on by default). A section has a `title` and a nonempty array of `frames`. A content frame looks like this.

```json
{
  "title": "Count one row at a time",
  "level": "elementary",
  "style": "example",
  "body": [
    {"text": "The bottom row has five points."},
    {"pause": true},
    {"text": "Move one row up and **lose one point** each time."},
    {"equation": "5+4+3+2+1=15."}
  ]
}
```

- Set `level` to `elementary`, `standard`, or `technical`. Use `example`, `theorem`, or `question` for a labeled block. The default style is `plain`.
- Use `text` or `bullet` for a short projected line. Use `$...$` for inline LaTeX math and `**...**` for emphasis, which produces Beamer's `\alert`. Use one `equation` item per display and double each LaTeX backslash in JSON, as in `{"equation": "N(k)=\\frac{(k+1)(k+2)}{2}"}`.
- Place at most one `{"pause": true}` between visible items when the audience needs time to think. Add an optional `notes` string for what you plan to say. Notes are stored in the generated source.
- Give a figure frame `"kind": "figure"`, a title, a level, and an `image` path relative to the JSON file. PDF, PNG, JPG, and JPEG are supported. Use `caption` for an optional one-line explanation.
- Start with a question or a small case the audience can work out. Give each frame one job. Introduce notation where it becomes useful, show the main theorem with its hypotheses, and use the proof sketch to explain the idea. Return to the opening example near the end. [Felix Gotti, Writing Beamer Presentations](https://math.mit.edu/~fgotti/writing-presentations.html), [AMS, Communicating Mathematics to a Broader Audience](https://blogs.ams.org/mathgradblog/2018/03/16/communicating-mathematics-broader-audience/).

## Validation

| Rule | Behavior |
|---|---|
| Timing | At most `floor(minutes / 2)` content frames. Figure, outline, title, and thank-you frames are exempt. Overlays share the same Beamer frame. |
| Text | Up to six visible text rows including the frame title and any block heading. Footers and text baked into images are outside the row count. The outline can therefore list up to five sections. |
| Formulas | Up to two display entries per frame. Every display counts. Put independent equations in separate entries. |
| Opening | The first third of content frames, rounded up, must be elementary. Any figure shown before the end of that opening also needs the elementary level. A missing worked example triggers a warning. |
| Technical material | At most five frames marked technical across the full talk, including figures. |
| Density | A frame has eight layout rows available. Each displayed equation uses two. PDF builds also reject overwide rows, equations, and LaTeX box overflows. |

`check` validates the structure and math markup without LaTeX. Run a PDF build to check rendered widths. English wording, mathematical correctness, and the difficulty labels are editorial decisions. Review those and the figures when rehearsing. For Beamer's behavior around frames, overlays, and handouts, see the [Beamer user guide](https://ctan.net/macros/latex/contrib/beamer/doc/beameruserguide.pdf).

## Python API

```python
from mathbeamer import build, render

deck = render("talk.json")
print(deck.talk.content_frames, deck.talk.warnings)
build("talk.json", "build/handout", handout=True)
```

`load_talk` returns the validated talk model. `render` also returns LaTeX source and the figure paths. `build` writes the project. These calls raise `TalkError` for an invalid talk or a failed TeX build. Compile math markup and figures from sources you trust.

## Development

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

The PDF integration tests use `latexmk`, `pdflatex`, and Poppler's `pdfinfo` and `pdftotext`. The example diagram can be rebuilt with `pdflatex -output-directory=examples examples/triangle.tex` using TikZ and the LaTeX `standalone` package.

Released under the [MIT License](LICENSE).
