Football Predictor
==================

Match-outcome (1X2) predictor for the English Premier League.
See :doc:`../../widgets/football` for implementation detail.

.. req:: Display calibrated 1X2 probabilities per match
   :id: REQ-010
   :status: implemented
   :tags: functional, football, t1

   The dashboard card must show calibrated home / draw / away
   probabilities summing to 100% for each match in the prediction
   batch.

.. req:: Show prediction confidence as a bucket
   :id: REQ-011
   :status: implemented
   :tags: functional, football, t1

   Each match must carry a high / medium / low confidence badge,
   computed from entropy x epistemic uncertainty x calibration
   health.

.. req:: Detail drawer explains "why this prediction"
   :id: REQ-012
   :status: implemented
   :tags: functional, football, explainability

   Clicking a match must open a panel listing the top six features
   that pushed the model toward the predicted outcome, with raw value,
   signed logit contribution, and a bar visualization.

.. req:: Bootstrap ensemble exposes epistemic uncertainty
   :id: REQ-013
   :status: implemented
   :tags: functional, football, uncertainty

   The K=20 bootstrap ensemble's per-class standard deviation must be
   surfaced in the detail drawer next to the calibrated probability.

.. req:: Training pipeline is reproducible from one command
   :id: REQ-014
   :status: implemented
   :tags: functional, football, pipeline

   ``python -m app.widgets.football.ml.train`` (run inside the
   container) must complete end-to-end: download CSVs, engineer
   features, train, calibrate, bootstrap, evaluate, persist artifacts,
   regenerate walkthrough figures.
