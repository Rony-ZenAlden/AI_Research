"""Render a ResearchSession as Markdown or PDF.

Markdown is just composition. PDF goes Markdown → HTML → WeasyPrint with a
print-friendly stylesheet (light background, serif body, monospace citations).
"""
from __future__ import annotations

import logging
import re
from io import BytesIO

from .models import ResearchSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------
def render_markdown(session: ResearchSession) -> str:
    """Render a session as a self-contained Markdown document."""
    lines: list[str] = []
    lines.append(f"# {session.question}")
    lines.append("")

    meta_bits = [f"NeuroSeek AI research report"]
    if session.completed_at:
        meta_bits.append(session.completed_at.strftime("%Y-%m-%d %H:%M UTC"))
    if session.duration_ms:
        meta_bits.append(f"{session.duration_ms / 1000:.1f}s")
    lines.append("> " + " · ".join(meta_bits))
    lines.append("")

    body = (session.report_text or "").strip() or "_(no report content)_"
    lines.append(body)
    lines.append("")

    # If the model didn't include a References section, append our own.
    has_references_section = bool(re.search(r"^##\s+references\s*$", body, re.IGNORECASE | re.MULTILINE))
    if not has_references_section and session.report_sources:
        lines.append("---")
        lines.append("")
        lines.append("## References")
        for s in session.report_sources:
            idx = s.get("index")
            title = (s.get("title") or "(untitled)").strip()
            ref = (s.get("ref") or "").strip()
            if ref:
                lines.append(f"[{idx}] {title} — {ref}")
            else:
                lines.append(f"[{idx}] {title}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
PRINT_CSS = """
@page {
  size: A4;
  margin: 22mm 18mm;
  @bottom-right { content: counter(page) " / " counter(pages); font-size: 9pt; color: #666; }
  @bottom-left  { content: "NeuroSeek AI"; font-size: 9pt; color: #666; }
}
* { box-sizing: border-box; }
body {
  font-family: "DejaVu Serif", Georgia, serif;
  font-size: 11pt;
  line-height: 1.55;
  color: #111;
  background: #fff;
}
h1 {
  font-family: "DejaVu Sans", Arial, sans-serif;
  font-size: 22pt;
  margin: 0 0 4mm 0;
  color: #1a1a2e;
}
h2 {
  font-family: "DejaVu Sans", Arial, sans-serif;
  font-size: 14pt;
  margin: 8mm 0 3mm 0;
  padding-top: 4mm;
  border-top: 1px solid #ddd;
  color: #2a2a3e;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
h2:first-of-type { border-top: none; padding-top: 0; }
h3 { font-family: "DejaVu Sans", Arial, sans-serif; font-size: 12pt; margin: 6mm 0 2mm; }
.meta {
  font-family: "DejaVu Sans", Arial, sans-serif;
  font-size: 9pt;
  color: #666;
  border-left: 3px solid #6366f1;
  padding: 3mm 4mm;
  margin: 0 0 6mm 0;
  background: #f6f6fb;
}
ul, ol { margin: 2mm 0 2mm 6mm; }
li { margin-bottom: 1mm; }
.cite {
  font-family: "DejaVu Sans Mono", monospace;
  font-size: 9pt;
  font-weight: bold;
  color: #6366f1;
  padding: 0 2px;
}
table { border-collapse: collapse; width: 100%; margin: 3mm 0; font-size: 10pt; }
th, td { border: 1px solid #ccc; padding: 2mm 3mm; text-align: left; vertical-align: top; }
th { background: #eef0f7; font-family: "DejaVu Sans", Arial, sans-serif; }
hr { border: none; border-top: 1px solid #ccc; margin: 6mm 0; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 10pt; background: #f6f6fb; padding: 0 2px; }
.references { font-family: "DejaVu Sans Mono", monospace; font-size: 9pt; color: #333; }
.references li { word-break: break-all; }
"""


def render_pdf(session: ResearchSession) -> bytes:
    """Render the session report as a PDF (via WeasyPrint).

    Imports are local so the heavy WeasyPrint stack (Pango/Cairo) is only
    loaded when someone actually exports a PDF.
    """
    import markdown as md
    from weasyprint import CSS, HTML

    body_md = render_markdown(session)

    # Tag [N] citations so the print CSS can style them distinctly.
    def _cite_repl(m: re.Match) -> str:
        return f'<span class="cite">[{m.group(1)}]</span>'

    body_html = md.markdown(
        body_md,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    body_html = re.sub(r"\[(\d+)\]", _cite_repl, body_html)

    full_html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{(session.question or 'Research report')[:200]}</title>"
        "</head><body>" + body_html + "</body></html>"
    )

    buf = BytesIO()
    HTML(string=full_html).write_pdf(target=buf, stylesheets=[CSS(string=PRINT_CSS)])
    return buf.getvalue()
