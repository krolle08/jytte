Football Predictor
==================

**What it is**: Dashboard card showing match-outcome predictions
(home win / draw / away win) for a held-out batch of EPL matches,
plus an in-app "why this prediction" panel listing the top
contributing features.

**Why it's here**: The widget is *half* the deliverable. The other
half is :doc:`../ml-walkthrough`, a from-first-principles ML tour
that uses this widget as the running worked example.

**Source**: ``app/widgets/football/``

Overview
--------

The widget reads ``/data/football/models/latest_predictions.json``,
produced by the offline training pipeline. The JSON contains, for
each match: calibrated 1X2 probabilities, ensemble mean + std,
entropy, an aggregate confidence bucket (high / medium / low),
and the top six features that pushed the model toward its
predicted outcome.

Key Responsibilities
--------------------

- Surface the next N predictions on the dashboard card with
  probability bars and confidence badge.
- Provide a detail drawer showing calibrated vs raw ensemble
  probabilities, epistemic standard deviation, and the "why"
  panel of top contributing features.
- Expose two MCP tools (``football_predictions``,
  ``football_metrics``) so Claude Code can query state.

Training Pipeline
-----------------

Run from inside the container:

.. code-block:: bash

   docker compose exec jytte python -m app.widgets.football.ml.train

The pipeline:

1. Downloads ~6 seasons of EPL CSVs from football-data.co.uk
   (cached after first run).
2. Engineers features (Elo, rolling 5-match form, head-to-head).
3. Chronological 80 / 10 / 10 split (train / val / test).
4. Fits a multinomial logistic regression, then a Platt-calibrated
   wrapper, then a K=20 bootstrap ensemble for epistemic
   uncertainty.
5. Writes nine PNG figures to ``docs/ml-figures/`` and a
   ``latest_predictions.json`` (model + features + per-match
   contributions) into the data volume.

Integration Points
------------------

- **External**: football-data.co.uk (CSV download, no auth).
- **Internal**: writes to ``/data/football/models/`` and
  ``docs/ml-figures/``; widget reads the JSON on next refresh.

Architecture
------------

.. uml::
   :caption: Football widget data flow

   !include <C4/C4_Component>

   Container_Boundary(jytte, "Jytte container") {
       Component(train, "ml/train.py", "Python script", "Offline training entrypoint")
       Component(features, "ml/features.py", "Python", "Elo + rolling form + h2h")
       Component(elo, "ml/elo.py", "Python", "Rolling Elo ratings")
       Component(ensemble, "ml/bootstrap.py", "Python", "K=20 bootstrap members")
       Component(eval, "ml/evaluation.py", "Python", "Metrics + 9 walkthrough PNGs")
       Component(fetch, "fetch.py", "Python", "Reads predictions JSON")
       Component(mcp, "mcp.py", "Python", "Registers football_predictions tool")
       ComponentDb(model, "latest.joblib", "joblib", "Calibrated model + ensemble")
       ComponentDb(preds, "latest_predictions.json", "JSON", "228 held-out predictions + top_features")
   }

   System_Ext(fdataco, "football-data.co.uk", "EPL CSVs")

   Rel(train, fdataco, "Downloads CSVs", "HTTPS")
   Rel(train, features, "Calls build_features()", "import")
   Rel(features, elo, "compute_pre_match_elo()", "import")
   Rel(train, ensemble, "Fits K=20 members", "import")
   Rel(train, eval, "compute_metrics() + plots", "import")
   Rel(train, model, "joblib.dump", "FS")
   Rel(train, preds, "json.dump", "FS")
   Rel(fetch, preds, "json.loads on refresh", "FS")
   Rel(mcp, fetch, "Wraps fetch() in MCP tool", "import")

   LAYOUT_WITH_LEGEND()

Design Specifications
---------------------

.. dropdown:: How requirements are fulfilled
   :icon: tasklist

   .. spec:: Calibrated multinomial logistic regression
      :id: SPEC-010
      :fulfills: REQ-010
      :status: implemented
      :tags: football, t1

      Multinomial logistic regression trained on rolling 5-match form
      + Elo features, calibrated via Platt scaling on a held-out
      validation fold. Persisted to ``latest_predictions.json`` per
      match.

   .. spec:: Confidence bucket from three uncertainty signals
      :id: SPEC-011
      :fulfills: REQ-011
      :status: implemented
      :tags: football, uncertainty

      Bucket = product of (1 - normalized entropy), (1 - normalized
      epistemic std), and calibration health factor. High >= 0.6,
      medium >= 0.3, otherwise low.

   .. spec:: Top features extracted via linear-model coefficients
      :id: SPEC-012
      :fulfills: REQ-012
      :status: implemented
      :tags: football, explainability

      At training time, for each held-out match the pipeline computes
      ``coef[winner_class, :] * x_scaled`` and surfaces the top six by
      absolute contribution into ``top_features``.

   .. spec:: K=20 bootstrap ensemble
      :id: SPEC-013
      :fulfills: REQ-013
      :status: implemented
      :tags: football, uncertainty

      Twenty bootstrap resamples of the training set, each fitted with
      the same pipeline. Inference returns per-class mean + std-dev
      across members.

   .. spec:: Single training entrypoint
      :id: SPEC-014
      :fulfills: REQ-014
      :status: implemented
      :tags: football, pipeline

      ``python -m app.widgets.football.ml.train`` runs the full
      pipeline and writes artifacts into the data volume.

Related Documentation
---------------------

- :doc:`../ml-walkthrough` - full ML walkthrough
- :doc:`../architecture` - system context
