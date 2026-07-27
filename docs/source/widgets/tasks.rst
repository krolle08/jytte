Tasks
=====

**What it is**: Surfaces open tasks from a local Obsidian vault.

**Why it's here**: Keeps the Tasks vault present on the dashboard
without round-tripping through Claude or any external API.

**Source**: ``app/widgets/tasks/``

Overview
--------

Uses a filesystem watcher (``manifest.yaml`` declares ``watcher: true``)
on the bind-mounted Obsidian Tasks folder. No Claude analyser - the
tasks are surfaced as-is and the widget supports edit-back via a
per-row drawer.

Key Responsibilities
--------------------

- Parse Obsidian task notes (YAML frontmatter + body).
- Group by status, priority, due date.
- Render the dashboard card and the detail drawer.
- Write status changes back to the source ``.md`` files.

Integration Points
------------------

- **Filesystem**: bind-mounted ``C:\\Obsidian\\Nichlas\\Tasks`` (or
  ``/data/obsidian-tasks`` inside the container).
- **No external services**.

Related Documentation
---------------------

- :doc:`../architecture` - widget component contract
