# Jytte - Feature Roadmap

> Every upcoming feature gets a section here BEFORE we cut code. Each
> section is a spec: purpose, scope, open questions, acceptance
> criteria. We review and accept the section, then implement it, then
> move to the next. No big-bang multi-feature builds.

---

## Shipped

| Tag  | What                                                              |
|------|-------------------------------------------------------------------|
| v0.1 | Plugin widget system (FastAPI + APScheduler + SQLite + MCP)       |
| v0.2 | Tasks widget (Obsidian folder watcher, edit-back, detail drawer)  |
| v0.3 | World Pulse map (news pins + crisis overlay, 3-source severity)   |
| v0.4 | UI polish pass (typography, asymmetric grid, microinteractions)   |

---

## Up next

The pipeline is F1 -> F2 -> F3. We treat each as: write spec here ->
review + accept -> implement -> next.

### F1 - Football predictor (with full ML walkthrough)

**Purpose.** Add a dashboard tab/card that predicts the outcomes of
upcoming football matches using a machine-learning model trained on
historical match data. The widget is half the deliverable; the other
half is a thorough, pedagogical document at `docs/ml-walkthrough.md`
that explains ML from first principles - using this very widget as
the worked example end to end. The point is NOT to ship a competitive
prediction model. The point is for Nichlas to learn ML by reading,
running, modifying, and observing a real model he built.

**What the widget shows.** A card on the dashboard listing the next
N upcoming matches in the chosen league(s). For each match we surface
THREE predictions, not just the result:

  T1. Match outcome (1X2): home win / draw / away win
      - probability per outcome, summing to 100%
      - confidence indicator (entropy + calibration band - see
        "Uncertainty handling" below)

  T2. Goalscorers
      - top 3 most likely scorers per side (P(scores in this match))
      - top 1 predicted assist (if data permits)
      - expected goals (xG) per team, with uncertainty band

  T3. Bookings (yellow / red cards)
      - top 1-2 players most likely to be booked, per side
      - predicted total cards in match, with a 50% prediction interval

For each match the widget also shows:

  - home team vs away team, date/time, competition
  - per-prediction "confidence" badge (high / medium / low) derived
    from calibrated probability + prediction interval width
  - on hover/click: a "why" panel listing the top features that
    drove each prediction (recent form, home advantage, head-to-head,
    referee history for bookings, opponent defensive xGA for
    goalscorers, etc.)
  - actual result + scorers + bookings once the match is played,
    with check/cross per prediction
  - rolling per-prediction accuracy + calibration metric over the
    last 30 days (so you can see "1X2 is well calibrated, bookings
    is overconfident", etc.)

**Algorithm + outcome scoring (how the model actually evaluates).**

Three separate prediction targets demand three different model
families. We use the right tool per target instead of forcing
everything into one model:

  T1. Match outcome (1X2)
      - Family: multinomial logistic regression (baseline) then
        gradient-boosted trees (LightGBM) once we want non-linear
        interactions.
      - Output: P(home), P(draw), P(away). Summed to 1 by softmax.
      - Loss during training: multinomial log-loss (cross-entropy).
      - Calibration: Platt scaling on a held-out fold so the raw
        outputs become trustworthy probabilities, not just rankings.

  T2. Goalscorers
      - Family: per-player binary logistic regression on
        P(player scores in match). Run once per player in each
        starting XI; rank descending.
      - Independent of T1 - but conditioned on the same match
        features (opponent strength, home advantage).
      - Output also feeds an aggregate team xG (sum of per-player
        scoring probabilities -> expected number of scorers per side,
        which is a noisy proxy for goals).
      - Loss: binary cross-entropy.

  T3. Bookings
      - Family: TWO models stacked.
        (a) Poisson regression for total cards in the match (mean
            arrival rate, given referee + teams + match context).
        (b) Per-player binary logistic for "this player gets booked",
            ranked top-N.
      - Why Poisson: card counts are non-negative integers with
        right-skewed distribution, exactly what Poisson is built for.
      - Output (a): predicted total cards, plus a 50% prediction
        interval (e.g. "4.2 cards, 50% chance between 3 and 5").
      - Output (b): top 1-2 most-likely-booked players per side.

How outcomes are "evaluated" once matches play:
  - 1X2: did the highest-probability outcome match the actual result?
    Plus log-loss across all three probabilities.
  - Goalscorers: precision @ top-3 (of the 3 predicted scorers, how
    many actually scored?). Plus Brier per player.
  - Bookings: mean absolute error on total card count; recall on
    top-2 booked-player predictions.
  - Per-target rolling 30-day metric shown in the card footer so
    you see drift in real time.

**Uncertainty handling (how predictions are weighted by uncertainty).**

A confident-looking 60/30/10 home/draw/away is meaningless if the
model is poorly calibrated. We treat uncertainty as a first-class
output, not an afterthought.

Three layers of uncertainty are computed and displayed:

  L1. Aleatoric (irreducible game randomness):
        - Surfaces as: prediction entropy. High entropy across the
          three 1X2 outcomes -> low confidence badge regardless of
          peak probability.
        - For Poisson card counts: variance grows with the mean, so
          we expose the prediction interval directly.

  L2. Epistemic (model uncertainty about its own answer):
        - Estimated via bootstrap aggregating: train K=20 model
          copies on bootstrap samples of the training data.
        - For each upcoming match, run all K models -> distribution
          of probabilities -> standard deviation across models = our
          epistemic uncertainty.
        - Surfaces as: confidence band (e.g. "65% home win, +/- 8%").
        - High epistemic uncertainty is a flag that the model is
          extrapolating outside its comfort zone (e.g. newly
          promoted side with little history).

  L3. Calibration (does 70% mean 70%?):
        - Built using Platt scaling on a held-out calibration fold.
        - Monitored via reliability diagrams in the walkthrough doc
          and a calibration drift metric in the widget footer.
        - When calibration drifts past a threshold, retraining is
          triggered automatically (not just on the weekly cadence).

How the widget combines these into one number:
  - The displayed "confidence" badge per prediction is:
        confidence_score = (1 - normalized_entropy)
                         * (1 - normalized_epistemic_std)
                         * calibration_health_factor
    where each factor is in [0, 1] and the product gives high /
    medium / low buckets (>0.6 / 0.3-0.6 / <0.3).
  - This means: a peak probability of 60% with low entropy, tight
    bootstrap band, and a well-calibrated model = HIGH confidence,
    while a peak of 80% with two close runners-up = MEDIUM at best.

**Parameters taken into consideration (features per target).**

Final feature list is locked at implementation time, but here is the
full intended set. The walkthrough explains each: what it is, why we
chose it, what its leakage / staleness traps are.

Match-level features (all three targets share these):
  - days_rest_home, days_rest_away
  - travel_distance_for_away
  - day_of_week, hour_of_day
  - match_importance_score (derby, relegation, title race, dead rubber)
  - competition_tier (league / cup / euro)
  - season_phase (early / mid / late)
  - weather (temperature, precipitation, wind) if available
  - venue_id, venue_capacity_utilization

Team-level rolling features (last N matches, both for and against):
  - points_per_match (last 5 / 10 / season)
  - goals_for, goals_against, goal_difference (last 5 / 10)
  - xG_for, xG_against (last 5 / 10) - shot-quality adjusted
  - shots_on_target, shots_total
  - clean_sheets_rate
  - cards_per_match (yellow, red) - feeds T3
  - possession_pct
  - pressing_intensity_proxy (opponent passes per defensive action)
  - form_weighted_by_recency (exponential decay over last K matches)
  - home_form vs away_form split
  - rest_quality (matches in last 7 days)

Head-to-head features:
  - last_5_h2h_outcomes (encoded), last_5_h2h_goals
  - home_win_rate_at_this_venue

T1-specific (match outcome):
  - elo_rating_home, elo_rating_away (we maintain our own rolling Elo)
  - elo_delta
  - betting_market_implied_odds (if we choose to use them - a signal,
    not the answer; including them risks leakage of "the market knows")
  - home_advantage_strength_for_this_team

T2-specific (goalscorers):
  - player_goals_per_90 (last 5 / 10 / season)
  - player_shots_per_90, shots_on_target_per_90
  - player_xG_per_90
  - player_minutes_played_recent (proxy for fitness)
  - player_is_penalty_taker
  - player_position (forward / mid / def encoded)
  - opponent_defensive_xG_against (positional)
  - team_attacking_share_of_player (% of team shots taken by player)
  - injury_doubt_flag

T3-specific (bookings):
  - referee_cards_per_match_avg
  - referee_strictness_score (cards per foul)
  - player_cards_per_90 (yellow, red)
  - player_position (defenders + DMs book more)
  - player_age (rough proxy for tactical fouls)
  - team_fouls_per_match
  - match_importance_score (high stakes -> more cards)
  - rivalry_indicator (derby boosts cards)
  - prior_h2h_cards

Features we explicitly EXCLUDE in v1 (to avoid leakage / complexity):
  - in-match live data (the model predicts pre-kickoff)
  - betting odds set within 1h of kickoff
  - any post-match stat from the match being predicted
  - lineups confirmed after this model is run (we use predicted XI)

**What the ML walkthrough doc covers.** A standalone learning artifact
under `docs/ml-walkthrough.md`. Structured so a smart engineer with no
prior ML can read it linearly and end up able to discuss models with
peers. Sections planned:

  1. What ML actually is (vs. statistics, vs. "AI"). When you'd reach for it.
  2. Supervised vs. unsupervised vs. RL. Why this is supervised.
  3. The pipeline: data -> features -> model -> evaluation -> deployment.
  4. Train / validation / test split. Why we need all three. Time-series
     splits (relevant here because matches are temporal).
  5. Feature engineering deep dive - every feature in the list above,
     with the trap each one carries.
  6. Multi-target prediction: when to use one model with multiple
     outputs vs separate models per target. Why we chose separate.
  7. Model families: linear models, trees, ensembles, neural nets.
     Plus Poisson regression for count data. Why we picked what we picked.
  8. The math of each chosen model - logistic + Poisson - just deep
     enough that the loss function and gradient step make sense.
  9. Overfitting + regularization. Cross-validation. Why we use
     time-series CV, not K-fold, on temporal data.
 10. Metrics per target: accuracy, log-loss, Brier, precision@k,
     mean absolute error, prediction interval coverage.
 11. Calibration - Platt scaling, isotonic regression, reliability
     diagrams. The full theory + the code we ran.
 12. Uncertainty quantification - bootstrap aggregation, prediction
     intervals, entropy. How L1/L2/L3 layers are computed.
 13. Why the model fails the way it fails. Concrete examples from
     our training set with the features that misled it.
 14. How to retrain, how often, what triggers retraining (drift
     detection on the calibration metric).
 15. How this is wired into Jytte's widget plugin.
 16. References + further reading.

**Architectural notes.**

  - New widget folder: `app/widgets/football/`
  - Data sources (multiple needed because no one free API gives us
    player + referee + xG data together):
      * football-data.org      -> fixtures, results, lineups, basic stats
      * Understat (scrape)     -> xG / xGA per team and per player
      * Fantasy Premier League -> player goals, minutes, prices (free, public)
      * fbref.com (scrape)     -> referee data, bookings, advanced stats
    Data layer abstracts these behind one `MatchRepository` interface.
  - Models:
      * T1 (1X2):        scikit-learn LogisticRegression (multinomial)
                         then LightGBM in a second pass.
      * T2 (goalscorers): scikit-learn LogisticRegression per player.
      * T3a (card count): scikit-learn / statsmodels Poisson regression.
      * T3b (booked player): scikit-learn LogisticRegression per player.
      * All wrapped in a custom `BootstrapEnsemble` (K=20) for epistemic
        uncertainty bands.
      * All calibrated via `CalibratedClassifierCV(method='sigmoid')`.
  - Library: scikit-learn + LightGBM + statsmodels (Poisson). No
    PyTorch / no neural nets - overkill and would obscure the lesson.
  - Training: a separate Python module, runs on demand (cli command
    or scheduled refresh). Persists `.joblib` per model to
    `/data/models/football/{target}/{version}.joblib`.
  - Inference: widget loads all models at startup; for each upcoming
    match runs all three targets in parallel.
  - Retraining cadence: weekly baseline + drift-triggered (when the
    rolling calibration metric crosses a threshold).
  - Storage: features dataset materialized as a Parquet file on the
    PVC so we don't re-fetch external APIs on every train.

**Open questions to lock before code (please answer in chat):**

  Q1. Which league(s)?
      Options: Danish Superliga only / English Premier League only /
               both / "top 5 European leagues". Smaller scope = faster
               train, fewer data quality issues, sharper teaching.
      Trade-off for the expanded prediction set: EPL has the richest
      free data (Understat, FPL API, FBref all cover it). Superliga
      coverage for player goals + bookings is thin.
      My recommendation: English Premier League for v1 (data wins).
      Layer Superliga in once the pipeline is proven.

  Q2. Confirm the multi-source data plan? Or restrict to one source
      and accept reduced T2/T3 quality?
      My recommendation: multi-source as listed above. The
      `MatchRepository` abstraction means each source is replaceable.

  Q3. Build all three targets at once, or ship 1X2 first then layer?
      Options:
        a) v1 = T1 only, v2 = +T2, v3 = +T3. Faster first delivery,
           ml-walkthrough stays simpler at v1.
        b) v1 = all three. Bigger build but the doc tells the full
           multi-target story in one read.
      My recommendation: (a). T1 lets us prove the pipeline + the
      uncertainty machinery on the simpler target before complicating
      everything with player-level data. The walkthrough doc still
      *covers* all three from v1; only the *code* lands in waves.

  Q4. Retraining cadence + how big a history window?
      My recommendation: weekly retrain, rolling 5-season window.
      Plus drift-triggered retrain when calibration crosses threshold.

  Q5. Where does the doc live?
      My recommendation: `docs/ml-walkthrough.md` as a single long-form
      MD file with images generated from the actual training (confusion
      matrix, learning curves, reliability diagrams, bootstrap bands).
      Also exposed as a route in the dashboard (`/docs/ml`) so it's
      read in-app, not just in the repo.

  Q6. Bootstrap ensemble size K?
      K=20 (default) gives reasonable epistemic bands at modest train
      cost. K=50 is more stable but 2.5x training time.
      My recommendation: K=20 in v1, knob exposed for experimentation.

**Acceptance criteria (when this feature is "done"):**

v1 (T1 only - match outcome):
  - [ ] `app/widgets/football/` plugin folder exists and is discovered
        by the registry on startup.
  - [ ] Dashboard shows upcoming matches with home/draw/away
        probabilities AND a confidence band (epistemic) AND a confidence
        badge (high/medium/low) computed per the formula above.
  - [ ] Clicking a match opens a "why" panel listing the top
        contributing features for the 1X2 prediction.
  - [ ] `python -m app.widgets.football.train` runs the full training
        pipeline (data fetch -> feature engineering -> CV training ->
        calibration -> bootstrap ensemble -> persistence).
  - [ ] Backtest metrics (accuracy, log-loss, Brier, calibration error)
        are printed during training and surfaced in the card footer.
  - [ ] `docs/ml-walkthrough.md` exists, covers all 16 sections above,
        and references the actual code we wrote (with line links).
  - [ ] Both the widget and the doc rebuild from `docker compose up
        --build` with no manual steps.

v2 (+ T2 goalscorers):
  - [ ] Per-player goalscorer model trained.
  - [ ] Top 3 likely scorers per side rendered on the match card.
  - [ ] Top-3 precision metric tracked in the card footer.

v3 (+ T3 bookings):
  - [ ] Poisson card-count model + per-player booking model trained.
  - [ ] Predicted total cards (with 50% interval) shown per match.
  - [ ] Top 1-2 likely booked players per side shown.
  - [ ] MAE on card count + recall@2 on booked-player tracked.

---

### F2 - Child activities finder ("Explorer")

**Purpose.** A web app (later: mobile) that makes it easy to find
things to do with the kids in a given area. Search by location +
category and get a curated, hopefully delightful, list of activities.
This is NOT a Jytte widget - it's a sibling app under the Jytte
umbrella that may eventually live at its own subdomain (e.g.
`activities.home.arpa`) and ship as a React Native / PWA mobile
build later.

**Activity categories (v1 wishlist):**

  - Playgrounds (legepladser)
  - Public swimming pools / svømmehaller
  - "Meet the animals" - petting zoos, farms, aquariums, dyrehaver
  - Indoor play centers (legeland) - useful in Danish winter
  - Outdoor events / festivals targeting kids
  - Museums with kid-friendly programs (børnemuseer)
  - Nature trails marked as kid-friendly
  - Library kids' events (børnebibliotek)
  - Cinemas with kids' showings

**Likely data sources:**

  - OpenStreetMap (via Overpass API) - playgrounds, swimming pools,
    zoos, libraries, museums. Free, comprehensive, no key. Best
    base layer.
  - KultuNaut (Danish cultural events API) - kids' events, museum
    programs, library events. Free API, needs registration.
  - VisitDenmark API / Naturstyrelsen - nature reserves with
    kid-friendly trails. Free.
  - Google Places API - paid above free tier, but best photos and
    opening hours. Optional enrichment layer.
  - Manual curation - some places worth bookmarking manually
    (e.g. specific Trustworks-area gems).

**Tech stack proposal (open question):**

  - Backend: Python FastAPI service. Lives at `apps/activities/`
    as a sibling of `app/` (the Jytte dashboard) OR in its own repo.
    Shares Jytte's container infrastructure (same Docker Compose,
    same k3s namespace) but its own database.
  - Frontend v1 (web): React + Tailwind, served as a static SPA via
    the FastAPI backend. Map view (Leaflet + OSM tiles) + list view.
  - Frontend v2 (mobile): React Native with Expo, sharing as much of
    the v1 codebase as possible (consider RNW or Tamagui).
  - Storage: Postgres with PostGIS for spatial queries (find
    playgrounds within X km of point). Lightweight - one new pod.
  - Search: full-text via Postgres tsvector for v1; opensearch only
    if scale demands it.

**Why this is a separate app from Jytte:**

  - Different consumer (the whole family vs Nichlas's work brain)
  - Different lifecycle (Jytte refreshes feeds every X min; this
    serves user queries on demand)
  - Different UI paradigm (map-centric, mobile-first)
  - Different data layer (geospatial)
  - Keeping it separate means Jytte stays a "dashboard for me" and
    Activities stays a "tool for the family"

**Open questions to lock before code:**

  Q1. Geography to support in v1?
      Options: just Hillerød / Copenhagen / all of Denmark / Denmark
      + Sweden cross-border. Recommendation: all of Denmark with
      good performance around Hillerød + Copenhagen.

  Q2. Sibling repo, sibling folder, or new top-level project?
      Recommendation: sibling folder `apps/activities/` under the
      jytte repo for now. Easy to extract into its own repo later.

  Q3. Authentication? LAN-only (like Jytte) or public-facing?
      If public, what auth?
      Recommendation: LAN-only via Tailscale for v1 (you access from
      phone via Tailscale). Public + auth is a follow-up.

  Q4. Mobile build approach v2?
      Options: React Native (most native feel), Capacitor (wraps the
      web app as a mobile app, minimal extra work), or PWA (good
      enough for "save to home screen" without app store).
      Recommendation: PWA first (~zero extra code), React Native
      only if PWA can't deliver.

  Q5. Should it integrate WITH Jytte? E.g. tasks tagged
      "weekend-activity" auto-link to a saved activity?
      Recommendation: not in v1 - keep it standalone, focus on the
      core search experience first.

**Acceptance criteria (v1 web):**

  - [ ] `apps/activities/` exists as a runnable FastAPI app
  - [ ] Map + list view of activities in the area
  - [ ] Filter by category (playground, pool, animals, etc.)
  - [ ] Filter by radius from a given point (autodetect via browser
        geolocation OR manual address search)
  - [ ] At least 3 data sources merged (OSM, KultuNaut, one more)
  - [ ] Tap an activity -> detail page with photos (where available),
        opening hours, address, "how to get there" map link
  - [ ] Save favourites locally (browser localStorage in v1)
  - [ ] Deployable to k3s alongside Jytte under separate ingress

---

### F3 - Custom MCP server (from scratch, learning exercise)

**Purpose.** A standalone, hand-rolled MCP server - NOT using FastMCP
- built specifically so Nichlas understands the protocol by writing
it. The deliverable pair, like F1, is the working server PLUS a
walkthrough doc at `docs/mcp-walkthrough.md`.

This is explicitly NOT a "make Jytte's MCP better" task. Jytte's
current MCP layer (`app/mcp_server.py`) uses FastMCP and is fine. F3
is a separate teaching artifact.

**What the server does.** Small enough to be readable, real enough to
prove the protocol works. My proposal: a server that exposes 3-4
tools wrapping the Jytte dashboard's data, but implemented from
scratch using only the JSON-RPC spec and Starlette. Examples:

  - `tool: latest_news` - returns the cached news items
  - `tool: open_tasks` - returns the cached tasks
  - `tool: world_severity` - returns the per-country crisis map
  - `resource: jytte://about` - a description of the server

It runs as a separate small FastAPI/Starlette app at `mcp/` in the
repo. Could be Dockerized separately if you want it deployable, or
just run locally with `uv run` / `python -m mcp_learn`.

**What the walkthrough doc covers.**

  1. The problem MCP solves. Why it's not just another REST API.
  2. The relationship between Hosts (Claude Desktop/Code), Clients,
     and Servers.
  3. JSON-RPC 2.0 - the actual wire protocol. We write our own
     parser to make this concrete.
  4. Initialization handshake: `initialize`, `initialized`, capability
     negotiation.
  5. The three primitives: tools, resources, prompts. When to use which.
  6. Schema validation - how clients know how to call your tool.
  7. Transports: stdio vs streamable-http vs SSE. We implement
     streamable-http from scratch.
  8. Error handling and the JSON-RPC error codes.
  9. Server-initiated notifications (e.g. `tools/list_changed`).
 10. Security: who can call what; the trust model.
 11. Comparing what we wrote to what FastMCP does for you (and
     when you'd choose one vs. the other).
 12. Connecting our server to Claude Code as a smoke test.

**Open questions to lock before code:**

  Q1. Where does this live? Options:
       - `mcp/` folder in the jytte repo (sibling to `app/`)
       - separate repo `jytte-mcp-learn` on your home GitLab
      My recommendation: sibling folder. Keeps everything in one place.

  Q2. Language?
       - Python (matches the rest of the stack)
       - TypeScript (MCP's reference SDK is TS - more idiomatic)
      My recommendation: Python. Stack consistency wins; the protocol
      is language-agnostic anyway.

  Q3. Tools to expose? The 3-4 example tools above, or something
      different (e.g. tools that operate on your Obsidian vault, or
      a calculator, or weather)? Calculator + weather is more
      "MCP textbook example". The Jytte-wrapping tools have the
      advantage of being immediately useful.

  Q4. Transport? My recommendation: streamable-http first (because
      that's what we use in Jytte). Optional stdio in an appendix.

**Acceptance criteria:**

  - [ ] `mcp/` folder exists with a runnable server.
  - [ ] No use of the `mcp` Python package (we're learning by NOT
        using the abstraction). Only `httpx` / `starlette` / `pydantic`
        / standard library.
  - [ ] Server implements `initialize`, `tools/list`, `tools/call`
        and at least one of `resources/list`, `resources/read`.
  - [ ] You can connect Claude Code to it and successfully invoke a
        tool end-to-end.
  - [ ] `docs/mcp-walkthrough.md` exists and is paired with the code.
  - [ ] A small test suite proves the protocol contract.

### F4 - Azure DevOps widget

**Purpose.** Add a dashboard card that surfaces *your* current Azure
DevOps state for the customer engagement(s) you are active on
(Dagrofa today, others later). The widget pulls three signals into one
glanceable place so you do not have to context-switch into the ADO web
UI to know "is anything on fire or waiting for me right now":

  P. Active pull requests
       - PRs where you are the author, with review state per reviewer
       - PRs where you are a required reviewer and have not yet voted
       - Optionally: PRs where any reviewer has voted "waiting" or
         "rejected" so blocked work surfaces fast
       - All PR`s

  B. Pipelines (Builds + Releases)
       - Currently running runs (with elapsed time)
       - Runs that finished in the last 24h, with a check/cross per run
       - A red-fail pill when the most recent run on the default branch
         is a failure (so you see drift on `main` quickly)
       - Optional drill into the failed log lines (see open question Q5)

  T. Taskboard work items
       - Work items currently assigned to you in the active sprint /
         iteration, grouped by state (To Do / In Progress / Done-today)
       - Tags / area path visible so you can tell customer / internal
       - Recently transitioned items (the "moved to Done" stream gives
         a quiet sense of throughput per day)

For each section the widget also shows:

  - A header pill with the count + a "needs you" badge when there is
    something blocking you (PR awaiting your review, failing pipeline
    on default branch, task transitioned to you since last refresh).
  - Per-row click opens a drawer with the full item detail (mirrors
    the football widget's drawer pattern).
  - The same SSE-driven live refresh other widgets use - no manual
    reload required.

**Data sources.** Azure DevOps REST API (`dev.azure.com/<org>`):

  - `GET /<org>/<project>/_apis/git/pullrequests?searchCriteria.status=active`
    with `creatorId` for "my PRs" and `reviewerId` for "PRs awaiting me".
  - `GET /<org>/<project>/_apis/build/builds?statusFilter=...&resultFilter=failed,canceled,succeeded`
    filtered by `branchName=refs/heads/main` for the default-branch
    red-fail pill, and unfiltered for the last-24h roll-up.
  - `GET /<org>/<project>/_apis/release/releases?statusFilter=active`
    (only if you actually use classic Releases - skip if pipelines-only).
  - `POST /<org>/<project>/_apis/wit/wiql` with a stored WIQL query
    (`SELECT [System.Id]... WHERE [System.AssignedTo] = @Me AND
    [System.IterationPath] UNDER 'Project\Sprint X'`) for the sprint
    board view. Backed by `GET /_apis/work/teamsettings/iterations`
    to discover the current iteration automatically.

Authentication is **Personal Access Token (PAT)** for v1. OAuth /
Entra ID is a clean follow-up but PAT is fewer moving parts and
matches how you already authenticate against ADO from CLI.

**Architectural notes.**

  - New widget folder: `app/widgets/azuredevops/`
  - `manifest.yaml`:
      * `refresh_minutes: 5` (PR state churns fast)
      * `client_refresh_seconds: 60`
      * `claude_analyzer: false` (no LLM in the hot path; chat can
        still pull the cached summary)
      * `expose_mcp: true` (tools: `ado_my_prs`, `ado_pipelines_status`,
        `ado_my_tasks`)
  - One `fetch.py` that calls the three ADO endpoints in parallel via
    `asyncio.gather` and merges into a single dict per section. Errors
    in any one section degrade gracefully (the other two still render).
  - One small `ado.py` client module wrapping `httpx.AsyncClient` with
    `auth=(PAT_USER, PAT_TOKEN)` and a tiny in-memory cache (60s) for
    iteration / repo metadata that never changes mid-day.
  - Environment variables (read at startup, surfaced in docker-compose
    + `.env.example`):
      * `JYTTE_ADO_ORG`           - org slug, e.g. `dagrofa-trustworks`
      * `JYTTE_ADO_PROJECT`       - project name (or comma list, see Q1)
      * `JYTTE_ADO_PAT`           - PAT token (secret)
      * `JYTTE_ADO_USER_EMAIL`    - for "@Me" mapping in WIQL +
                                    creator/reviewer matching on PRs
      * `JYTTE_ADO_TEAM`          - optional, defaults to project's
                                    default team (used for iteration
                                    discovery)
  - K3s deploy: add the PAT to `secret.example.yaml`.
  - The widget tolerates "no ADO config" gracefully (renders a
    "configure ADO_* env vars" empty state, same shape as the
    football "no model yet" placeholder).

**Open questions to lock before code:**

  Q1. Single project or multiple?
      Right now you are active on Dagrofa, but Trustworks-internal
      ADO also exists. Options:
        a) Single `JYTTE_ADO_PROJECT` for v1; add multi-project as v2. First project will be Trustworks App
        Solution:a

  Q2. "My" PRs definition
      Three reasonable lenses:
        a) Author = me  (you opened it)
        b) Reviewer = me, not yet voted  (you owe a review)
        Solution:a and b. 

  Q3. Pipelines scope
      ADO has both Build (modern YAML pipelines) and Release (classic).
      Options:
        a) Pipelines only (the modern `pipelines` API).
        b) Pipelines + classic Releases.
      Solution:(a). 
      Dagrofa uses modern pipelines; we only
      add Releases if a future customer needs them.

  Q4. Default-branch red-fail pill
      When the most recent run on `main` is a failure, show a
      prominent red banner on the card header until the next green
      run lands. Worth the extra polling, or noise?
      My recommendation: keep it. This is the single most useful
      signal in the whole widget for the kind of work you do.
      Solution: Do it!

  Q5. Failed-log drill-in
      Should clicking a failed pipeline open a drawer showing the
      last ~50 lines of the failing log, or just link out to ADO?
      Options:
        a) Link out (one extra API call avoided)
        b) Drawer with last log lines (one extra API call, more
           context without leaving Jytte)
      Solution: a for v1. 
      Maybe later adding log fetching is a relevant
      v1.1, but only if the link-out turns out to be friction.

  Q6. Taskboard scope
      Options:
        a) Current iteration only, assigned to me.
        b) Current iteration only, all states except Done/Removed.
        c) All open items assigned to me regardless of iteration.
      Solution: a. 
      Future dev may look into c, or a buttom to open the task board in ADO

  Q7. Refresh cadence
      ADO has soft rate limits (~200 requests / 5 minutes per IP per
      user) and your widget will issue 3-4 calls per refresh.
      Options:
        a) 5 minutes (default).
        b) 2 minutes (snappier but ~3x the load).
      Solution: a and a manual "refresh now" button on the card header, and the widgets refresh shall not be linked to other refresh or update buttons on the page- 

  Q8. Auth
      My recommendation: PAT in v1. Document the minimal scopes
      needed (Code: Read, Build: Read, Work Items: Read). OAuth /
      Entra ID as a follow-up if/when this widget needs to write.
      Solution: PAT

  Q9. Notifications
      Should a *new* failed pipeline on `main`, or a *new* PR awaiting
      your review, push an SSE event that flashes the card / browser
      title in addition to the regular refresh?
      Solution: yes for both, gated behind a tiny "muted"
      toggle (per-section) stored client-side. Cheap to add since SSE
      is already wired.
  

  Q10. Privacy / secret handling
      PAT goes in `.env` + k3s Secret. We never log it, never echo it
      via `/health`, never include it in MCP tool output.
      Solution: Goes into .env file

**Acceptance criteria (v1):**

  - [x] `app/widgets/azuredevops/` plugin folder exists and is
        discovered by the registry on startup.
  - [x] Dashboard card shows three sections: PRs, Pipelines,
        Taskboard, each with count badge + "needs you" indicator
        where applicable.
  - [x] Active PRs (authored by me) and PRs awaiting my review are
        clearly separated.
  - [x] Pipelines section shows currently running + last 24h, with
        a red-fail pill when latest default-branch run failed
        (per Q4; default branch resolved per-repo, not hardcoded to `main`).
  - [x] Taskboard shows current-iteration items assigned to me,
        grouped by state.
  - [x] Clicking any row opens a detail drawer (same pattern as
        football + tasks widgets).
  - [x] MCP tools `ado_my_prs`, `ado_pipelines_status`, `ado_my_tasks`
        exist and return the cached state.
  - [x] Widget renders an actionable empty state when ADO env vars
        are missing.
  - [x] PAT is never logged. `/health` does not leak it.
  - [x] Runs locally via `docker compose up` (env vars wired through
        docker-compose.yml). k3s Secret stub added to
        `deploy/k8s/secret.example.yaml` for the home-server path.

**Verified live** against `Trustworks/App` during build:
PRs (7 authored, 1 awaiting review), Pipelines (6 runs in last 24h,
0 failing on default), Sprint board (3 items in `App\Sprint 3`).

**v1.1 ideas (parking, not committed):**

  - Stale-PR warning (PR open > N days with no activity).
  - Per-pipeline trend sparkline (last 20 runs, green/red dots).
  - Drawer that shows the last ~50 log lines of a failing pipeline
    (Q5 option b).
  - Cross-project rollup (multiple `JYTTE_ADO_PROJECT` values).

### F5 - n8n integration substrate (hybrid)

**Purpose.** Move deterministic, scheduled, API-bound work off the
Python process and into n8n - while keeping Jytte's dashboard, MCP
server, chat layer, and ML widgets exactly where they are. This is
explicitly NOT a rewrite of Jytte. It is the introduction of n8n as
an integration sidecar that owns "fetch from external service on a
schedule, normalize, write into Jytte's cache".

The principle being codified (saved as durable feedback in memory):
**AI runs over already-fetched state, never as the fetcher itself.**
n8n now owns the fetcher half; Jytte owns the reasoning + UI half.

**What changes (in scope for F5 v1):**

  - n8n runs alongside Jytte: same Docker Compose stack for dev,
    same k3s namespace in production.
  - **ADO is the pilot.** The full F4 widget API surface
    (PRs / pipelines / WIQL tasks) moves out of `app/widgets/azuredevops/ado.py`
    and into an n8n workflow that runs on the same 5-minute cadence
    and writes results into Jytte's SQLite via a new internal HTTP
    endpoint.
  - After the pilot proves the pattern, **news (RSS) and geomap
    (RSS + ACLED)** migrate. Both are pure schedule + fetch +
    transform, ideal for n8n.

**What explicitly does NOT move (out of scope, ever, for this pattern):**

  - **Dashboard** (FastAPI + HTMX + Jinja, asymmetric grid, drawer
    pattern, SSE refresh stream). n8n has no dashboard primitive
    worth using here.
  - **MCP server** (`app/mcp_server.py` + per-widget `mcp.py`). n8n
    has webhooks, not MCP. Claude Code talks to Jytte directly.
  - **Chat endpoint** (`/chat`, Claude over cached widget summaries).
    Reasoning over state belongs in Python next to the cache.
  - **Football widget** (scikit-learn, bootstrap ensemble, 9 figures,
    walkthrough doc generation). No n8n native equivalent for
    scikit-learn; subprocess hacks are worse than the status quo.
  - **Tasks widget** (Obsidian folder watcher via `watchdog`). n8n
    can poll a path but cannot subscribe to inotify events from
    inside a different container reliably; the existing file-watcher
    is fast and correct.
  - **Widget plugin registry** (`app/registry.py`). The discovery /
    lifecycle / SSE-broadcast pattern is value Jytte already
    provides; n8n would not replace it, only feed into it.

**Architecture (the only diagram in this spec).**

```
                                +---------------------+
                                |        n8n          |   workflows:
                                |  (same k3s ns       |   - azuredevops fetch (F5 v1)
                                |   as jytte)         |   - news rss fetch (F5 v1.1)
                                +-----+--------+------+   - geomap rss+acled (F5 v1.2)
                                      |        |
                       (fetches)      |        |  (POST cached state with secret header)
                                      v        v
   +-----------+ ext APIs        +--------+    +---------------------+
   | ADO / RSS |<----------------+ workflow|--> | POST /widgets/<n>/  |
   | ACLED ... |                 | nodes  |    |   state             |
   +-----------+                 +--------+    +----------+----------+
                                                          |
                                                          v
                                            +-------------+-------------+
                                            |  Jytte FastAPI            |
                                            |  +-------------------+    |
                                            |  | sqlite cache      |<-- widget reads here
                                            |  +-------------------+    |
                                            |  + dashboard / MCP /      |
                                            |    chat / football / etc. |
                                            +---------------------------+

   user ──HTTPS──> Jytte dashboard ──(only when asking a reasoning question)──> Claude
```

n8n produces; Jytte consumes + reasons + renders.

**Per-widget changes after migration.**

  - `app/widgets/azuredevops/ado.py`           -> archived (gone)
  - `app/widgets/azuredevops/fetch.py`         -> reads cached state, no HTTP
  - `app/widgets/azuredevops/manifest.yaml`    -> new `source: n8n` field;
                                                  `refresh_minutes: null` (n8n
                                                  schedules, not APScheduler)
  - `app/widgets/azuredevops/mcp.py`           -> unchanged (still serves cache)
  - `app/widgets/azuredevops/routes.py`        -> unchanged (drawer still reads cache)
  - `app/widgets/azuredevops/card.html`        -> unchanged
  - `deploy/n8n/workflows/azuredevops.json`    -> new (git-committed workflow)
  - `app/main.py`                              -> new POST /widgets/{name}/state
                                                  protected by X-Jytte-Internal-Secret
  - `docker-compose.yml`                       -> add n8n service + JYTTE_INTERNAL_SECRET
  - `deploy/k8s/n8n.yaml`                      -> new n8n Deployment + Service + PVC
  - `deploy/k8s/secret.example.yaml`           -> add JYTTE_INTERNAL_SECRET + n8n auth env

**How the Integrations agent + per-service skills adapt.**

The pattern stays. What changes is *who* invokes the skill.

  - **Before F5**: the agent reads the skill, calls the API directly
    on each invocation.
  - **After F5**: the skill is the API contract reference. The
    *workflow* (built once, runs every 5 minutes) is the operational
    implementation. The agent only invokes the API directly when the
    user asks an *ad-hoc* question that wouldn't benefit from a
    cached background fetch ("what was the status of build #1234
    yesterday at 3pm?"). For dashboard data, the agent reads
    `/widgets/azuredevops` JSON instead of calling ADO itself.

The `azure-devops` skill gets a new section: **"How this is wired
through n8n"** documenting which nodes the workflow uses, the
mapping from skill operations to workflow steps, and where the
workflow JSON lives.

**Open questions to lock before code:**

  Q1. n8n deployment topology
      Options:
        a) Sidecar in the same docker-compose / same k3s pod as Jytte
        b) Separate service in the same Docker Compose stack +
           separate Deployment in the same k3s namespace
      Recommendation: (b). Independent lifecycle, independent
      restart, separate logs. n8n is heavy enough (Node + Postgres-
      backed queue mode optional) that pod-sharing causes resource
      contention.
      Solution: b

  Q2. Sync direction: push from n8n, or pull from Jytte?
      Options:
        a) n8n pushes to Jytte via HTTP POST after each workflow run
        b) Jytte polls n8n's "executions" API on a schedule
      Recommendation: (a). Push is simpler, lower latency, and means
      Jytte doesn't need to know n8n's internal API. If n8n is down,
      pushes simply stop and Jytte keeps showing the last-known-good
      state with a "stale" indicator.
      Solution: A

  Q3. Auth between n8n -> Jytte
      Options:
        a) Shared secret header (`X-Jytte-Internal-Secret`)
        b) mTLS via k3s service-account
        c) k3s NetworkPolicy + cluster-internal-only Service (no auth)
      Recommendation: (a) for v1. Cheap, debuggable, works the same
      in Docker Compose and k3s. (b) is a follow-up if we ever
      expose Jytte's API to anything beyond this trust boundary.
      Solution: A for now in the future option c should be an option to tap into if wanted

  Q4. Workflow source of truth
      Options:
        a) n8n's own database (Postgres or SQLite) - workflows live
           there and are exported manually
        b) Workflows live as JSON in `deploy/n8n/workflows/` in this
           repo and are auto-imported on n8n startup
      Recommendation: (b). Git-tracked, diffable, deployable. The
      n8n DB still exists for execution history but workflows are
      always re-derived from git on container start.
      Solution: (b). Workflows live as JSON in `deploy/n8n/workflows/`,
      auto-imported by an init script on container start. Editing
      loop: iterate in the n8n UI -> Export -> overwrite the JSON
      file -> commit. A short "How to edit a workflow" section goes
      into `deploy/n8n/README.md` for future-us.

  Q5. SQLite write contract
      Options:
        a) HTTP endpoint `POST /widgets/{name}/state` on Jytte
        b) n8n writes directly to the SQLite file via a shared PVC
      Recommendation: (a). Direct DB writes from another process to
      SQLite are fragile (locking, schema drift, no atomic upsert
      semantics enforced). HTTP gives us versioning, schema
      validation, and proper auth.
      Solution: a

  Q6. Graceful degradation when n8n is down
      Recommendation: the widget renders the last-known-good state
      with a "stale: N minutes" indicator. After 3x the expected
      refresh interval with no update, the indicator escalates
      visually. Nothing crashes. Same pattern Jytte already uses
      when ANTHROPIC_API_KEY is missing.
      Solution: Retry-with-jitter + escalating health response.

        - Each workflow execution that succeeds POSTs the result to
          `/widgets/<n>/state`.
        - Each workflow execution that FAILS POSTs the error code +
          short message + execution ID to `/widgets/<n>/error`
          (n8n's "Error Trigger" node calls this endpoint).
        - Jytte tracks per-widget `consecutive_failures` and
          `last_error`. The card always renders the last successful
          state plus a freshness banner showing: time since last
          good fetch, failure count, and the most recent error code.

        Escalation ladder:
          - 1 failure  : show error code inline, retain last-good data.
          - 3 failures : Jytte's watchdog health-checks n8n's
                         `/healthz`. If unreachable AND the env flag
                         `JYTTE_AUTO_RESTART_N8N=true` is set, Jytte
                         issues a one-shot restart (Docker socket in
                         dev, k3s API delete-pod in prod). The
                         restart is logged + surfaced in the banner.
          - 6 failures : banner exposes a "View n8n logs" link that
                         opens the n8n execution-history UI for that
                         workflow (n8n's own page at
                         `<n8n>/workflow/<id>/executions`).

        Dashboard NEVER crashes from an external error. Counter
        resets after the next successful POST.

        Security note: the auto-restart capability requires Jytte to
        hold either docker.sock access (dev) or a k3s ServiceAccount
        with pod-delete RBAC (prod). Gated behind the env flag and
        OFF by default; user opts in explicitly. When OFF, the
        watchdog still tracks + displays health but does not act.

  Q7. Pilot scope confirmation
      F5 v1 = ADO migration only. F5 v1.1 = news. F5 v1.2 = geomap.
      Football, tasks, dashboard, MCP, chat, registry all stay
      Python-native forever. **Locked per user instruction.**
      Solution: Agree

  Q8. n8n licensing
      n8n is "fair-code" (Sustainable Use License) - free for
      personal + internal-business use up to limits, paid above.
      For home + Trustworks-internal use this is fine.
      Recommendation: document the license boundary in the workflow
      README so future-us doesn't accidentally cross it.
      Solution: Agree

**Acceptance criteria (v1 - ADO pilot):**

  - [x] n8n service runs alongside Jytte in `docker-compose.yml`,
        with workflows volume-mounted from `deploy/n8n/workflows/`.
  - [x] `deploy/k8s/n8n.yaml` deploys n8n in the `jytte` k3s
        namespace with persistent storage for execution history.
  - [x] `deploy/n8n/workflows/azuredevops.json` is the committed
        source-of-truth for the ADO workflow.
        **Status**: Phase 2/3 ships a smoke-test workflow (schedule
        trigger -> single fetch -> Jytte /state POST + ErrorTrigger
        branch). Expanding to the full 11-call chain happens in the
        n8n UI per the Q4 editing loop, then exported.
  - [ ] The workflow performs the same 11 calls F4 makes today
        (per `docs/azuredevops-api-walkthrough.md`) on a 5-minute
        cron, normalises the result, and POSTs the same JSON shape
        that `fetch.py` currently produces.
        **Status**: pending UI expansion (Phase 3 visual step).
  - [x] Jytte exposes `POST /widgets/{name}/state` gated by
        `X-Jytte-Internal-Secret`. Writes upsert a row into the
        existing state table and broadcast an SSE update.
  - [x] Jytte also exposes `POST /widgets/{name}/error` (same auth)
        for the n8n Error Trigger node. Records `last_error` +
        increments `consecutive_failures` on the same row.
  - [x] A new SQLite column `consecutive_failures` (int, default 0)
        and `last_error` (json, nullable) is added to `widget_state`.
        Reset to 0 on successful state POST.
        (Also added `last_success_at` so the freshness banner can
        show time-since-last-good independently of failure
        timestamps.)
  - [x] A Jytte watchdog job (APScheduler, 60s cadence) reads
        per-widget freshness and:
          (1) at 3 consecutive failures health-checks n8n's
              `/healthz`,
          (2) at 3 failures AND `JYTTE_AUTO_RESTART_N8N=true` AND
              n8n unreachable -> issues a one-shot restart via
              docker.sock (dev) or k3s API (prod),
          (3) at 6 failures surfaces a "View n8n logs" link in
              the widget banner that opens the n8n execution-history
              page for that workflow.
        Restart SDKs are optional deps (commented in requirements.txt);
        without them the watchdog logs the intent and continues.
  - [x] `JYTTE_AUTO_RESTART_N8N` defaults to `false`. Documented
        security trade-off captured in `deploy/n8n/README.md`.
  - [x] Card banner pattern is uniform across all widgets that use
        the F5 substrate: "updated N min ago :: failures M :: <error
        code if M>0>". Stable visual treatment regardless of widget.
        Implemented as `app/templates/freshness_banner.html`
        included from each F5-receiver widget's `card.html`.
  - [x] Widget can declare `source: n8n` in its `manifest.yaml`,
        which disables the local APScheduler refresh and routes all
        state through the POST endpoints.
  - [ ] `app/widgets/azuredevops/fetch.py` becomes a state reader
        only - no httpx, no ADO knowledge. ~30 lines max.
        **Status**: pending Phase 5 cutover (flip after live n8n
        push verified).
  - [ ] `app/widgets/azuredevops/ado.py` is deleted; the
        `azure-devops` skill grows a "wired through n8n" section.
        **Status**: pending Phase 5 cutover.
  - [ ] When n8n is stopped, the card still renders with a
        "stale: N min" badge and does not crash.
        **Status**: machinery in place (banner reads
        last_success_at); end-to-end verification pending live boot.
  - [ ] PAT lives in n8n's credentials store (encrypted at rest)
        plus optionally in Jytte's env (for ad-hoc agent use). It
        does not flow over the n8n -> Jytte boundary in either
        direction.
        **Status**: v1 smoke workflow pulls PAT from `$env.AZDO_PAT`
        for simplicity; v1.1 moves it to n8n credential store.
  - [ ] `features.md` F4 acceptance criteria stay green - users see
        the same card, same drawers, same MCP tools, same data.
        **Status**: pending Phase 5 cutover + live test.
  - [ ] One end-to-end smoke test: stop Jytte's old fetcher path,
        bring up n8n, refresh dashboard, see the same 7 PRs / 6 runs
        / 3 sprint items as the F4 baseline.
        **Status**: pending live `docker compose up`.

**Phase 5 cutover checklist (after n8n live + workflow verified):**

  1. Edit `app/widgets/azuredevops/manifest.yaml`, set `source: n8n`.
  2. Confirm in dashboard: AZDO card now driven entirely by n8n
     pushes. Local refresh button is a no-op.
  3. Strip `app/widgets/azuredevops/fetch.py` to a state-reader
     (~30 lines: read cached payload + enrich for card; same shape
     as today's fetch.py output).
  4. Delete `app/widgets/azuredevops/ado.py`.
  5. Update `~/.claude/skills/azure-devops/SKILL.md` with a
     "Wired through n8n" section pointing at
     `deploy/n8n/workflows/azuredevops.json`.
  6. Restart Jytte; verify same 7 PRs / 6 runs / 3 sprint items.

**Acceptance criteria (v1.1 - news migration):**

  - [ ] News RSS workflow in `deploy/n8n/workflows/news.json`.
  - [ ] `app/widgets/news/` fetch.py becomes a state reader.
  - [ ] Claude analyzer stays Python (it's reasoning, not fetching).

**Acceptance criteria (v1.2 - geomap migration):**

  - [ ] Geomap workflow handles RSS + ACLED via two parallel
        branches in one workflow.
  - [ ] Gazetteer + severity scoring stay Python (reasoning + spatial
        joins, not fetching).

**Non-goals (do NOT do as part of F5):**

  - Migrating the football widget (ML pipeline stays Python).
  - Migrating the tasks watcher (filesystem watcher stays Python).
  - Replacing the dashboard with n8n's UI (n8n's UI is for flow
    editing, not consumption).
  - Replacing the MCP server with n8n webhooks.
  - Moving the `/chat` Claude integration into n8n (reasoning lives
    next to the cache).
  - Migrating workflow execution history out of n8n (n8n owns its
    own observability).

**Rollback plan.**

If the F5 pilot reveals show-stoppers (latency, complexity, n8n
upgrade pain), reverting is a single commit:

  - Restore `app/widgets/azuredevops/ado.py` from git.
  - Restore the original `fetch.py`.
  - Remove the n8n service from compose / k3s.
  - The `POST /widgets/{name}/state` endpoint can stay - it is
    generally useful (manual data injection, future ingestion
    paths) but becomes orphan code if no caller uses it.

The rollback is cheap because Jytte's plugin-folder widget model
already lets each widget pick its data source independently.

### F6 - Editable tasks (Obsidian + ADO)

**Purpose.** Let the user act on the dashboard, not just look at it. Two
sources, same UX shape:

  - **Obsidian tasks**: change status / priority / due from the drawer
    (or one-click "mark done" from the card row).
  - **ADO work items**: change the state from the drawer (To Do →
    Active → Resolved → Closed → Removed). Comments + assignee come in
    v1.1.

The principle (saved as memory in this session): **AI runs over cached
state, never as the fetcher**. F6 adds a third rule by analogy:
**writes are user-initiated and latency-sensitive, so they go direct
from Jytte to the source - not through n8n**. n8n is the reader; Jytte
is the writer.

**What's already in place vs what's missing**

| Layer            | Obsidian                          | Azure DevOps             |
|------------------|------------------------------------|--------------------------|
| Write client     | `app/widgets/tasks/writer.py` ✓   | needs `ado_writer.py`    |
| HTTP route       | needs PATCH /widgets/tasks/edit    | needs PATCH /widgets/azuredevops/edit-item |
| Form in drawer   | needs HTMX form                    | needs HTMX form          |
| Card quick-action| needs "✓ done" button per row     | none (drawer-only)       |
| Refresh after    | watchdog/SSE already wired         | needs in-place cache patch + SSE |
| Audit trail      | none today                         | none today               |

**Architectural notes.**

  - **Writes never touch n8n.** Latency, simplicity, and the
    user-initiated nature put writes in Jytte. Reads still cut over
    to n8n per F5.
  - **Allowlist per widget.** `writer.py` already enforces
    `EDITABLE_FIELDS = {status, priority, due, category, customer,
    title, tags}`. The ADO writer gets the same shape, scoped to one
    field in v1 (`System.State`).
  - **State refresh.**
      * Obsidian: watcher already fires on file change → fetch
        re-reads → SSE. Free for us.
      * ADO: the PATCH response returns the updated work item; we
        in-place patch the cached SQLite row + emit SSE so the
        dashboard reflects the change without waiting for the next
        n8n tick.
  - **Audit.** Each edit appended to a new `widget_edits` table:
    `widget, target_id, field, old_value, new_value, at, source`.
    Always-on; useful for "what did I change today?" and for
    troubleshooting drift between widget and source-of-truth.
  - **Concurrency.** v1 = last-write-wins. v1.1 adds ETag /
    `If-Match: <rev>` for ADO.

**Open questions to lock before code:**

  Q1. Obsidian field scope
      Options:
        a) Status only (covers 80%: "mark done", "block", "resume")
        b) Status + priority + due (the three operational fields)
        c) Full EDITABLE_FIELDS set already in writer.py
        d) (c) + body text
      Recommendation: (b). Status is daily; priority+due weekly;
      everything else (body, category, customer, tags) is rarer and
      better done in Obsidian.
      Solution: (b)

  Q2. ADO field scope
      Options:
        a) State only (To Do/Active/Resolved/Closed/Removed)
        b) State + assignee
        c) State + assignee + add comment
        d) Full field editing
      Recommendation: (a) for v1. State transitions are the 80%
      action. Comments + assignee in v1.1.
      Solution: (a)

  Q3. UI placement
      Options:
        a) Inline in drawer: dl flips to form when "Edit" clicked
        b) Separate edit modal
        c) Quick-action buttons on the card row + drawer form
      Recommendation: (a) for the drawer; (c) ADDITIONALLY for
      Obsidian's card row only (one-click "✓ done"). ADO drawer-only
      because card rows already carry the pipeline + PR context and
      adding state-picker buttons there gets noisy.
      Solution: (a) + (c) - inline drawer form everywhere, plus
      one-click "done" on Obsidian card rows.

  Q4. ADO write path
      Options:
        a) Jytte → ADO REST API directly (PATCH /_apis/wit/workitems)
        b) Jytte → n8n webhook → ADO → result back to Jytte
      Recommendation: (a). Writes are user-initiated and need <1s
      latency. The F5 principle ("n8n for scheduled/deterministic
      fetches") explicitly does NOT cover writes. A small
      `ado_writer.py` handles the PATCH; reading still goes via n8n.
      Solution: (a) - direct Jytte -> ADO. n8n stays read-only.

  Q5. Optimistic UI vs wait-for-confirmation
      Options:
        a) Optimistic: paint the change immediately, rollback on error
        b) Wait: show a spinner until the source confirms
      Recommendation: (b) for v1. ADO PATCHes are 300-800ms which is
      fine to wait for. Obsidian writes are local (<50ms). Optimistic
      UI is a v1.1 polish if waiting feels slow.
      Solution: (b) - wait for confirmation.

  Q6. Concurrency
      Options:
        a) Last-write-wins (no checks)
        b) ETag / `If-Match: <rev>` on ADO
        c) Diff-warning if cached state differs from current server state
      Recommendation: (a) for v1. v1.1 adds (b).
      Solution: (a) - last-write-wins.

  Q7. Audit trail
      Recommendation: new SQLite table `widget_edits` capturing every
      change. Always-on, not configurable. Surfaces in a future "edit
      log" view but always written.
      Solution: accepted as recommended.

  Q8. Permissions / guardrails
      Recommendation: explicit field allowlist per widget (already
      done in Obsidian writer; mirror in ADO writer). **No deletes
      from the dashboard** in v1 - too dangerous, almost never wanted.
      Solution: accepted as recommended.

  Q9. Refresh strategy after edit
      Recommendation: for Obsidian rely on the existing file-watcher
      → fetch → SSE chain. For ADO, the PATCH response returns the
      updated work item; we apply it in-place to the cached state
      row and emit SSE immediately so the dashboard reflects the
      change without waiting for the next 5-minute n8n tick.
      Solution: accepted as recommended.

**Acceptance criteria (v1):**

  Obsidian:
  - [x] `POST /widgets/tasks/edit` endpoint wraps `writer.edit_task()`.
        Accepts form fields `path` + `status?` + `priority?` + `due?`
        per Q1.
  - [x] Drawer has an "edit" toggle that swaps the `<dl>` for an HTMX
        form with status / priority / due inputs. Cancel returns to
        view mode.
  - [x] Card row has a one-click "✓ done" button per task. Sets
        `status: done`; writer auto-sets `done = <today>` field.
  - [x] After save, watcher fires → fetch re-reads → SSE refreshes
        the card. Drawer re-renders in view mode showing new values.

  ADO:
  - [x] `app/widgets/azuredevops/ado_writer.py` with
        `patch_workitem(item_id, fields) -> dict`.
        Hits `PATCH /_apis/wit/workitems/{id}` with
        Content-Type: application/json-patch+json.
        Field allowlist: `System.State` only in v1.
  - [x] `POST /widgets/azuredevops/edit-item` endpoint accepts form
        fields `id` + `state`, calls `patch_workitem`, in-place
        patches the cached widget payload via
        `db.patch_widget_payload`, emits SSE, returns re-rendered
        drawer.
  - [x] Detail drawer for work items shows valid state transitions
        as a `<select>`; submitting POSTs to the new endpoint.
  - [x] State change visible on dashboard within ~1s (the in-place
        cache patch happens synchronously inside the same request).

  Cross-cutting:
  - [x] New `widget_edits` SQLite table (`widget`, `target_id`,
        `field`, `old_value`, `new_value`, `source`, `at`); every
        successful edit logged via `db.record_edit()`.
  - [x] Failed ADO edits re-render the drawer with a red error pill
        above the form (`edit_error` template var); cache stays
        untouched.
  - [x] No write code touches n8n. The whole F6 path is direct
        Jytte → source-of-truth.
  - [x] Unit smoke test passes: Obsidian writer mutates the file,
        the `done` date auto-sets on status→done, audit captures
        both fields, path traversal is blocked, non-allowlisted
        fields are silently ignored, `patch_widget_payload` mutates
        cached row in place.
  - [ ] ADO live PATCH validated end-to-end (live test inside the
        running stack; pending you running `docker compose up`).

**v1.1 ideas (parking, not committed):**

  - ADO comments (`POST /_apis/wit/workitems/{id}/comments`)
  - ADO assignee change (`System.AssignedTo` allowlist)
  - Optimistic UI for ADO state changes (sub-second perceived latency)
  - ETag / If-Match for ADO concurrency
  - Edit log viewer page (`/edits?widget=...`)
  - Obsidian body editing (probably better as "open in Obsidian"
    deep-link, which detail.html already has)

### F7 - Family budget planner

**Purpose.** A simple browser-editable family budget in Jytte. Holds
the recurring household expenses (car, electricity, mortgage, house,
food, internet, insurance, subscriptions) plus income lines. Lives in
the same SQLite DB Jytte already uses; reachable from any device on
the LAN.

**Scope, v1 (this skeleton):**

  - Two tables: `budget_categories` (slug, name, kind) and
    `budget_entries` (category, name, amount, recurrence, due, notes).
  - Pre-seeded categories: car / electricity / mortgage / house / food
    / internet / insurance / subscriptions / other-expense /
    salary / other-income.
  - HTMX inline form to add + edit + delete entries.
  - `/budget` page grouping entries by category, showing monthly and
    annual totals.
  - Dashboard card with a compact "monthly net" view.
  - MCP tools: `budget_summary`, `budget_entries`.

**Explicitly out of scope for v1:**

  - Actuals tracking vs budget (recording real transactions). v2.
  - Multi-currency conversion. v2.
  - Bank-statement import (CSV / PSD2 / Nordigen). v2.
  - Charts / graphs. v2.

**Money handling rule (non-negotiable):**

  - Amounts are stored in **integer minor units** (`amount_cents`).
    Never use floats for currency. Display layer formats to two
    decimals. This avoids the float-rounding bug that haunts every
    home-grown budget app.

**Data shape:**

```
budget_categories
  id, slug, name, kind ('expense' | 'income'), sort_order, created_at

budget_entries
  id, category_id, name, amount_cents, currency (default 'DKK'),
  recurrence ('monthly' | 'yearly' | 'one-off'),
  due_day (1-31, monthly), due_date (ISO, one-off / yearly),
  active (0 | 1), notes, created_at, updated_at
```

**Acceptance criteria (v1 skeleton):**

  - [ ] Schema + seed run idempotently on `init_db()`.
  - [ ] `app/widgets/budget/` exists with manifest, fetch, card, mcp,
        routes, db helper, CLAUDE.md.
  - [ ] `/budget` page lists every category section with its entries,
        monthly total, annual total, grand totals (income / expense
        / net).
  - [ ] HTMX form: create + edit + delete entries from the page,
        without a full reload.
  - [ ] Dashboard card shows monthly net + a "/budget tab ->" link.
  - [ ] Audit: every create/edit/delete recorded in `widget_edits`.
  - [ ] All amounts stored as `amount_cents INTEGER`. No float
        comparison anywhere.
  - [ ] Budget tab added to top navigation.

---

## Working agreement

  - Each feature gets reviewed in chat. You say "accept F1" (or "tweak
    Q3 to X, then accept") and we move to implementation.
  - During implementation, this file gets updated with status checkmarks.
  - When a feature ships, its section moves up to the "Shipped" table
    with a new vX.Y tag.
  - If you have new ideas mid-stream, drop them at the bottom of this
    file under a "Parking lot" section - we'll spec them later.

## Parking lot

(empty - add features here as they come up)
