Maintainability
===============

.. req:: Adding a new widget requires no edits outside its folder
   :id: REQ-120
   :status: implemented
   :tags: non-functional, maintainability, platform

   A new widget must be added by dropping a folder under
   ``app/widgets/<name>/`` containing ``manifest.yaml``, ``fetch.py``,
   optional ``analyze.py``, ``card.html``, optional ``mcp.py``,
   optional ``routes.py``. No central registration code should require
   editing.

.. req:: Architecture and feature roadmap documented in-repo
   :id: REQ-121
   :status: implemented
   :tags: non-functional, maintainability, documentation

   The C4 architecture diagrams (this Sphinx site) and the feature
   roadmap (``features.md`` at the repo root) must be kept up to date
   as a precondition for shipping a new feature.
