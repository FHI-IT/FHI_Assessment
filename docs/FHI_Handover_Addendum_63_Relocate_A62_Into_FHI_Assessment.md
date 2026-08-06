# Handover Addendum 63 — Relocate Addendum 62 into the `FHI_Assessment` repo

Date: 2026-08-06 · Repo **`FHI_Assessment`** (Streamlit reviewer dashboard). Branch **`main`**, commit **`0f61839`**, pushed to `origin/main` (`dc2d092..0f61839`). Docs-only; no code touched.

## Why
A62 documents a change to the **`FHI_Assessment`** dashboard, but it was written into the **`fhi-quote-entry`** pipeline repo's `docs/` by accident — that was simply the active working directory at the time. It belongs with the code it describes, so it was moved.

## Convention established (going forward)
- Addenda that document the **`FHI_Assessment`** dashboard live in **`FHI_Assessment/docs/`**.
- Addenda that document the **`fhi-quote-entry`** pipeline (Azure Functions) stay in **`fhi-quote-entry/docs/`** (that's where A1–A61 live).
- The addendum **number sequence is shared** across both repos (single running counter), so numbers stay globally unique and chronological regardless of which repo the file sits in.

## What was done
1. **Confirmed A62 was untracked** in `fhi-quote-entry` (`git status` showed `??`, `git ls-files --error-unmatch` failed) — never staged or committed there, so nothing to un-commit. Pure filesystem move.
2. **Created** `FHI_Assessment/docs/` (did not previously exist) and **moved** the file into it.
3. **Committed + pushed** in `FHI_Assessment` on `main`:
   - `0f61839` — "Add Addendum 62 — exclude Cover Id 21 from assessment queue".
4. **Verified single location:** `find` for `*Addendum_62*` under `fhi-quote-entry` returns nothing; `git ls-files docs/` in `FHI_Assessment` lists exactly the one tracked file.

## Current state
- `FHI_Assessment/docs/FHI_Handover_Addendum_62_Dashboard_Exclude_CoverId21.md` — tracked, committed (`0f61839`), pushed. ✅
- No copy remains in `fhi-quote-entry`. ✅

## Notes
- Git warned LF→CRLF normalisation on this Windows checkout — cosmetic, content unchanged.
- The push auto-redeploys the same running Streamlit code (docs-only diff) — harmless, no functional effect.

## Files
`docs/FHI_Handover_Addendum_62_Dashboard_Exclude_CoverId21.md` (moved in; repo `FHI_Assessment`, commit `0f61839`).
`docs/FHI_Handover_Addendum_63_Relocate_A62_Into_FHI_Assessment.md` (this note).
