"""Guards for the chat stored-XSS fix.

The chat (and the admin session/doc-gen views) render Markdown to ``innerHTML``.
That output is sanitized with DOMPurify so untrusted DB/doc content echoed into an
agent answer can't execute as HTML. These tests are static guards: they fail if a
future edit reintroduces an unsanitized ``marked.parse`` or drops the DOMPurify
script tag from a page that renders Markdown. (DOMPurify's own correctness is
covered by the behavioural test and by upstream Cure53 tests.)
"""

import re
from collections.abc import Generator
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "backend"
VENDOR_PURIFY = WEB / "static" / "js" / "vendor" / "purify.min.js"

# Files that call marked.parse and assign the result to innerHTML.
RENDER_FILES = [
    WEB / "static" / "js" / "chat" / "markdown-renderer.js",
    WEB / "static" / "js" / "docsources" / "generate.js",
    WEB / "console" / "templates" / "console" / "sessions" / "detail.html",
]


def _iter_source_files() -> Generator[Path, None, None]:
    for path in WEB.rglob("*"):
        if path.suffix in (".js", ".html") and "vendor" not in path.parts:
            yield path


def test_vendored_dompurify_present() -> None:
    """The sanitizer ships in-repo (no CDN dependency for a security control)."""
    assert VENDOR_PURIFY.is_file(), "vendored purify.min.js is missing"
    banner = VENDOR_PURIFY.read_text(encoding="utf-8")[:200]
    assert "DOMPurify" in banner, "purify.min.js does not look like DOMPurify"


def test_every_marked_parse_is_sanitized() -> None:
    """No marked.parse(...) anywhere reaches innerHTML without DOMPurify.sanitize.

    Every occurrence must sit on a line that also calls DOMPurify.sanitize — the
    three render sites all wrap inline as ``DOMPurify.sanitize(marked.parse(...))``.
    """
    offenders = []
    for path in _iter_source_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "marked.parse(" in line and "DOMPurify.sanitize(" not in line:
                offenders.append(f"{path.relative_to(WEB)}:{lineno}: {line.strip()}")
    assert not offenders, "unsanitized marked.parse() found:\n" + "\n".join(offenders)


def test_render_sites_load_dompurify_directly() -> None:
    """Each render site (or its page) pulls in DOMPurify before it renders.

    The two JS modules run on pages whose template loads purify.min.js; the inline
    template loads it itself. We assert the vendored script is referenced by every
    template that loads marked directly.
    """
    marked_re = re.compile(r"marked(\.min\.js|/marked)")
    for path in WEB.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        if marked_re.search(text):
            assert "purify.min.js" in text, (
                f"{path.relative_to(WEB)} loads marked but not purify.min.js"
            )


def test_rendermarkdown_wraps_with_dompurify() -> None:
    """The central chat renderer sanitizes its output."""
    src = (WEB / "static" / "js" / "chat" / "markdown-renderer.js").read_text(encoding="utf-8")
    assert re.search(r"DOMPurify\.sanitize\(\s*marked\.parse\(", src), (
        "renderMarkdown() no longer wraps marked.parse in DOMPurify.sanitize"
    )
