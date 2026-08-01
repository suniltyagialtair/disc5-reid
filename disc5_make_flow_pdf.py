# disc5_make_flow_pdf.py
# Renders DISC5_ReID_System_Flow.md to a styled PDF in the Oravont report house style
# (navy/teal headings, styled tables, "Oravont Systems LLP | Restricted | Page N of M"
# footer), with Figures 1-3 embedded as vector graphics.
#
# The .md is canonical; this PDF is a rendering driven by it and is never edited by hand.
#
#   python disc5_make_flow_pdf.py --src DISC5_ReID_System_Flow.md \
#                                 --out DISC5_ReID_System_Flow.pdf
#
# Pipeline: markdown -> HTML (python-markdown) + CSS paged media -> WeasyPrint. SVG figures
# in figures/ are embedded as vectors, untouched. Requires: pip install markdown weasyprint.

import argparse
import os
import re
import sys

import markdown

NAVY = "#1f3a5f"
TEAL = "#0e8a7d"
GREY = "#5b6672"

CSS = f"""
@page {{
    size: A4;
    margin: 20mm 16mm 18mm 16mm;
    @top-right {{ content: "DISC5 Re-ID System Flow";
                  font-family: 'Liberation Sans'; font-size: 8pt;
                  font-style: italic; color: {GREY}; }}
    @bottom-left {{ content: "Oravont Systems LLP";
                    font-family: 'Liberation Sans'; font-size: 8pt; color: {GREY}; }}
    @bottom-center {{ content: "Restricted";
                      font-family: 'Liberation Sans'; font-size: 8pt; color: {GREY}; }}
    @bottom-right {{ content: "Page " counter(page) " of " counter(pages);
                     font-family: 'Liberation Sans'; font-size: 8pt; color: {GREY}; }}
}}
body {{ font-family: 'Liberation Sans', Arial, sans-serif; font-size: 10pt;
        color: #1b2430; line-height: 1.5; }}
.brand {{ text-align: center; margin: 0 0 4px 0; }}
.brand .co {{ font-size: 20pt; font-weight: bold; color: {NAVY}; letter-spacing: 1px; }}
.brand .tag {{ font-size: 11pt; font-style: italic; color: {TEAL}; }}
h1 {{ font-size: 18pt; color: {NAVY}; text-align: center; margin: 12px 0 2px 0; }}
h2 {{ font-size: 13.5pt; color: {NAVY}; border-bottom: 2pt solid {NAVY};
      padding-bottom: 3px; margin-top: 20px; page-break-after: avoid; }}
h3 {{ font-size: 11pt; color: {TEAL}; margin-top: 13px; page-break-after: avoid; }}
table {{ border-collapse: collapse; width: 100%; margin: 9px 0;
         font-size: 9pt; page-break-inside: avoid; }}
th {{ background: {NAVY}; color: white; text-align: left; padding: 4px 7px; }}
td {{ border-bottom: 0.5pt solid #d7dde4; padding: 3.5px 7px; vertical-align: top; }}
tr:nth-child(even) td {{ background: #f4f6f9; }}
code {{ font-family: 'DejaVu Sans Mono', monospace; font-size: 8.4pt;
        background: #eef2f6; padding: 0 2px; }}
strong {{ color: #10233c; }}
div.figwrap {{ text-align: center; page-break-inside: avoid; margin: 10px 0; }}
img {{ max-width: 100%; }}
img.fig {{ max-width: 100%; }}
img.portrait {{ max-height: 236mm; width: auto; }}
hr {{ border: none; border-top: 0.5pt solid #c3cbd4; margin: 14px 0; }}
li {{ margin-bottom: 2px; }}
blockquote {{ border-left: 3pt solid {TEAL}; margin-left: 0; padding-left: 11px;
              color: {GREY}; }}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="DISC5_ReID_System_Flow.md")
    ap.add_argument("--out", default="DISC5_ReID_System_Flow.pdf")
    args = ap.parse_args()

    md_text = open(args.src, encoding="utf-8").read()
    base = os.path.dirname(os.path.abspath(args.src))
    html_body = markdown.markdown(md_text, extensions=["tables", "sane_lists"])

    # Wrap each SVG figure; portrait figures get a height cap so each sits on one page.
    def repl(m):
        src, alt = m.group("src"), m.group("alt")
        svg = os.path.join(base, src)
        if not os.path.exists(svg):
            sys.exit("missing figure: " + svg)
        head = open(svg, encoding="utf-8", errors="ignore").read(2000)
        mm = re.search(r'viewBox="[\d.\s-]*?([\d.]+)\s+([\d.]+)"', head)
        w, h = (float(mm.group(1)), float(mm.group(2))) if mm else (1.0, 1.0)
        cls = "fig portrait" if h > w else "fig"
        print(f"  {src}: {w:.0f}x{h:.0f}pt ({'portrait' if h > w else 'landscape'}), vector")
        return (f'<div class="figwrap"><img class="{cls}" alt="{alt}" src="{svg}"/></div>')

    html_body = re.sub(
        r'<img alt="(?P<alt>[^"]*)" src="(?P<src>[^"]+\.svg)"\s*/?>', repl, html_body)

    brand = ('<div class="brand"><div class="co">ORAVONT SYSTEMS</div>'
             '<div class="tag">Underwater Acoustic Intelligence</div></div>')
    html = (f"<html><head><meta charset='utf-8'><style>{CSS}</style></head>"
            f"<body>{brand}{html_body}</body></html>")

    from weasyprint import HTML
    HTML(string=html, base_url=base).write_pdf(args.out)
    print(f"wrote {args.out}  ({os.path.getsize(args.out):,} B)")


if __name__ == "__main__":
    main()
