# Process flow - FEAT-NNN

## User flow
1. <step>
2. <step>

## Data flow
```
<source> --(fetch/push)--> widget_state (db) --(SSE widget:<name>)--> card.html --(HTMX)--> browser
```

## Edit-back flow (if the feature writes)
```
form -> POST /widgets/<name>/<action> -> source-of-truth write -> db.record_edit -> SSE -> re-rendered partial
```
