import re
from pathlib import Path

HTML = Path(__file__).parent.parent / "graph" / "index.html"


def test_graph_page_is_wired_and_theme_aware():
    src = HTML.read_text(encoding="utf-8")
    assert '<script src="data.js">' in src and "window.EMBER_DATA" in src
    for el in ("cohort", "subject", "x-select", "y-select", "c-select", "scatter", "cohort-table", "radar", "evidence", "tooltip", "back"):
        assert f'id="{el}"' in src, el
    assert "prefers-color-scheme: dark" in src and ':root:not([data-theme="light"])' in src and ':root[data-theme="dark"]' in src
    assert "textContent" in src and "innerHTML" not in src           # untrusted strings never go through innerHTML
    assert "#2a78d6" in src and "#86b6ef" in src and "#0d366b" in src  # slot-1 blue and the ordinal ramp ends
    assert "<table" in src and 'class="legend"' in src


def test_page_renders_all_four_panels():
    src = HTML.read_text(encoding="utf-8")
    for panel in ("panel-heat", "panel-split", "panel-groups", "panel-subject"):
        assert f'id="{panel}"' in src, f"missing {panel}"


def test_page_shows_the_data_quality_banner():
    assert 'id="banner"' in HTML.read_text(encoding="utf-8")


def test_page_reads_the_analysis_block_and_never_recomputes_it():
    src = HTML.read_text(encoding="utf-8")
    assert "EMBER_DATA" in src and ".analysis" in src
    for banned in ("Math.sqrt", "pstdev", "linkage("):
        assert banned not in src, f"the page must not compute statistics itself ({banned})"


def test_page_makes_no_network_calls():
    """Offline from file://. The SVG/XML namespace URI is an identifier, never a fetch."""
    src = HTML.read_text(encoding="utf-8")
    for banned in ("fetch(", "XMLHttpRequest", "import(", "<link", "<script src=\"http"):
        assert banned not in src, f"the page must work offline from file:// ({banned})"
    urls = [u for u in re.findall(r"https?://[^\"\')\s]+", src)
            if not u.startswith("http://www.w3.org/")]
    assert not urls, f"remote resources: {urls}"
