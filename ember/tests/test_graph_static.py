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
