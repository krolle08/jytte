"""FEAT-004 ComputerWorld: newsletter article extraction (pure regex)."""

from app.widgets.computerworld import fetch as f


HTML = '''
<a href="https://computerworld.dk/art/12345/some-long-article-title-here">Some long article title here</a>
<a href="https://computerworld.dk/unsubscribe?u=1">Afmeld nyhedsbrevet nu</a>
<a href="https://www.facebook.com/computerworld">Foelg os paa Facebook her</a>
<a href="https://computerworld.dk/art/12345/some-long-article-title-here?utm=news">Some long article title here duplicate</a>
<a href="https://computerworld.dk/art/999/great-headline-about-ai-in-denmark">Great headline about AI in Denmark</a>
<a href="https://example.com/ad/banner">Totally unrelated advertisement link</a>
<a href="https://computerworld.dk/x">short</a>
'''


def test_extract_keeps_articles_drops_noise():
    arts = f._extract_articles(HTML, "computerworld.dk")
    titles = [a["title"] for a in arts]
    assert "Some long article title here" in titles
    assert "Great headline about AI in Denmark" in titles
    # unsubscribe + facebook + external ad + short link all dropped
    assert not any("Afmeld" in t for t in titles)
    assert not any("Facebook" in t for t in titles)
    assert not any("advertisement" in t for t in titles)
    assert "short" not in titles


def test_dedup_by_href_query_stripped():
    arts = f._extract_articles(HTML, "computerworld.dk")
    # the ?utm= duplicate collapses onto the first by _dedup_key
    first = [a for a in arts if a["link"].startswith("https://computerworld.dk/art/12345")]
    assert len(first) == 1


def test_dedup_key():
    assert f._dedup_key("https://x.dk/a/1?utm=y") == "https://x.dk/a/1"
    assert f._dedup_key("https://x.dk/a/1/") == "https://x.dk/a/1"
