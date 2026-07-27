Widget Platform
===============

.. req:: Widgets are auto-discovered from app/widgets/
   :id: REQ-001
   :status: implemented
   :tags: functional, platform

   On startup the registry must scan ``app/widgets/`` and load every
   subfolder that contains a ``manifest.yaml``. No central registry of
   widget names should be required.

.. req:: Each widget has its own cadence
   :id: REQ-002
   :status: implemented
   :tags: functional, platform

   The scheduler must respect each widget's ``refresh_minutes`` from
   ``manifest.yaml``. Widgets must be able to opt out of scheduled
   refresh (file-watcher widgets) by omitting the value.

.. req:: Widgets can register MCP tools
   :id: REQ-003
   :status: implemented
   :tags: functional, mcp

   A widget with ``expose_mcp: true`` and an ``mcp.py`` module exposing
   ``register(mcp, widget)`` must have its tools wired into the MCP
   server at startup.
