# Handover Addendum 62 — Dashboard: exclude Cover Id = 21 (test/internal) quotes from the assessment queue

Date: 2026-08-06 · Repo **`FHI_Assessment`** (the Streamlit reviewer dashboard — separate from the `fhi-quote-entry` pipeline repo where these addenda live). Branch **`main`**, commit **`dc2d092`**, pushed to `origin/main` (`5077ee6..dc2d092`). **Live after a Streamlit reboot / cache expiry (see Deploy).**

## What changed
The dashboard queue was surfacing test/internal quotes (Cover Id = 21) to reviewers. Added one filter to the Supabase query in `fetch_data()` so those rows never reach the queue.

`streamlit_app.py` — inside `fetch_data()`, one line inserted into the `CLAPA_tbl_PA_Quotes` query chain:

```python
q_data = (
    client.from_(T_QUOTES)
          .select("*")
          .eq("QuoteStatus", awaiting_id)
          .or_("Policy Number.is.null,Policy Number.eq.")
          .not_.is_("Broker", "null")
          .not_.eq("Cover Id", 21)          # <-- added (A62)
          .order("DateEntered", desc=True)
          .execute()
).data or []
```

## Why `.not_.eq` and not a whitelist
`Cover Id` has four values in live data: **20, 21, 22, and NULL**. We want to drop only 21 and keep everything else, **including NULLs**.
- `.not_.eq("Cover Id", 21)` → SQL `NOT ("Cover Id" = 21)`. Because `NULL = 21` is *unknown* (not true), `NOT (unknown)` is also unknown, so NULL rows are **not** excluded — they stay in the queue. 20 and 22 also stay. Only 21 is removed. ✅
- A whitelist like `.in_("Cover Id", [20, 22])` would have **wrongly dropped the NULLs** (NULL is not in the list). ✗

## Column-name note
`Cover Id` contains a space. PostgREST / supabase-py handle spaced column names fine when passed as a plain string to `.not_.eq()`, so `"Cover Id"` as written is correct — **no** quotes-within-quotes, **no** URL-encoding.

## Deploy
Streamlit Cloud auto-redeploys the code in ~60s after the push. **But this filter touches cached data**, so the filtered result won't appear until one of:
- Reboot the app from **share.streamlit.io** (fastest), **or**
- Wait out the ~5-minute `st.cache_data` TTL.

## Verification / follow-up (flag)
- After the reboot, confirm the queue no longer shows any Cover Id = 21 quotes, and that Cover Id 20/22/NULL quotes still appear (i.e. count didn't over-drop).
- No DB/DDL change; read-only query filter only. No pipeline (`fhi-quote-entry`) change.

## Files
`streamlit_app.py` (repo `FHI_Assessment`, commit `dc2d092`).
