"""Public GET /privacy endpoint.

Serves the privacy statement (src/handlers/api/resources/privacy_statement.md) as rendered
HTML so customers can open it from a link in Telegram. The Markdown is converted
with the `markdown` library (tables + sane lists) and wrapped in a small styled
page.
"""

import base64
import logging
import os
from typing import Any

import markdown

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_BASE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "resources")
_STATEMENT_PATH = os.path.join(_BASE_DIR, "privacy_statement.md")
_LOGO_PATH = os.path.join(_BASE_DIR, "ubbc_logo.jpg")
_CACHE_TTL = 3600  # seconds; the statement changes rarely

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Privacyverklaring UBBC Bot</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; line-height: 1.6;
         max-width: 780px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
  h1, h2 {{ line-height: 1.25; }}
  h1 {{ font-size: 1.8rem; }}
  h2 {{ font-size: 1.3rem; margin-top: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left;
           vertical-align: top; }}
  th {{ background: #f4f4f4; }}
  code {{ background: #f0f0f0; padding: 0.1rem 0.3rem; border-radius: 3px;
          font-size: 0.9em; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 2rem 0; }}
  em {{ color: #555; }}
  .logo {{ position: fixed; top: 1rem; right: 1rem; width: 72px; height: auto;
           border-radius: 8px; }}
  @media (max-width: 900px) {{ .logo {{ position: static; display: block;
           margin: 0 0 1rem auto; }} }}
</style>
</head>
<body>
{logo}
{content}
</body>
</html>
"""


def _safe_open(path: str, mode: str):
    """Open a file only if it resolves to within this handler's directory.

    Defense in depth: the asset paths are fixed constants today, but this guard
    ensures that even a future change introducing a request-derived path cannot
    be used to read arbitrary files (path traversal) outside _BASE_DIR.
    """
    resolved = os.path.realpath(path)
    if resolved != _BASE_DIR and not resolved.startswith(_BASE_DIR + os.sep):
        raise PermissionError(f"Refusing to read path outside the privacy asset directory: {path}")
    return open(resolved, mode, encoding=None if "b" in mode else "utf-8")


def _render(md_text: str) -> str:
    return markdown.markdown(md_text, extensions=["tables", "sane_lists"])


def _logo_img() -> str:
    """Return an <img> tag with the logo inlined as a data URI, or '' if missing."""
    try:
        with _safe_open(_LOGO_PATH, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        return f'<img class="logo" src="data:image/jpeg;base64,{data}" alt="UBBC logo">'
    except OSError as e:
        logger.error(f"Could not load privacy logo: {e}")
        return ""


# Built once per warm Lambda container: the statement does not change during a
# container's life, so render it lazily and reuse the HTML across invocations.
_cached_page: str | None = None


def _get_page() -> str:
    global _cached_page
    if _cached_page is None:
        with _safe_open(_STATEMENT_PATH, "r") as f:
            _cached_page = _PAGE_TEMPLATE.format(logo=_logo_img(), content=_render(f.read()))
    return _cached_page


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "text/html; charset=utf-8",
                "Cache-Control": f"max-age={_CACHE_TTL}",
            },
            "body": _get_page(),
        }
    except Exception as e:
        logger.error(f"Error in privacy API: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "text/html; charset=utf-8"},
            "body": "<!DOCTYPE html><html><body><p>Privacyverklaring is tijdelijk niet beschikbaar.</p></body></html>",
        }
