"""Guards for the inline-script JSON injection fix.

Server data destined for client-side JS is emitted with Django's ``json_script``
filter, which HTML-escapes ``<``/``>``/``&`` (e.g. a literal ``</script>`` in a
query-result cell becomes ``\\u003C/script>``). The previous ``{{ x|safe }}``
inside/next to a ``<script>`` let such content break out of the tag.
"""

from pathlib import Path

from django.utils.html import json_script

WEB = Path(__file__).resolve().parent.parent / "backend"

# (template path, json_script element id) — the converted injection sites.
SITES = [
    ("portal/templates/portal/reports.html", "report-groups-data"),
    ("console/templates/console/dashboards/chart_form.html", "chart-cached-data"),
    ("console/templates/console/docsources/form.html", "doc-type-descriptions"),
    ("console/templates/console/docsources/generate.html", "dest-folders"),
    ("console/templates/console/docsources/generate_library.html", "existing-folders"),
]


def test_sites_use_json_script_not_safe() -> None:
    for rel, element_id in SITES:
        text = (WEB / rel).read_text(encoding="utf-8")
        assert f'json_script:"{element_id}"' in text, f"{rel} no longer uses json_script"
        assert "|safe" not in text, f"{rel} still contains a |safe filter"


# Templates that render pre-converted Markdown from repo-controlled files (not user input).
_SAFE_FILTER_ALLOWLIST = {
    Path("console/templates/console/version.html"),  # changelog .md files from changelog/
}


def test_no_safe_filter_anywhere_in_templates() -> None:
    """No template should dump server data into the page with |safe."""
    offenders = [
        p.relative_to(WEB)
        for p in WEB.rglob("*.html")
        if "|safe" in p.read_text(encoding="utf-8")
        and p.relative_to(WEB) not in _SAFE_FILTER_ALLOWLIST
    ]
    assert not offenders, f"|safe found in templates: {offenders}"


def test_json_script_escapes_script_breakout() -> None:
    """The filter neutralizes a </script> + HTML payload in the data.

    json_script wraps the value in its own <script>…</script>; the only literal
    closing tag is that wrapper's. The payload's </script> must be escaped, so a
    cell value can't break out of the tag.
    """
    payload = {"cell": "</script><img src=x onerror=alert(1)>"}
    out = str(json_script(payload, "x"))
    # The payload's breakout sequence must not appear verbatim anywhere.
    assert "</script><img" not in out, "payload broke out of the script tag"
    assert "<img" not in out, "raw <img survived (would execute on breakout)"
    # …it must appear in escaped form instead.
    assert "\\u003C/script\\u003E\\u003Cimg" in out, "payload was not unicode-escaped"
