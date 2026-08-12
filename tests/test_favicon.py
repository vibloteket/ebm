from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_all_web_pages_use_the_ebm_favicon():
    pages = sorted((ROOT / "web").glob("*.html"))
    assert pages
    for page in pages:
        assert '<link rel="icon" href="./favicon.svg" type="image/svg+xml">' in page.read_text()


def test_favicon_is_copied_into_static_site():
    script = (ROOT / "scripts" / "build-static-site.sh").read_text()
    assert 'cp "$ROOT/web/favicon.svg" "$OUT/favicon.svg"' in script
