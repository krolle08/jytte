# Process flow - FEAT-003

## Render flow (unchanged pipeline, new layout)
```
vault watcher -> tasks.fetch() -> upsert_state -> SSE widget:tasks
   -> /widgets/tasks?partial=1 -> tasks/card.html (now full list, scrollable)
   -> placed at grid-row 1 full-width by .card-tasks CSS
```

## Grid
```
row 1: tasks       (1 / -1)   <- main screen hero
row 2: emails      (1 / -1)
row 3: azuredevops (1 / -1)
row 4: geomap      (1 / -1)
row 5: budget (1)  news (2)
row 6: football (1)
row 7: chat        (1 / -1)
```
