Reliability
===========

.. req:: A failing widget must not crash the dashboard
   :id: REQ-110
   :status: implemented
   :tags: non-functional, reliability

   Exceptions raised inside a widget's ``fetch()`` must be caught by
   ``Widget.refresh()`` and logged, leaving the other widgets and the
   FastAPI process intact.

.. req:: Model + predictions persist across container restart
   :id: REQ-111
   :status: implemented
   :tags: non-functional, reliability, football

   ``latest.joblib`` and ``latest_predictions.json`` must live on the
   ``jytte-data`` Docker volume (or k3s PVC) so a rebuild of the image
   does not erase trained state.
