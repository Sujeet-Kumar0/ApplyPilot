"""PDF rendering via Playwright headless Chromium."""

from __future__ import annotations

import logging
from pathlib import Path

import applypilot.scoring.pdf as _pdf_module
from applypilot.scoring.pdf.html_renderer import build_html, _load_skill_annotations
from applypilot.scoring.pdf.parser import parse_resume

log = logging.getLogger(__name__)


def render_pdf(html: str, output_path: str) -> None:
    """Render HTML to PDF using Playwright's headless Chromium."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        page.pdf(
            path=output_path,
            format="Letter",
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            print_background=True,
        )
        browser.close()


def convert_to_pdf(text_path: Path, output_path: Path | None = None, html_only: bool = False) -> Path:
    """Convert a text resume/cover letter to PDF."""
    text_path = Path(text_path)
    text = text_path.read_text(encoding="utf-8")
    resume = parse_resume(text)
    skill_annotations = _load_skill_annotations(text_path)
    html = build_html(resume, skill_annotations=skill_annotations)

    if html_only:
        out = Path(output_path or text_path.with_suffix(".html"))
        out.write_text(html, encoding="utf-8")
        log.info("HTML generated: %s", out)
        return out

    out = Path(output_path or text_path.with_suffix(".pdf"))
    render_pdf(html, str(out))
    log.info("PDF generated: %s", out)
    return out


def batch_convert(limit: int = 0) -> int:
    """Convert .txt files in _pdf_module.TAILORED_DIR that don't have corresponding PDFs."""
    if not _pdf_module.TAILORED_DIR.exists():
        return 0

    candidates = [f for f in sorted(_pdf_module.TAILORED_DIR.glob("*.txt")) if not f.name.endswith("_JOB.txt")]
    to_convert = [f for f in candidates if not f.with_suffix(".pdf").exists()]
    if limit > 0:
        to_convert = to_convert[:limit]
    if not to_convert:
        return 0

    log.info("Converting %d files to PDF...", len(to_convert))
    converted = 0

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            for f in to_convert:
                try:
                    resume = parse_resume(f.read_text(encoding="utf-8"))
                    html = build_html(resume)
                    out = f.with_suffix(".pdf")
                    page.set_content(html, wait_until="networkidle")
                    page.pdf(
                        path=str(out),
                        format="Letter",
                        margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                        print_background=True,
                    )
                    converted += 1
                except Exception as e:
                    log.error("Failed to convert %s: %s", f.name, e)
        finally:
            browser.close()
    return converted
