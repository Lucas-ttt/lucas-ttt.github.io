#!/usr/bin/env python3
"""Build the public one-page resume from its Markdown source.

Requires reportlab. Run from any directory with Python 3.12 or newer.
On systems without a supported Chinese font, set RESUME_CJK_FONT to an
embeddable TrueType font; RESUME_CJK_BOLD_FONT is optional.
"""

from __future__ import annotations

import argparse
from html import escape
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import textsplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from reportlab.platypus import paragraph as paragraph_layout


ROOT = Path(__file__).resolve().parents[1]
INK = colors.HexColor("#24352e")
ACCENT = colors.HexColor("#286b51")
MUTED = colors.HexColor("#5c6a63")
RULE = colors.HexColor("#d4ded7")
# ReportLab's default CJK break list is Japanese. Include fullwidth Chinese
# punctuation so a line cannot begin with a comma, semicolon or closing quote.
textsplit.ALL_CANNOT_START += "，。；：！？）》”’"
paragraph_layout.ALL_CANNOT_START += "，。；：！？）》”’"


def register_fonts() -> None:
    candidates = [
        os.environ.get("RESUME_CJK_FONT", ""),
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]
    regular = next((path for path in candidates if path and Path(path).is_file()), None)
    if not regular:
        raise SystemExit("Set RESUME_CJK_FONT to an embeddable Chinese TrueType font.")
    bold = os.environ.get("RESUME_CJK_BOLD_FONT")
    if not bold and Path("/System/Library/Fonts/STHeiti Medium.ttc").is_file():
        bold = "/System/Library/Fonts/STHeiti Medium.ttc"
    pdfmetrics.registerFont(TTFont("Resume", regular, subfontIndex=0))
    pdfmetrics.registerFont(TTFont("ResumeBold", bold or regular, subfontIndex=0))
    pdfmetrics.registerFontFamily(
        "Resume", normal="Resume", bold="ResumeBold", italic="Resume", boldItalic="ResumeBold"
    )


def inline(markdown: str) -> str:
    """Convert only the inline Markdown used by the resume, preserving links."""
    value = escape(markdown)
    value = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        r'<link href="\2" color="#286b51"><u>\1</u></link>',
        value,
    )
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"`([^`]+)`", r'<font color="#286b51">\1</font>', value)
    return value


def make_story(markdown: str, size: float) -> list:
    base = ParagraphStyle(
        "body", fontName="Resume", fontSize=size, leading=size * 1.45,
        textColor=INK, alignment=TA_LEFT, wordWrap="CJK", spaceAfter=5,
    )
    styles = {
        "body": base,
        "h1": ParagraphStyle(
            "name", parent=base, fontName="ResumeBold", fontSize=24, leading=30,
            textColor=INK, spaceAfter=4,
        ),
        "h2": ParagraphStyle(
            "section", parent=base, fontName="ResumeBold", fontSize=size + 1.5,
            leading=size + 6, textColor=ACCENT, spaceBefore=8, spaceAfter=4,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "project", parent=base, fontName="ResumeBold", fontSize=size + 0.5,
            leading=size + 5, spaceBefore=5, spaceAfter=4, keepWithNext=True,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=base, leftIndent=8, firstLineIndent=0,
            bulletIndent=0, bulletFontName="Resume", bulletFontSize=size - 1,
            spaceAfter=4,
        ),
        "meta": ParagraphStyle(
            "meta", parent=base, fontSize=size - 0.1, leading=size + 4,
            textColor=MUTED, spaceAfter=4,
        ),
    }
    story = []
    before_first_section = True
    for line in markdown.splitlines():
        line = line.strip()
        if not line or line.startswith("更新于 "):
            continue
        if line.startswith("# "):
            story.append(Paragraph(inline(line[2:]), styles["h1"]))
        elif line.startswith("## "):
            if before_first_section:
                story.append(Spacer(1, 4))
                story.append(HRFlowable(width="100%", thickness=0.7, color=RULE))
                before_first_section = False
            story.append(Paragraph(inline(line[3:]), styles["h2"]))
        elif line.startswith("### "):
            story.append(Paragraph(inline(line[4:]), styles["h3"]))
        elif line.startswith("- "):
            story.append(Paragraph(inline(line[2:]), styles["bullet"], bulletText="·"))
        else:
            kind = "meta" if before_first_section else "body"
            story.append(Paragraph(inline(line), styles[kind]))
    return story


def build(source: Path, destination: Path) -> float:
    markdown = source.read_text(encoding="utf-8")
    date_match = re.search(r"^更新于 (.+)$", markdown, flags=re.MULTILINE)
    updated = date_match.group(1) if date_match else ""
    title_match = re.search(r"^# (.+)$", markdown, flags=re.MULTILINE)
    title = title_match.group(1) if title_match else source.stem
    register_fonts()
    # Prefer a legible size. If edits no longer fit one page, stop rather than
    # silently discard content or shrink text below the minimum.
    with TemporaryDirectory(prefix="lucas-resume-") as folder:
        for size in (9.5, 9.25, 9.0, 8.75):
            target = Path(folder) / "resume.pdf"
            pages = []

            def footer(canvas, doc):
                pages.append(doc.page)
                canvas.saveState()
                canvas.setStrokeColor(RULE)
                canvas.setLineWidth(0.5)
                canvas.line(38, 32, A4[0] - 38, 32)
                canvas.setFont("Resume", 7.5)
                canvas.setFillColor(MUTED)
                if updated:
                    canvas.drawString(38, 20, f"更新于 {updated}")
                canvas.drawRightString(A4[0] - 38, 20, str(doc.page))
                canvas.restoreState()

            doc = SimpleDocTemplate(
                str(target), pagesize=A4, leftMargin=38, rightMargin=38,
                topMargin=30, bottomMargin=42, title=f"{title} | AI 应用开发",
                author=title, subject="个人项目实践与求职简历",
            )
            doc.build(make_story(markdown, size), onFirstPage=footer, onLaterPages=footer)
            if pages == [1]:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(target.read_bytes())
                return size
    raise SystemExit("Resume exceeds one A4 page. Edit the Markdown before rebuilding.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "public/downloads/lucas-ai-resume.md")
    parser.add_argument("--output", type=Path, default=ROOT / "public/downloads/lucas-ai-resume.pdf")
    args = parser.parse_args()
    size = build(args.source, args.output)
    print(f"Built {args.output} (one A4 page, body {size:g} pt)")


if __name__ == "__main__":
    main()
