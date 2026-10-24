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

from dataclasses import dataclass


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


# Shared by every feed in the GTA category. Long forms only: _keep() is a
# substring match, so "gta" alone would match inside unrelated words.
GTA_KEYWORDS: tuple[str, ...] = (
    "grand theft auto", "gta 6", "gta vi", "gta6", "gta online",
    "rockstar games", "rockstar north",
)


CATEGORIES: list[Category] = [
    Category(
        slug="games",
        title="Spil",
        max_items=20,
        feeds=[
            # Broad, high-volume, reliable RSS. Eurogamer and RPS are
            # editorial; IGN and GameSpot carry the announcements first.
            FeedSource(url="https://www.eurogamer.net/feed", name="Eurogamer"),
            FeedSource(url="https://www.rockpapershotgun.com/feed", name="Rock Paper Shotgun"),
            FeedSource(url="https://feeds.ign.com/ign/games-all", name="IGN"),
            FeedSource(url="https://www.gamespot.com/feeds/news/", name="GameSpot"),
            FeedSource(url="https://www.pcgamer.com/rss/", name="PC Gamer"),
            FeedSource(url="https://www.polygon.com/rss/index.xml", name="Polygon"),
            # Danish coverage, so the category is not all English.
            FeedSource(url="https://www.gamereactor.dk/rss/rss.php?texttype=news",
                       name="Gamereactor DK"),
        ],
    ),
    Category(
        slug="games-releases",
        title="Nye og opdaterede spil",
        max_items=20,
        feeds=[
            # Gematsu is the best single source for release dates and
            # Japanese announcements; the rest are keyword-filtered down
            # to launch and patch news only.
            FeedSource(url="https://www.gematsu.com/feed", name="Gematsu"),
            FeedSource(url="https://www.nintendolife.com/feeds/latest", name="Nintendo Life"),
            FeedSource(url="https://www.pushsquare.com/feeds/latest", name="Push Square"),
            FeedSource(
                url="https://www.eurogamer.net/feed", name="Eurogamer",
                keywords=("release date", "out now", "launches", "launch",
                          "released", "early access", "patch", "update",
                          "version 1.", "dlc", "expansion", "udkommer"),
            ),
            FeedSource(
                url="https://feeds.ign.com/ign/games-all", name="IGN",
                keywords=("release date", "out now", "launches", "launch",
                          "released", "early access", "patch", "update",
                          "dlc", "expansion"),
            ),
            FeedSource(
                url="https://www.pcgamer.com/rss/", name="PC Gamer",
                keywords=("release date", "out now", "launch", "released",
                          "early access", "patch", "update", "dlc", "mod"),
            ),
        ],
    ),
    Category(
        slug="blizzard",
        title="Blizzard og WoW",
        max_items=20,
        feeds=[
            # Dedicated and unfiltered: these are Blizzard-only outlets,
            # so a keyword filter would only throw away good items.
            # Verified live 2026-10-12: both return 200 with real
            # editorial items.
            FeedSource(url="https://www.wowhead.com/news/rss/all", name="Wowhead"),
            FeedSource(url="https://blizzardwatch.com/feed/", name="Blizzard Watch"),
            # MMO-Champion is deliberately NOT here. Its only reachable
            # feed (external.php?type=RSS2) is the FORUM, not the news
            # section: it returned thread titles like "Since qhen
            # timewalking cache is giving tier token?" and worse, and it
            # drowned the real news by volume. rss.php and /feed both 403,
            # and the newcontent variant returns zero items. Checked
            # 2026-10-12.
            # Blizzard's own newsroom has no working RSS: news.blizzard.com
            # /en-us/rss and /en-gb/rss both 404, and icy-veins.com/feed
            # returns 403 to anything that is not a browser. So the big
            # announcements are picked up from the broad gaming feeds
            # instead, narrowed to Blizzard titles.
            FeedSource(url="https://feeds.ign.com/ign/games-all", name="IGN",
                       keywords=("blizzard", "world of warcraft", "warcraft",
                                 "diablo", "overwatch", "hearthstone", "starcraft")),
            FeedSource(url="https://www.pcgamer.com/rss/", name="PC Gamer",
                       keywords=("blizzard", "world of warcraft", "warcraft",
                                 "diablo", "overwatch", "hearthstone", "starcraft")),
            FeedSource(url="https://www.eurogamer.net/feed", name="Eurogamer",
                       keywords=("blizzard", "world of warcraft", "warcraft",
                                 "diablo", "overwatch", "hearthstone", "starcraft")),
        ],
    ),
    Category(
        slug="gta",
        title="GTA",
        max_items=20,
        feeds=[
            # No dedicated feed exists: rockstargames.com/newswire.rss and
            # /newswire/feed both 404 as of 2026-10-12. GTA 6 coverage lands
            # in every major outlet anyway, so this is broad feeds narrowed
            # by keyword.
            #
            # Keywords are deliberately long. _keep() does a case-insensitive
            # SUBSTRING match, so a bare "gta" would hit inside unrelated
            # words and a bare "rockstar" would pull in energy drinks and
            # music writing. "grand theft auto" and "rockstar games" do not.
            FeedSource(url="https://feeds.ign.com/ign/games-all", name="IGN",
                       keywords=GTA_KEYWORDS),
            FeedSource(url="https://www.pcgamer.com/rss/", name="PC Gamer",
                       keywords=GTA_KEYWORDS),
            FeedSource(url="https://www.eurogamer.net/feed", name="Eurogamer",
                       keywords=GTA_KEYWORDS),
            FeedSource(url="https://www.rockpapershotgun.com/feed",
                       name="Rock Paper Shotgun", keywords=GTA_KEYWORDS),
            FeedSource(url="https://www.gamespot.com/feeds/news/", name="GameSpot",
                       keywords=GTA_KEYWORDS),
            FeedSource(url="https://www.polygon.com/rss/index.xml", name="Polygon",
                       keywords=GTA_KEYWORDS),
            FeedSource(url="https://www.gamereactor.dk/rss/rss.php?texttype=news",
                       name="Gamereactor DK", keywords=GTA_KEYWORDS),
        ],
    ),
    Category(
        slug="games-hype",
        title="Hype og annonceringer",
        max_items=18,
        feeds=[
            FeedSource(
                url="https://www.eurogamer.net/feed", name="Eurogamer",
                keywords=("announced", "announce", "reveal", "revealed",
                          "trailer", "upcoming", "preview", "hands-on",
                          "delayed", "delay", "teaser", "annonceret"),
            ),
            FeedSource(
                url="https://feeds.ign.com/ign/games-all", name="IGN",
                keywords=("announced", "announce", "reveal", "revealed",
                          "trailer", "upcoming", "preview", "first look",
                          "delayed", "delay", "teaser"),
            ),
            FeedSource(
                url="https://www.rockpapershotgun.com/feed", name="Rock Paper Shotgun",
                keywords=("announced", "reveal", "trailer", "upcoming",
                          "preview", "hands-on", "delayed"),
            ),
            FeedSource(
                url="https://www.gematsu.com/feed", name="Gematsu",
                keywords=("announced", "reveal", "trailer", "teaser",
                          "delayed", "upcoming"),
            ),
            FeedSource(
                url="https://www.polygon.com/rss/index.xml", name="Polygon",
                keywords=("announced", "reveal", "trailer", "upcoming",
                          "preview", "delayed"),
            ),
        ],
    ),
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
