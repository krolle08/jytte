# Tasks - FEAT-002

- [ ] T1 `ADOConfig.enabled` field + `discover_configs()` reads `AZDO_ENABLED[_SUFFIX]`
- [ ] T2 `fetch.py` - disabled instances become awaiting_activation stubs with no client/no request
- [ ] T3 `_normalize_workitem` - add sprint, due_date, urgency
- [ ] T4 `ado.py:get_workitem_comments(item_id, slug)` using sanitized `_get`
- [ ] T5 `routes.py` - detail route loads comments for kind=item only
- [ ] T6 `detail.html` - render sprint/due/urgency + comments block (drawer = the "expand")
- [ ] T7 `ado_writer.py` - refuse writes to a disabled/awaiting instance
- [ ] T8 `mcp.py` - iterate instances[], tag by slug, skip awaiting_activation
- [ ] T9 `card.html` + `ado_tab.html` - show awaiting-activation instances distinctly
- [ ] T10 `.env.example` - AZDO_*_DAGROFA + AZDO_ENABLED_DAGROFA=false
- [ ] T11 `tests/test_ado_normalize.py`
- [ ] T12 Boot smoke + docker build
