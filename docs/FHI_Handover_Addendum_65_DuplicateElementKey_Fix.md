# Handover Addendum 65 — Dashboard: fix `StreamlitDuplicateElementKey` crash (key on unique QuoteVer, not QuoteNo)

Date: 2026-08-06 · Repo **`FHI_Assessment`** (Streamlit reviewer dashboard). Branch **`main`**, commit **`ea18f63`**, pushed to `origin/main` (`f225e55..ea18f63`).

## Problem
The app crashed with `StreamlitDuplicateElementKey`. Root cause: two different quotes in the queue can share the same **`QuoteNo`** — a known consequence of the versioning model (a V2 quote gets a fresh QuoteNo that can collide with another quote's QuoteNo). The queue loop built widget keys from `QuoteNo` alone (`key=f"sel_{qno}"`), so two rows produced the same key → duplicate-key exception. The selection identifier (`selected_quote_no = qno`) had the same ambiguity, so selecting one row could surface the wrong quote's detail.

## Fix — selection identity & all widget keys now use a unique per-row token
New module-level helper:
```python
def _row_key(a: dict) -> str:
    qv = a.get("QuoteVer", "")
    return str(qv) if qv else str(a["QuoteNo"])
```
`QuoteVer` is unique per quote version; `QuoteNo` is the fallback only when QuoteVer is absent.

Everywhere in `main()` that keyed on the bare QuoteNo now keys on `_row_key` / `selected_quote_key` / `sel_key`:

| Site | Before | After |
|------|--------|-------|
| `opts` dict + selection init | `a["QuoteNo"]` / `selected_quote_no` | `_row_key(a)` / `selected_quote_key` |
| Queue highlight | `== qno` | `== row_key` |
| Select button | `key=f"sel_{qno}"`, stores `qno` | `key=f"sel_{row_key}"`, stores `row_key` |
| Detail-pane lookup | `a["QuoteNo"] == sel_qno` | `_row_key(a) == sel_key` |
| `ref_id` state key | `ref_id_{sel_qno}` | `ref_id_{sel_key}` |
| Decision widgets | `reopen_ / rname_ / fa_ / fm_ / use_prem_ / reason_ / btn_release_ / btn_refer_ / btn_decline_` + `{sel_qno}` | all `{sel_key}` |
| Pop on decision | `selected_quote_no` | `selected_quote_key` |

## Deliberately left on QuoteNo — the `detail` dict lookup
`detail` (members/categories) is **built and keyed by `QuoteNo`** in `fetch_data()` (`detail[str(int(q["QuoteNo"]))] = …`), because the member/category tables are queried by `QuoteNo` (`.in_("QuoteNo", target_ids)`). So the detail lookup was changed to use the **resolved selected row's** QuoteNo rather than the ambiguous session value:
```python
det = detail.get(str(sel["QuoteNo"]), {})
```
This keeps member retrieval correct without re-keying a DB-sourced dict on QuoteVer (the DB has no QuoteVer key for members). `_row_key` disambiguates *which row is selected*; `sel["QuoteNo"]` then fetches that row's member block.

> Note / possible follow-up: because member & category data are stored per `QuoteNo`, two genuinely different quotes that collide on `QuoteNo` would share the same `detail` entry (and one overwrites the other during construction at `detail[str(qid)] = …`). That is a **pre-existing data-model limitation**, out of scope for this crash fix. If member data ever needs to be disambiguated per version, the member/cat fetch and the `detail` key would need a version-aware identifier too. Flagging only.

## Verification (before commit)
- `grep` — no `sel_qno` / `selected_quote_no` remain; no widget `key=` built from `{qno}`. The one surviving `{qno}` (card line 478, `#{qno} · … mbrs …`) is **display text**, not a key — correct to keep.
- `py -m py_compile streamlit_app.py` → **OK, compiles**.

## Deploy
Auto-redeploys ~60s after push. **Touches the cached data flow → reboot the app from share.streamlit.io** (or wait out the ~5-min TTL) before confirming the crash is gone. To confirm the fix, open a queue that contains two rows sharing a QuoteNo (different QuoteVer) — the page should render without the duplicate-key error, and selecting each should show its own detail.

## Files
`streamlit_app.py` (repo `FHI_Assessment`, commit `ea18f63`; +34 / −22).
