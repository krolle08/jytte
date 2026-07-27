Performance
===========

.. req:: Football training pipeline completes in under five minutes
   :id: REQ-100
   :status: implemented
   :tags: non-functional, performance, football

   ``python -m app.widgets.football.ml.train`` on a development laptop
   (no GPU) should complete in under five minutes from cold start
   (download + train + plot).

.. req:: Dashboard card refresh stays under two seconds
   :id: REQ-101
   :status: open
   :tags: non-functional, performance, dashboard

   A HTMX partial fetch for any widget card should return a complete
   HTML fragment in under two seconds from a warm cache.
