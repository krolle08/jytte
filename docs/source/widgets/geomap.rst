World Pulse (geomap)
====================

**What it is**: World map of news + crisis events, with per-country
severity overlay.

**Why it's here**: Single pane for "what's happening in the world right
now", merging RSS news pins with ACLED-derived crisis severity.

**Source**: ``app/widgets/geomap/``

Overview
--------

Loads a world-countries GeoJSON, scores each country by a 3-source
severity formula (recent ACLED events, news intensity, fatalities),
then renders an interactive map with click-through drill-downs.

Key Responsibilities
--------------------

- Fetch news and crisis feeds on the refresh cadence.
- Score country severity from multiple signals.
- Render the SVG map card + per-country detail.

Integration Points
------------------

- **RSS feeds** for general news pins.
- **ACLED API** for crisis-event data (``ACLED_KEY`` / ``ACLED_EMAIL``).
- **Claude API** (optional) for narrative analysis.

Related Documentation
---------------------

- :doc:`../architecture` - widget component contract
