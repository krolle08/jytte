"""Feed configuration for the geomap widget.

Each feed has:
  - id          : short id used in the cache
  - name        : display name shown in pins
  - url         : RSS/Atom URL
  - kind        : danish | worldwide | tech
  - home_iso    : ISO_A3 fallback country if article has no detectable location
  - domain      : used for favicon lookup
"""

FEEDS = [
    # danish
    {"id": "dr",        "name": "DR",            "url": "https://www.dr.dk/nyheder/service/feeds/allenyheder",  "kind": "danish",     "home_iso": "DNK", "domain": "dr.dk"},
    {"id": "politiken", "name": "Politiken",     "url": "https://politiken.dk/rss/senestenyt.rss",              "kind": "danish",     "home_iso": "DNK", "domain": "politiken.dk"},
    {"id": "cwdk",      "name": "Computerworld", "url": "https://www.computerworld.dk/rss",                     "kind": "danish",     "home_iso": "DNK", "domain": "computerworld.dk"},
    # worldwide
    {"id": "guardian",  "name": "The Guardian",  "url": "https://www.theguardian.com/world/rss",                "kind": "worldwide",  "home_iso": "GBR", "domain": "theguardian.com"},
    {"id": "cnn",       "name": "CNN",           "url": "http://rss.cnn.com/rss/edition.rss",                   "kind": "worldwide",  "home_iso": "USA", "domain": "cnn.com"},
    # tech (AI + solution architecture)
    {"id": "anthropic", "name": "Anthropic",     "url": "https://www.anthropic.com/news/feed.xml",              "kind": "tech",       "home_iso": "USA", "domain": "anthropic.com"},
    {"id": "latent",    "name": "Latent Space",  "url": "https://www.latent.space/feed",                         "kind": "tech",       "home_iso": "USA", "domain": "latent.space"},
    {"id": "tldr",      "name": "TLDR",          "url": "https://tldr.tech/api/rss/tech",                        "kind": "tech",       "home_iso": "USA", "domain": "tldr.tech"},
    {"id": "pragmatic", "name": "Pragmatic Eng", "url": "https://newsletter.pragmaticengineer.com/feed",         "kind": "tech",       "home_iso": "NLD", "domain": "pragmaticengineer.com"},
    {"id": "awsarch",   "name": "AWS Architect", "url": "https://aws.amazon.com/blogs/architecture/feed/",       "kind": "tech",       "home_iso": "USA", "domain": "aws.amazon.com"},
    {"id": "hn",        "name": "Hacker News",   "url": "https://news.ycombinator.com/rss",                      "kind": "tech",       "home_iso": "USA", "domain": "news.ycombinator.com"},
]

KIND_COLOR = {
    "danish":    "#f4b860",  # warm amber
    "worldwide": "#5ee1d0",  # cyan
    "tech":      "#9b8cff",  # violet (the AI tone)
}


def by_id(feed_id: str) -> dict | None:
    for f in FEEDS:
        if f["id"] == feed_id:
            return f
    return None


def favicon(domain: str) -> str:
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"


# Curated active armed-conflicts baseline. Always-on layer so the map
# lights up even when ACLED is not configured. Edit this when the
# geopolitical picture shifts. Severity scale 1..4 (green/yellow/orange/red).
ACTIVE_CONFLICTS: list[dict] = [
    {"iso": "UKR", "severity": 4, "name": "Russia-Ukraine war",                  "type": "armed conflict"},
    {"iso": "PSE", "severity": 4, "name": "Israel-Gaza war",                     "type": "armed conflict"},
    {"iso": "SDN", "severity": 4, "name": "Sudan civil war",                     "type": "armed conflict"},
    {"iso": "MMR", "severity": 3, "name": "Myanmar civil war",                   "type": "armed conflict"},
    {"iso": "LBN", "severity": 3, "name": "Israel-Hezbollah conflict",           "type": "armed conflict"},
    {"iso": "IRN", "severity": 3, "name": "Israel-Iran strikes",                 "type": "armed conflict"},
    {"iso": "YEM", "severity": 3, "name": "Yemen war / Houthi conflict",         "type": "armed conflict"},
    {"iso": "COD", "severity": 3, "name": "DRC east / M23 insurgency",           "type": "armed conflict"},
    {"iso": "HTI", "severity": 3, "name": "Haiti gang violence",                 "type": "armed conflict"},
    {"iso": "SYR", "severity": 2, "name": "Syria post-Assad instability",        "type": "armed conflict"},
    {"iso": "ETH", "severity": 2, "name": "Ethiopia internal conflicts",         "type": "armed conflict"},
    {"iso": "SOM", "severity": 2, "name": "Somalia / al-Shabaab",                "type": "armed conflict"},
    {"iso": "LBY", "severity": 2, "name": "Libya factional conflict",            "type": "armed conflict"},
    {"iso": "MLI", "severity": 2, "name": "Mali insurgency",                     "type": "armed conflict"},
    {"iso": "BFA", "severity": 2, "name": "Burkina Faso insurgency",             "type": "armed conflict"},
    {"iso": "NER", "severity": 2, "name": "Niger insurgency",                    "type": "armed conflict"},
    {"iso": "NGA", "severity": 2, "name": "Nigeria - Boko Haram / banditry",     "type": "armed conflict"},
    {"iso": "MOZ", "severity": 2, "name": "Mozambique - Cabo Delgado",           "type": "armed conflict"},
    {"iso": "AFG", "severity": 2, "name": "Afghanistan post-withdrawal",         "type": "armed conflict"},
    {"iso": "MEX", "severity": 2, "name": "Mexico cartel violence",              "type": "armed conflict"},
    {"iso": "COL", "severity": 2, "name": "Colombia armed groups",               "type": "armed conflict"},
    {"iso": "VEN", "severity": 2, "name": "Venezuela political crisis",          "type": "armed conflict"},
]
