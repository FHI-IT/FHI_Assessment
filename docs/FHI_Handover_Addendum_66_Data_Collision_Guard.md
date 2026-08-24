# Handover Addendum 66 — Dashboard: data-collision guard for quotes sharing a QuoteNo

Date: 2026-08-06 · Repo **`FHI_Assessment`** (Streamlit reviewer dashboard). Branch **`main`**, commit **`da8698e`**, pushed to `origin/main` (`e1939a0..da8698e`).

## Background
Because a versioned quote can be assigned a `QuoteNo` that **collides** with another quote (a CRM data-model issue being raised separately with IT), two different quotes can share one QuoteNo. Member and category data are stored keyed by **QuoteNo only**, so when a collision exists both quotes resolve to the **same** member data — meaning at least one quote shows another company's members and a recommendation computed from them.

The duplicate-key **crash** was already fixed in Addendum 65 (widgets/selection keyed on `QuoteVer`). A65 flagged this shared-member-data limitation as a known follow-up. **This addendum (66) is that follow-up** — it makes the collision *visible* and *blocks decisions* so reviewers don't silently act on unreliable data. It does **not** fix the underlying data model (that's the CRM/IT change).

## Changes to `streamlit_app.py`

**1. Detection — `fetch_data()` (after the assessments list is built, before `return`).**
```python
from collections import Counter          # added at top of file
...
qno_counts = Counter(a.get("QuoteNo") for a in assessments)
for a in assessments:
    a["_qno_collision"] = qno_counts.get(a.get("QuoteNo"), 0) > 1
```
Every assessment gets a boolean `_qno_collision`. In the normal (no-collision) case every value is `False` — no other behaviour changes.

**2. Detail-pane banner — right pane, immediately after the recommendation block, before the audit-reference / "01 · Quote Facts".** Renders **only** when `sel.get("_qno_collision")`. Red bordered box: "⚠️ Data collision — do not action from this screen", naming the shared QuoteNo and the other quote(s) (matched by same QuoteNo, different QuoteVer), telling the reviewer to verify in the CRM before deciding.

**3. Queue-card marker — queue loop.** A small red `⚠ COLLISION` pill (built as `collision_tag`, HTML-entity glyphs `&#9888;`) is prepended to the card meta line (`#{qno} · … mbrs …`) when the row is flagged, so reviewers spot collisions before clicking.

**4. Decision block disabled on collided quotes (the recommended optional step — done).** In the Reviewer Decision section, when `sel.get("_qno_collision")` the three decision buttons are replaced with:
> ⛔ Decision recording is disabled for this quote due to a data collision (shared QuoteNo). Resolve in the CRM first.

So no RELEASE/REFER/DECLINE can be recorded against unreliable data. (The "Reopen decision" path for already-decided quotes is unchanged.)

## Verification (before commit)
- `py -m py_compile streamlit_app.py` → **OK, compiles**.
- Unit sanity check of the detection logic: with rows `[268575/V1, 268575/V2, 111/V1]` → the two 268575 rows flag `True`, the 111 row `False`. A no-collision-only set → **all `False`**. Banner/marker/disable all gate on `sel.get("_qno_collision")`, so they render only for flagged quotes.

## Deploy
Auto-redeploys ~60s after push. **Touches the cached data flow → reboot the app from share.streamlit.io** (or wait out the ~5-min TTL) before confirming. Confirm by selecting either **SVS Partnership Limited** or **Independent Aquatic Imports Limited** (they share **QuoteNo 268575**) — both should show the red collision banner, the queue cards should carry the `⚠ COLLISION` pill, and the decision buttons should be replaced by the disabled message.

## Not addressed here (still open, for IT)
The root cause — colliding QuoteNos and member/category data keyed by QuoteNo only — is a CRM data-model issue being raised separately with IT. Until that is resolved, colliding quotes cannot be actioned from the dashboard and must be handled in the CRM.

## Files
`streamlit_app.py` (repo `FHI_Assessment`, commit `da8698e`; +54 / −16).
