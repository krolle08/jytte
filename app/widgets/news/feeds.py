"""Feed configuration for the news widget.

One named CATEGORY = N feeds + N keyword filters. The dashboard card
focuses on the WORLD_CUP category (per request); the /news tab page
shows every category with photos + summaries + click-through to the
source URL.

Adding a new category: drop a new dict into CATEGORIES with a slug,
display title, a list of RSS feed URLs, and optional keyword filters
(only items whose title or summary matches at least one keyword are
kept; an empty filter keeps everything).

Adding/removing feeds: edit the `feeds` list. The fetcher is
fault-tolerant - a 404 or parse error on one feed does not sink the
category.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FeedSource:
    url: str
    name: str                       # short, for the "via X" line on each card
    # When set, only items with at least one keyword (case-insensitive)
    # in title OR summary are kept. Use this when the feed is broad
    # (e.g. general football feed) but the category is narrow (World Cup).
    keywords: tuple[str, ...] = ()


@dataclass
class Category:
    slug: str
    title: str
    feeds: list[FeedSource]
    # Cap rendered items per category (newest first across all feeds).
    max_items: int = 24


CATEGORIES: list[Category] = [
    Category(
        slug="world-cup",
        title="World Cup",
        max_items=18,
        feeds=[
            # The Guardian's dedicated World Cup feed - no keyword filter needed.
            FeedSource(
                url="https://www.theguardian.com/football/world-cup/rss",
                name="The Guardian",
            ),
            # Broad football feeds keyword-filtered to anything World-Cup-shaped:
            # main tournaments, qualifiers, FIFA Club World Cup, Euros, etc.
            FeedSource(
                url="https://www.fifa.com/rss-feeds/news",
                name="FIFA",
                keywords=("world cup", "wc 202", "qualif", "fifa"),
            ),
            FeedSource(
                url="https://www.espn.com/espn/rss/soccer/news",
                name="ESPN FC",
                keywords=("world cup", "wc 202", "qualif", "fifa"),
            ),
            FeedSource(
                url="https://feeds.bbci.co.uk/sport/football/rss.xml",
                name="BBC Sport",
                keywords=("world cup", "wc 202", "qualif", "fifa"),
            ),
        ],
    ),

    Category(
        slug="ai",
        title="AI",
        feeds=[
            FeedSource(url="https://www.technologyreview.com/feed/",                name="MIT Technology Review",
                       keywords=("ai", "artificial intelligence", "llm", "model", "machine learning", "openai", "anthropic", "google", "deepmind")),
            FeedSource(url="https://venturebeat.com/category/ai/feed/",             name="VentureBeat AI"),
            FeedSource(url="https://www.artificialintelligence-news.com/feed/",     name="AI News"),
            FeedSource(url="https://huggingface.co/blog/feed.xml",                  name="Hugging Face"),
            FeedSource(url="https://openai.com/blog/rss.xml",                       name="OpenAI"),
        ],
    ),

    Category(
        slug="claude",
        title="Claude",
        feeds=[
            # NOTE: anthropic.com does not currently publish a public RSS feed
            # (every reasonable URL returns 404). The category therefore relies
            # entirely on keyword-filtered broad tech feeds. If Anthropic adds
            # one, drop a FeedSource(url=..., name="Anthropic") above this line.
            # Broad tech feeds keyword-filtered to anything Claude-shaped:
            # company name, model family names (Sonnet/Opus/Haiku), agent SDK,
            # and the MCP protocol Anthropic ships.
            FeedSource(url="https://venturebeat.com/category/ai/feed/",             name="VentureBeat",
                       keywords=("claude", "anthropic", "sonnet", "opus", "haiku", "agent sdk", "mcp")),
            FeedSource(url="https://feeds.feedburner.com/TechCrunch/",              name="TechCrunch",
                       keywords=("claude", "anthropic", "sonnet", "opus", "haiku", "agent sdk", "mcp")),
            FeedSource(url="https://www.theverge.com/rss/index.xml",                name="The Verge",
                       keywords=("claude", "anthropic", "sonnet", "opus", "haiku", "agent sdk", "mcp")),
        ],
    ),

    Category(
        slug="it-architecture",
        title="IT Architecture",
        feeds=[
            FeedSource(url="https://martinfowler.com/feed.atom",                    name="Martin Fowler"),
            FeedSource(url="https://feed.infoq.com/architecture-design",           name="InfoQ Architecture"),
            FeedSource(url="https://www.thoughtworks.com/rss/insights.xml",         name="Thoughtworks"),
            FeedSource(url="https://aws.amazon.com/blogs/architecture/feed/",       name="AWS Architecture"),
            FeedSource(url="https://devops.com/feed/",                              name="DevOps.com"),
        ],
    ),

    Category(
        slug="conferences",
        title="Conferences & Courses",
        feeds=[
            # Broad tech feeds keyword-filtered to event-shaped headlines.
            # Real news rarely says "conference" verbatim; named events
            # ("KubeCon", "GOTO", "re:Invent") + verbs ("keynote",
            # "announced at") catch the bulk.
            FeedSource(url="https://feed.infoq.com/news",                          name="InfoQ",
                       keywords=("conference", "qcon", "kubecon", "devoxx", "goto",
                                 "ndc", "javazone", "summit", "keynote", "workshop",
                                 "training", "course", "certification", "re:invent",
                                 "ignite", "build 202", "google i/o", "wwdc")),
            FeedSource(url="https://devops.com/feed/",                             name="DevOps.com",
                       keywords=("conference", "kubecon", "devoxx", "summit", "keynote",
                                 "workshop", "training", "certification", "re:invent",
                                 "ignite", "course")),
            # Replaces the old learn.microsoft.com 404. devblogs covers MS
            # ecosystem learning / conference announcements (Build, Ignite).
            FeedSource(url="https://devblogs.microsoft.com/feed/",                 name="Microsoft DevBlogs",
                       keywords=("conference", "summit", "ignite", "build 202",
                                 "training", "course", "certification", "learn", "workshop")),
        ],
    ),

    Category(
        slug="football",
        title="Football",
        feeds=[
            FeedSource(url="https://www.theguardian.com/football/rss",              name="The Guardian"),
            FeedSource(url="https://feeds.bbci.co.uk/sport/football/rss.xml",       name="BBC Sport"),
            FeedSource(url="https://www.espn.com/espn/rss/soccer/news",             name="ESPN FC"),
        ],
    ),

    Category(
        slug="movies",
        title="Movies",
        feeds=[
            # NOTE: Empire Online (empireonline.com) no longer publishes a
            # public RSS feed at any known path. Variety + IndieWire cover
            # the same beat well.
            FeedSource(url="https://variety.com/v/film/feed/",                      name="Variety"),
            FeedSource(url="https://www.indiewire.com/feed/",                       name="IndieWire"),
            FeedSource(url="https://www.hollywoodreporter.com/c/movies/feed/",      name="Hollywood Reporter"),
        ],
    ),

    Category(
        slug="series",
        title="Series",
        feeds=[
            FeedSource(url="https://variety.com/v/tv/feed/",                        name="Variety TV"),
            FeedSource(url="https://tvline.com/feed/",                              name="TVLine"),
            FeedSource(url="https://www.indiewire.com/c/tv/feed/",                  name="IndieWire TV"),
        ],
    ),
]


# Convenience accessors
def get_category(slug: str) -> Category | None:
    return next((c for c in CATEGORIES if c.slug == slug), None)


def category_slugs() -> list[str]:
    return [c.slug for c in CATEGORIES]
