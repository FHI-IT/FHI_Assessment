# Handover Addendum 68 — Dashboard: composite QuoteNo+QuoteVer row key (DuplicateElementKey recurrence)

Date: 2026-08-06 · Repo **`FHI_Assessment`** (Streamlit reviewer dashboard). Branch **`main`**, commit **`a393fc3`**, pushed to `origin/main` (`976aa96..a393fc3`).

## Problem — the A65 fix wasn't enough
A65 keyed queue rows on `QuoteVer` (with a `QuoteNo` fallback) to survive **QuoteNo** collisions. But the live data now also contains a **QuoteVer** collision: `268574-2` appears under **both** QuoteNo 268574 and QuoteNo 268575. So QuoteVer alone is not unique either, and `StreamlitDuplicateElementKey` came back.

The only reliable unique identifier is the **combination** `QuoteNo|QuoteVer` — verified unique across all colliding rows in the live data.

## Fix — `_row_key()` now uses the composite
```python
def _row_key(a):
    qno  = str(a.get("QuoteNo", "") or "")
    qver = str(a.get("QuoteVer", "") or "")
    raw  = f"{qno}|{qver}" if (qno or qver) else f"idx{id(a)}"
    return "row_" + "".join(c if c.isalnum() else "_" for c in raw)
```
- Combines both fields, so neither field colliding alone can produce a duplicate key.
- **Sanitised** to a safe Streamlit key string (non-alphanumerics → `_`, `row_` prefix).
- **Last-resort guard:** if both fields are empty on two rows, `idx{id(a)}` keeps keys distinct via object identity.

**Single choke point:** `selected_quote_key`/`sel_key` and every widget `key=` in `main()` already route through `_row_key()` (since A65), so changing the helper's internals fixes all call sites at once. Verified — the only `_row_key(` uses are the `opts` dict, the queue-loop `row_key`, and the detail-pane `sel` match; `grep` shows **no** widget key built directly from `{qno}`/`{qver}` that bypasses it.

## Detail-pane lookup — unchanged and still correct
The selected row is resolved by `_row_key(a) == sel_key`, then `detail` is looked up by that row's `sel["QuoteNo"]` (member/category data is QuoteNo-keyed). That stays. It means the two rows sharing **QuoteNo 268575** (SVS Partnership + one Aquatic Imports row) still share `detail` member data — the known collision from A66. The **A66 `_qno_collision` guard is unaffected** (it counts QuoteNo occurrences), so the red banner / `⚠ COLLISION` pill / disabled decision buttons still fire for those rows.

## Verification (before commit)
- `py -m py_compile streamlit_app.py` → **OK, compiles**.
- Ran the required assertion against the **actual** `_row_key` source (extracted via `ast`, so no app side effects) on the exact three breaking rows:
  ```
  (268574, 268574-2) -> row_268574_268574_2
  (268575, 268574-2) -> row_268575_268574_2
  (268575, 268575-1) -> row_268575_268575_1
  ```
  `len(set(keys)) == 3` ✅ — three distinct keys. Empty-field guard also produced distinct keys.

## Deploy
Auto-redeploys ~60s after push. **Cached-data path → reboot the app from share.streamlit.io** (or wait the ~5-min TTL). Confirm the full queue (~50 rows) renders **without the DuplicateElementKey crash**, and that the A66 collision banner still appears for the QuoteNo 268575 pair.

## Relationship to prior addenda
- **A65** (`ea18f63`) — introduced `_row_key` (QuoteVer + QuoteNo fallback). Superseded internals by this addendum.
- **A66** (`da8698e`) — `_qno_collision` guard (banner/pill/disabled buttons). Still in force, unaffected.

## Files
`streamlit_app.py` (repo `FHI_Assessment`, commit `a393fc3`; +9 / −8).
