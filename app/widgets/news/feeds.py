"""Feed configuration for the news widget.

One named CATEGORY = a section ('business' | 'private'), a display title,
N feeds + optional keyword filters, and a default sort order. The /news
page groups categories into sections and renders them in a user-editable
order (persisted in the DB via db_news.py); these `section` / `sort_order`
values are only the SEED defaults.

Adding a category: drop a Category into CATEGORIES with a unique slug,
section, title, feeds, and a sort_order. It is seeded into the ordering
prefs on next boot (INSERT OR IGNORE), appended at its default position.

Danish feed URLs are best-effort - a 404 or parse error on one feed does
not sink the category (the fetcher is fault-tolerant). Verify/adjust URLs
here as sources change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Section order + display titles (seed defaults; user can reorder sections).
DEFAULT_SECTION_ORDER = ["business", "private"]
SECTION_TITLES = {"business": "Business", "private": "Private"}


@dataclass
class FeedSource:
    url: str
    name: str                       # short, for the "via X" line on each card
    keywords: tuple[str, ...] = ()  # keep only items matching >= 1 (title/summary)


@dataclass
class Category:
    slug: str
    title: str
    feeds: list[FeedSource]
    section: str = "business"       # 'business' | 'private' (seed default)
    sort_order: int = 100           # seed order within the section
    max_items: int = 24


CATEGORIES: list[Category] = [
    # ─────────────── Business ───────────────
    Category(
        slug="computerworld", title="ComputerWorld", section="business", sort_order=10,
        feeds=[
            # Confirmed feed: the <link rel="alternate"> on computerworld.dk.
            FeedSource(url="https://www.computerworld.dk/rss/all", name="ComputerWorld"),
        ],
    ),
    Category(
        slug="danish-it", title="Danish IT", section="business", sort_order=20,
        feeds=[
            FeedSource(url="https://www.version2.dk/rss", name="Version2"),
            FeedSource(url="https://ing.dk/rss/nyheder", name="Ingenioren"),
            FeedSource(url="https://www.dr.dk/nyheder/service/feeds/viden~teknologi", name="DR Teknologi"),
        ],
    ),
    Category(
        slug="ai", title="AI", section="business", sort_order=30,
        feeds=[
            FeedSource(url="https://www.technologyreview.com/feed/", name="MIT Technology Review",
                       keywords=("ai", "artificial intelligence", "llm", "model", "machine learning", "openai", "anthropic", "google", "deepmind")),
            FeedSource(url="https://venturebeat.com/category/ai/feed/", name="VentureBeat AI"),
            FeedSource(url="https://www.artificialintelligence-news.com/feed/", name="AI News"),
            FeedSource(url="https://huggingface.co/blog/feed.xml", name="Hugging Face"),
            FeedSource(url="https://openai.com/blog/rss.xml", name="OpenAI"),
        ],
    ),
    Category(
        slug="claude", title="Claude", section="business", sort_order=40,
        feeds=[
            FeedSource(url="https://venturebeat.com/category/ai/feed/", name="VentureBeat",
                       keywords=("claude", "anthropic", "sonnet", "opus", "haiku", "agent sdk", "mcp")),
            FeedSource(url="https://feeds.feedburner.com/TechCrunch/", name="TechCrunch",
                       keywords=("claude", "anthropic", "sonnet", "opus", "haiku", "agent sdk", "mcp")),
            FeedSource(url="https://www.theverge.com/rss/index.xml", name="The Verge",
                       keywords=("claude", "anthropic", "sonnet", "opus", "haiku", "agent sdk", "mcp")),
        ],
    ),
    Category(
        slug="it-architecture", title="IT Architecture", section="business", sort_order=50,
        feeds=[
            FeedSource(url="https://martinfowler.com/feed.atom", name="Martin Fowler"),
            FeedSource(url="https://feed.infoq.com/architecture-design", name="InfoQ Architecture"),
            FeedSource(url="https://www.thoughtworks.com/rss/insights.xml", name="Thoughtworks"),
            FeedSource(url="https://aws.amazon.com/blogs/architecture/feed/", name="AWS Architecture"),
            FeedSource(url="https://devops.com/feed/", name="DevOps.com"),
        ],
    ),
    Category(
        slug="conferences", title="Conferences & Courses", section="business", sort_order=60,
        feeds=[
            FeedSource(url="https://feed.infoq.com/news", name="InfoQ",
                       keywords=("conference", "qcon", "kubecon", "devoxx", "goto", "ndc", "javazone",
                                 "summit", "keynote", "workshop", "training", "course", "certification",
                                 "re:invent", "ignite", "build 202", "google i/o", "wwdc")),
            FeedSource(url="https://devops.com/feed/", name="DevOps.com",
                       keywords=("conference", "kubecon", "devoxx", "summit", "keynote", "workshop",
                                 "training", "certification", "re:invent", "ignite", "course")),
            FeedSource(url="https://devblogs.microsoft.com/feed/", name="Microsoft DevBlogs",
                       keywords=("conference", "summit", "ignite", "build 202", "training", "course",
                                 "certification", "learn", "workshop")),
        ],
    ),

    # ─────────────── Private ───────────────
    Category(
        slug="computer-games", title="Computer games", section="private", sort_order=10,
        feeds=[
            FeedSource(url="https://www.eurogamer.net/feed", name="Eurogamer"),
            FeedSource(url="https://www.pcgamer.com/rss/", name="PC Gamer"),
            FeedSource(url="https://feeds.ign.com/ign/games-all", name="IGN"),
            FeedSource(url="https://www.polygon.com/rss/index.xml", name="Polygon"),
        ],
    ),
    Category(
        slug="concerts", title="Concerts", section="private", sort_order=20,
        feeds=[
            # Concert / live-music NEWS (RSS). Concert *listings* by city would
            # need a ticketing API (Songkick / Bandsintown) - future option.
            FeedSource(url="https://consequence.net/feed/", name="Consequence"),
            FeedSource(url="https://www.stereogum.com/feed/", name="Stereogum"),
            FeedSource(url="https://pitchfork.com/rss/news/", name="Pitchfork"),
        ],
    ),
    Category(
        slug="football", title="Football", section="private", sort_order=30,
        feeds=[
            FeedSource(url="https://www.theguardian.com/football/rss", name="The Guardian"),
            FeedSource(url="https://feeds.bbci.co.uk/sport/football/rss.xml", name="BBC Sport"),
            FeedSource(url="https://www.espn.com/espn/rss/soccer/news", name="ESPN FC"),
        ],
    ),
    Category(
        slug="movies", title="Movies", section="private", sort_order=40,
        feeds=[
            FeedSource(url="https://variety.com/v/film/feed/", name="Variety"),
            FeedSource(url="https://www.indiewire.com/feed/", name="IndieWire"),
            FeedSource(url="https://www.hollywoodreporter.com/c/movies/feed/", name="Hollywood Reporter"),
        ],
    ),
    Category(
        slug="series", title="Series", section="private", sort_order=50,
        feeds=[
            FeedSource(url="https://variety.com/v/tv/feed/", name="Variety TV"),
            FeedSource(url="https://tvline.com/feed/", name="TVLine"),
            FeedSource(url="https://www.indiewire.com/c/tv/feed/", name="IndieWire TV"),
        ],
    ),
]


# Convenience accessors
def get_category(slug: str) -> Category | None:
    return next((c for c in CATEGORIES if c.slug == slug), None)


def category_slugs() -> list[str]:
    return [c.slug for c in CATEGORIES]
