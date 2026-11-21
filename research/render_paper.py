"""Render the editable Markdown paper with ReportLab.

Run from the checkout with: python research/render_paper.py
"""

from pathlib import Path
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/paper.md"
OUTPUT = ROOT / "output/pdf/adaptive_secondbrain_paper.pdf"
INK = colors.HexColor("#172822")
ACCENT = colors.HexColor("#245C4D")
MUTED = colors.HexColor("#485B53")
RULE = colors.HexColor("#CCE0D6")
PALE = colors.HexColor("#F2F7F4")
MARGIN = 59
CONTENT_WIDTH = letter[0] - 2 * MARGIN - 12

BODY = ParagraphStyle("Body", fontName="Times-Roman", fontSize=11.3, leading=15.4, textColor=INK, spaceAfter=8.5)
TITLE = ParagraphStyle("Title", fontName="Times-Bold", fontSize=39, leading=44, textColor=INK, spaceAfter=5)
SUBTITLE = ParagraphStyle("Subtitle", fontName="Times-Roman", fontSize=20, leading=24, textColor=ACCENT, spaceAfter=15)
META = ParagraphStyle("Meta", fontName="Helvetica", fontSize=9, leading=12, textColor=MUTED, spaceAfter=21)
HEADING = ParagraphStyle("Heading", fontName="Helvetica-Bold", fontSize=12.8, leading=16,
                         textColor=ACCENT, spaceBefore=9, spaceAfter=7, keepWithNext=True)
CAPTION = ParagraphStyle("Caption", parent=BODY, fontSize=10.25, leading=13.4, textColor=MUTED, spaceBefore=5)
REFERENCE = ParagraphStyle("Reference", parent=BODY, fontSize=9.7, leading=13.1, spaceAfter=6)
CELL = ParagraphStyle("Cell", parent=BODY, fontName="Helvetica", fontSize=8.9, leading=12, spaceAfter=0)
TABLE_HEADER = ParagraphStyle("TableHeader", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)


def inline(markdown):
    text = escape(markdown, {'"': '&quot;'})
    text = re.sub(r"\[([^\]]+)\]\((https://[^)]+)\)",
                  r'<link href="\2" color="#245C4D"><u>\1</u></link>', text)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def paper_table(lines):
    headings, _, *entries = [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]
    widths = {
        "Retrieval mode": (.24, .13, .13, .15, .35),
        "Ingestion comparison": (.38, .20, .42),
        "Failure": (.29, .71),
        "Follow-up condition": (.25, .24, .22, .13, .16),
    }[headings[0]]
    cells = [[Paragraph(inline(h), TABLE_HEADER) for h in headings]]
    cells.extend([Paragraph(inline(cell), CELL) for cell in row] for row in entries)
    table = Table(cells, colWidths=[CONTENT_WIDTH * width for width in widths], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PALE, colors.white]),
        ("LINEBELOW", (0, -1), (-1, -1), .6, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def paper_flow(markdown):
    result = []
    for block in re.split(r"\n\s*\n", markdown.strip()):
        if block == "<!-- pagebreak -->":
            result.append(PageBreak())
        elif block.startswith("|"):
            result.append(paper_table(block.splitlines()))
        elif block.startswith("# "):
            title, subtitle = block.splitlines()
            result.extend([Paragraph(inline(title[2:]), TITLE), Paragraph(inline(subtitle[3:]), SUBTITLE)])
        elif block.startswith("### "):
            result.append(Paragraph(inline(block[4:]), HEADING))
        else:
            style = BODY
            if block.startswith("Adaptive Second Brain project"):
                style = META
            elif block.startswith("**Table "):
                style = CAPTION
            elif re.match(r"^\[\d+\] ", block):
                style = REFERENCE
            result.append(Paragraph(inline(block.replace("\n", " ")), style))
    return result


def furniture(canvas, document):
    width, height = letter
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(.7)
    canvas.line(MARGIN + 6, height - 44, width - MARGIN - 6, height - 44)
    canvas.line(MARGIN + 6, 45, width - MARGIN - 6, 45)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8.5)
    canvas.drawString(MARGIN + 6, height - 33, "ADAPTIVE SECOND BRAIN")
    canvas.drawRightString(width - MARGIN - 6, height - 33, "SYSTEMS AND EVALUATION")
    canvas.drawString(MARGIN + 6, 31, "Adaptive Second Brain project | November 2026")
    canvas.drawRightString(width - MARGIN - 6, 31, str(document.page))
    canvas.restoreState()


def deterministic_canvas(*args, **kwargs):
    return Canvas(*args, **{**kwargs, "invariant": 1})


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=letter, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=57, bottomMargin=56, title="Adaptive Second Brain",
                            author="Adaptive Second Brain project",
                            subject="Local multimodal retrieval with verifiable source evidence")
    doc.build(paper_flow(SOURCE.read_text(encoding="utf-8")), onFirstPage=furniture,
              onLaterPages=furniture, canvasmaker=deterministic_canvas)
    print(OUTPUT)


if __name__ == "__main__":
    main()
