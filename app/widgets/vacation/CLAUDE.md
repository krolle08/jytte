# vacation widget - Danish school holidays

Powers `/vacation`. Modelled on
<https://danmarkshelligdage.dk/da/skoleferier/>, which is where the
request came from, but **nothing is scraped**.

## Why rules and not a scraper

The site publishes a table. A scraper against it would be one markup
change away from breaking, would need a network call in the fetch path,
and would only ever know the two school years the page happens to show.

Five arithmetic rules reproduce that table exactly and keep working for
2035. They were verified against the published 2025/2026 values before
the widget was written:

| Ferie          | Rule                                                      | 2025/2026 published | Computed |
|----------------|-----------------------------------------------------------|---------------------|----------|
| Efteraarsferie | Mon-Fri of ISO week 42                                     | 13-17 okt           | match    |
| Juleferie      | Monday of week holding 24 Dec, to Sunday of week holding 1 Jan | 22 dec - 4 jan, 14 dage | match |
| Vinterferie    | Mon-Fri of ISO week 7 (oest) / 8 (vest)                    | 9-13 feb / 16-20 feb | match   |
| Paaskeferie    | Easter Sunday minus 8 days, to Easter Monday               | 28 mar - 6 apr, 10 dage | match |
| Sommerferie    | Last Saturday in June, plus 43 days                        | 27 jun - 9 aug      | match    |

Easter comes from the anonymous Gregorian algorithm in `fetch.py`.

## The one honest caveat

The school year is set **per kommune**. These dates are the common
pattern, not an authority, and a given kommune can differ by a day or
two. `CAVEAT` carries that sentence and the page prints it rather than
burying it, because a vacation page that is confidently wrong about
when school restarts is worse than one that says it is approximate.

The east/west winter split is the only variation large enough to model.
Both weeks are always computed and carried in `variants`, so the page
can show the other half of the country instead of silently choosing.

## Shape

`fetch()` returns `ready`, `today`, the selected `region` with its label
and week, `regions`, `years` (3 school years, current first), `current`
(a holiday running today, with `days_left`), `next` (with `days_until`),
`caveat` and `source_url`.

`build(region, today)` is the synchronous version. The page calls it
directly when `?r=` asks for a region the cached payload was not built
with: re-running five date computations is cheaper than caching a
payload per region.

`school_year(start_year, region)` is the unit, and `start_year` is the
August year, so 2025 means 2025/2026.

## School year boundary

The year turns over with the **summer holiday**, not 1 January. Before
summer ends, the current school year is still the one that started last
August. `_build` uses `_last_saturday_in_june` for that test, so the
page does not jump a year forward every New Year.

## Region default

`JYTTE_VACATION_REGION` in `.env`, `oest` or `vest`. Defaults to `oest`.
The page overrides it per request with `?r=`.

## MCP

Two tools, both read-only: `school_holidays_next` and
`school_holidays_year`. Exposed because "hvornaar er der vinterferie"
otherwise costs a web search.

## No credentials, no network, no AI

Plain arithmetic. There is nothing to put in `.env` beyond the region
preference, and nothing here should ever grow a fetch.
