"""
Freedom Health Insurance — New Business Review
Streamlit app (Task 2 + Task 3)
"""

import math
import json
import random
import string
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from supabase import create_client
from supabase.client import ClientOptions

from assessment_engine import assess_quote, parse_money

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FHI — New Business Review",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

FHI_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
  html, body, [class*="css"] { font-family: 'Nunito', sans-serif !important; }
  :root {
    --fhi-magenta: #990858;
    --fhi-teal:    #006f8e;
    --fhi-navy:    #282f4b;
    --fhi-bg:      #f7f7f9;
    --fhi-card:    #ffffff;
  }
  .fhi-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 18px 28px; background: white;
    border-bottom: 3px solid var(--fhi-magenta);
    margin: -1rem -1rem 1.5rem -1rem;
  }
  .fhi-header-title h1 { font-size: 1.7rem; font-weight: 800; color: var(--fhi-navy); margin: 0; }
  .fhi-header-title p  { color: #666; font-size: 0.85rem; margin: 0; }
  .fhi-header-meta     { text-align: right; font-size: 0.8rem; color: #888; }
  div[data-testid="metric-container"] {
    background: white; border-radius: 10px; padding: 16px 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07);
    border-top: 3px solid #e0e0e0;
  }
  .badge {
    display: inline-block; padding: 3px 10px; border-radius: 20px;
    font-size: 0.75rem; font-weight: 700; letter-spacing: 0.04em;
  }
  .badge-RELEASE { background: #d4edda; color: #155724; }
  .badge-REFER   { background: #fff3cd; color: #856404; }
  .badge-DECLINE { background: #f8d7da; color: #721c24; }
  .flag-row { padding: 6px 10px; border-radius: 6px; margin: 4px 0; font-size: 0.85rem; }
  .flag-DECLINE { background: #fdecea; border-left: 4px solid #e74c3c; }
  .flag-REFER   { background: #fff8e1; border-left: 4px solid #f39c12; }
  .flag-INFO    { background: #e8f4f8; border-left: 4px solid #3498db; }
  .flag-pass    { background: #eaf6ef; border-left: 4px solid #2ecc71; }
  .flag-refer   { background: #fff8e1; border-left: 4px solid #f39c12; }
  .flag-fail    { background: #fdecea; border-left: 4px solid #e74c3c; }
  .flag-info    { background: #e8f4f8; border-left: 4px solid #3498db; }
  .sec-ref      { color: var(--fhi-teal); font-weight: 700; font-size: 0.8rem; margin-left: 6px; }
  .ref-id-box {
    background: #f0f4ff; border: 1.5px dashed #4a6fa5;
    border-radius: 8px; padding: 10px 16px;
    font-family: 'Courier New', monospace; font-size: 1rem;
    font-weight: 700; color: var(--fhi-navy); letter-spacing: 0.05em;
    display: flex; align-items: center; justify-content: space-between;
  }
  .ref-id-label { font-size: 0.72rem; font-family: 'Nunito', sans-serif;
                  color: #666; margin-bottom: 2px; }
  .section-label {
    font-size: 0.7rem; font-weight: 800; letter-spacing: 0.1em;
    text-transform: uppercase; color: #aaa; margin: 18px 0 6px 0;
  }
  .money { font-weight: 700; color: var(--fhi-navy); }
  .money-good { color: #2a9d8f; }
  .money-warn { color: #e9c46a; }
  .quote-meta { font-size: 0.8rem; color: #888; }
  div[data-testid="stButton"] > button {
    border-radius: 8px; font-weight: 700; font-family: 'Nunito', sans-serif;
  }
  #MainMenu, footer { visibility: hidden; }
  header[data-testid="stHeader"] { background: transparent; }
</style>
"""

# ── Authentication ─────────────────────────────────────────────────────────────
def check_password() -> bool:
    if st.session_state.get("authenticated"):
        return True
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown("## 🏥 Freedom Health — New Business Review")
        st.markdown("Please enter the team password to continue.")
        pw = st.text_input("Password", type="password", key="pw_input")
        if st.button("Sign in", use_container_width=True):
            try:
                correct = st.secrets["app_password"]
            except Exception:
                correct = "devmode"
            if pw == correct:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password — please try again.")
    return False

if not check_password():
    st.stop()

# ── Inject CSS only after auth passes ─────────────────────────────────────────
st.markdown(FHI_CSS, unsafe_allow_html=True)

# ── Supabase client ────────────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        st.error("Supabase credentials not found in st.secrets.")
        st.stop()
    return create_client(
        url.rstrip("/"),
        key,
        options=ClientOptions(schema="12_clapa", postgrest_client_timeout=30),
    )

# ── Table names ────────────────────────────────────────────────────────────────
T_QUOTES  = "CLAPA_tbl_PA_Quotes"
T_MEMBERS = "CLAPA_tbl_Quotes_Members"
T_CATS    = "CLAPA_tbl_PA_Quote_Cats"
T_STATUS  = "CLAPA_tbl_PA_Quote_Status"
T_LOG     = "assessment_log"
ENGINE_VERSION = "v6.1"


def clean_nans(obj):
    if isinstance(obj, dict):
        return {k: clean_nans(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nans(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


@st.cache_data(ttl=300, show_spinner=False)
def fetch_data():
    client = get_client()
    status_rows = client.from_(T_STATUS).select("*").execute().data or []
    status_map = {r["QuoteID"]: r["QuoteStatus"] for r in status_rows}
    awaiting_id = next(
        (k for k, v in status_map.items() if v == "Input - Awaiting assessment"), None
    )
    if awaiting_id is None:
        return [], {}
    q_data = (
        client.from_(T_QUOTES)
              .select("*")
              .eq("QuoteStatus", awaiting_id)
              .is_("Policy Number", "null")
              .not_.is_("Broker", "null")
              .order("DateEntered", desc=True)
              .execute()
    ).data or []
    quotes_df = pd.DataFrame(q_data)
    if quotes_df.empty:
        return [], {}
    quotes_df = quotes_df[
        ~quotes_df["QuoteName"].fillna("").str.contains(
            "QUOTES|Prioritary|---", case=False, regex=True
        )
    ].copy()
    target_ids = quotes_df["QuoteNo"].astype(int).tolist()
    members_df = pd.DataFrame(
        (client.from_(T_MEMBERS).select("*").in_("QuoteNo", target_ids).execute().data or [])
    )
    cats_df = pd.DataFrame(
        (client.from_(T_CATS).select("*").in_("QuoteNo", target_ids).execute().data or [])
    )
    quotes_df["AnnualPremium_n"] = quotes_df["AnnualPremium"].apply(parse_money)
    quotes_df["DateEntered_dt"]  = pd.to_datetime(quotes_df["DateEntered"], errors="coerce")
    quotes_df["StatusName"]      = quotes_df["QuoteStatus"].map(status_map)
    assessments = []
    detail = {}
    for _, q in quotes_df.iterrows():
        qid  = int(q["QuoteNo"])
        msub = members_df[members_df["QuoteNo"] == qid] if not members_df.empty else pd.DataFrame()
        csub = cats_df[cats_df["QuoteNo"] == qid]       if not cats_df.empty  else pd.DataFrame()
        a = assess_quote(q, msub, csub)
        a = clean_nans(a)
        assessments.append(a)
        detail[str(qid)] = {
            "members": [
                {
                    "name":   str(m.get("Insured Name") or m.get("Surname") or f"Employee {m['MemberNo']}")[:40],
                    "age":    int(m["Insured Age"]) if pd.notna(m.get("Insured Age")) else None,
                    "smoker": str(m.get("Smoker Y/N", "")),
                    "uw":     str(m.get("underwriting Type", "")),
                    "cover":  str(m.get("Type of cover", "")),
                    "annual": float(m["Annual Premium"]) if pd.notna(m.get("Annual Premium")) else None,
                }
                for _, m in msub.iterrows()
            ],
            "member_count_total": len(msub),
        }
    assessments.sort(key=lambda x: x.get("DateEntered", ""), reverse=True)
    return assessments, detail


def generate_reference_id(quote_no: int) -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"FHI-A-{datetime.now():%Y-%m-%d}-{quote_no}-{suffix}"


def get_or_create_log_entry(client, assessment: dict) -> str:
    quote_no  = assessment["QuoteNo"]
    quote_ver = assessment.get("QuoteVer", "")
    try:
        existing = (
            client.from_(T_LOG)
                  .select("reference_id")
                  .eq("quote_no", quote_no)
                  .eq("quote_ver", quote_ver)
                  .is_("reviewer_decision", "null")
                  .order("assessed_at", desc=True)
                  .limit(1)
                  .execute()
        )
        if existing.data:
            return existing.data[0]["reference_id"]
    except Exception:
        pass
    ref_id = generate_reference_id(quote_no)
    try:
        client.from_(T_LOG).insert({
            "reference_id":              ref_id,
            "quote_no":                  quote_no,
            "quote_ver":                 quote_ver,
            "company_name":              assessment.get("QuoteName"),
            "broker":                    assessment.get("Broker"),
            "system_recommendation":     assessment["recommendation"],
            "system_reason":             assessment.get("recommendation_reason"),
            "rules_fired":               json.dumps(assessment.get("flags", [])),
            "rules_checked":             json.dumps(assessment.get("checks", [])),
            "suggested_release_annual":  assessment.get("SuggestedRelease_Annual"),
            "suggested_release_monthly": assessment.get("SuggestedRelease_Monthly"),
            "engine_version":            ENGINE_VERSION,
            "quote_data_snapshot":       json.dumps(assessment),
        }).execute()
    except Exception as e:
        st.session_state.setdefault("log_errors", []).append(str(e))
    return ref_id


def record_reviewer_decision(client, ref_id, decision, system_rec,
                              override_reason="", final_annual=None, final_monthly=None):
    is_override = decision != system_rec
    client.from_(T_LOG).update({
        "reviewer":            st.session_state.get("reviewer_name", "Unknown"),
        "reviewer_decision":   decision,
        "reviewer_decided_at": datetime.utcnow().isoformat(),
        "reviewer_override":   is_override,
        "reviewer_reason":     override_reason if is_override else None,
        "final_premium_annual":  final_annual,
        "final_premium_monthly": final_monthly,
    }).eq("reference_id", ref_id).execute()


def fmt_money(v):
    return "—" if v is None else f"£{v:,.2f}"


def render_flag(f):
    sev  = f.get("severity", "INFO")
    ref  = f.get("ref", "")
    rule = f.get("rule", "")
    det  = f.get("detail", "")
    ref_span = f'<span class="sec-ref">{ref}</span>' if ref else ""
    st.markdown(
        f'<div class="flag-row flag-{sev}"><strong>{rule}</strong>{ref_span}'
        f'<br><span style="color:#555">{det}</span></div>',
        unsafe_allow_html=True,
    )


def render_check(c):
    status = c.get("status", "pass")
    icon   = {"pass": "✅", "fail": "❌", "refer": "⚠️", "info": "ℹ️"}.get(status, "•")
    ref    = c.get("ref", "")
    ref_span = f'<span class="sec-ref">{ref}</span>' if ref else ""
    st.markdown(
        f'<div class="flag-row flag-{status}">{icon} <strong>{c.get("rule","")}</strong>'
        f'{ref_span} — <span style="color:#555">{c.get("detail","")}</span></div>',
        unsafe_allow_html=True,
    )


# ── Main UI ────────────────────────────────────────────────────────────────────
def main():
    client = get_client()
    if "reviewer_name" not in st.session_state:
        st.session_state["reviewer_name"] = "Unknown"

    # Header
    logo_path = Path(__file__).parent / "logo.png"
    cols = st.columns([1, 6, 2])
    with cols[0]:
        if logo_path.exists():
            st.image(str(logo_path), width=110)
    with cols[1]:
        st.markdown(
            "<h1 style='font-size:1.6rem;font-weight:800;color:#282f4b;margin:0'>New Business Review</h1>"
            "<p style='color:#888;font-size:0.82rem;margin:0'>Automated assessment · Quote Parameters v2.1 (effective 1 April 2026)</p>",
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.markdown(
            f"<div style='text-align:right;font-size:0.8rem;color:#888'>"
            f"<strong>{datetime.now().strftime('%d %b %Y · %H:%M')}</strong><br>"
            f"Reviewer: {st.session_state['reviewer_name']}</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.info(
        "**Quote Parameters v2.1 (1 April 2026):** All checkable rules applied. "
        "Average age is *premium-weighted* (per §3); §n references shown beside rules; "
        "manual checks listed at the bottom of each quote."
    )

    with st.spinner("Loading live data from Supabase…"):
        assessments, detail = fetch_data()

    if not assessments:
        st.warning("No new-business quotes currently awaiting assessment.")
        return

    n_release = sum(1 for a in assessments if a["recommendation"] == "RELEASE")
    n_refer   = sum(1 for a in assessments if a["recommendation"] == "REFER")
    n_decline = sum(1 for a in assessments if a["recommendation"] == "DECLINE")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("In Queue",       len(assessments))
    k2.metric("Auto-Release",   n_release)
    k3.metric("Refer / Review", n_refer)
    k4.metric("Decline",        n_decline)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 2], gap="large")

    with left:
        st.markdown("### Quote Queue")
        filter_sel = st.radio("Filter", ["ALL", "DECLINE", "REFER", "RELEASE"],
                              horizontal=True, label_visibility="collapsed", key="queue_filter")
        filt = filter_sel if filter_sel != "ALL" else None
        visible = [a for a in assessments if filt is None or a["recommendation"] == filt]
        if not visible:
            st.caption(f"No quotes matching '{filter_sel}'")

        opts = {a["QuoteNo"]: f"{a.get('QuoteName','—')} #{a['QuoteNo']} [{a['recommendation']}]"
                for a in visible}
        if "selected_quote_no" not in st.session_state or \
                st.session_state["selected_quote_no"] not in opts:
            st.session_state["selected_quote_no"] = list(opts.keys())[0] if opts else None

        for a in visible:
            qno = a["QuoteNo"]
            rec = a["recommendation"]
            badge_color = {"RELEASE": "#2a9d8f", "REFER": "#e9c46a", "DECLINE": "#e76f51"}.get(rec, "#aaa")
            bg = "#f0f4ff" if st.session_state.get("selected_quote_no") == qno else "white"
            avg_age = a.get("AvgMemberAge")
            st.markdown(
                f'<div style="background:{bg};border-radius:8px;padding:10px 14px;'
                f'margin-bottom:6px;border-left:4px solid {badge_color};box-shadow:0 1px 3px rgba(0,0,0,0.07)">'
                f'<div style="display:flex;justify-content:space-between;align-items:center">'
                f'<strong style="font-size:0.9rem;color:#282f4b">{a.get("QuoteName","—")}</strong>'
                f'<span style="background:{badge_color};color:white;padding:2px 8px;border-radius:12px;font-size:0.72rem;font-weight:700">{rec}</span>'
                f'</div><div style="font-size:0.78rem;color:#888;margin-top:3px">'
                f'#{qno} · {a.get("NumMembers","?")} mbrs · {f"avg {avg_age:.1f}" if avg_age else ""} · {a.get("Broker","")[:28]}'
                f'</div><div style="font-size:0.82rem;color:#282f4b;font-weight:700;margin-top:2px">'
                f'{fmt_money(a.get("OurAnnual"))}/yr</div></div>',
                unsafe_allow_html=True,
            )
            if st.button("View →", key=f"sel_{qno}"):
                st.session_state["selected_quote_no"] = qno
                for k in ["pending_decision", "override_reason", "final_annual", "final_monthly"]:
                    st.session_state.pop(k, None)
                st.rerun()

    with right:
        sel_qno = st.session_state.get("selected_quote_no")
        if not sel_qno:
            st.info("Select a quote from the queue to view details.")
            return
        sel = next((a for a in assessments if a["QuoteNo"] == sel_qno), None)
        if not sel:
            st.warning("Quote not found.")
            return

        rec = sel["recommendation"]
        badge_color = {"RELEASE": "#2a9d8f", "REFER": "#e9c46a", "DECLINE": "#e76f51"}.get(rec, "#aaa")
        ref_id = get_or_create_log_entry(client, sel)
        st.session_state[f"ref_id_{sel_qno}"] = ref_id

        date_str = str(sel.get("DateEntered", ""))[:10]
        st.markdown(
            f"<p style='color:#aaa;font-size:0.78rem;margin-bottom:2px'>QUOTE · {date_str}</p>"
            f"<h2 style='margin:0;color:#282f4b'>{sel.get('QuoteName','—')}</h2>"
            f"<p style='color:#888;font-size:0.85rem;margin-top:2px'>"
            f"{sel.get('QuoteVer','—')} via {sel.get('Broker','—')} · System status: {sel.get('StatusName','—')}</p>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='background:#f9f9f9;border-left:5px solid {badge_color};"
            f"border-radius:8px;padding:12px 18px;margin:10px 0'>"
            f"<span style='background:{badge_color};color:white;padding:4px 12px;"
            f"border-radius:16px;font-weight:800;font-size:0.9rem'>{rec}</span>"
            f"&nbsp; <strong>System recommendation:</strong> {sel.get('recommendation_reason','')}</div>",
            unsafe_allow_html=True,
        )

        st.markdown("<div class='ref-id-label'>AUDIT REFERENCE — paste into CRM note field</div>", unsafe_allow_html=True)
        st.code(ref_id, language=None)

        # ── 01 · Quote Facts — compact card grid ────────────────────────────
        st.markdown("#### 01 · Quote Facts")

        def _fact_card(label, value, band_text="", band_class="neutral"):
            band_colors = {"good": "#2a9d8f", "warn": "#e9c46a",
                           "bad":  "#e76f51", "neutral": "#888"}
            color = band_colors.get(band_class, "#888")
            band_html = (
                f'<span style="font-size:0.78rem;color:{color};font-weight:700;'
                f'margin-left:6px">· {band_text}</span>'
            ) if band_text else ""
            return (
                f'<div style="background:white;border-radius:8px;padding:12px 16px;'
                f'box-shadow:0 1px 3px rgba(0,0,0,0.06);height:100%">'
                f'<div style="font-size:0.66rem;color:#aaa;text-transform:uppercase;'
                f'letter-spacing:0.08em;font-weight:700;margin-bottom:4px">{label}</div>'
                f'<div style="font-size:1.05rem;color:#282f4b;font-weight:700">'
                f'{value}{band_html}</div></div>'
            )

        avg_age = sel.get("AvgMemberAge")
        ppl     = sel.get("PremPerLife")
        who     = sel.get("WhoCreated") or "—"
        role    = sel.get("CreatorLicence") or ""

        facts_html = (
            "<div style='display:grid;grid-template-columns:repeat(3,1fr);"
            "gap:12px;margin:10px 0 20px 0'>"
            + _fact_card("Members", sel.get("NumMembers", "—"))
            + _fact_card("Weighted Avg Age",
                         f"{avg_age:.2f}" if avg_age else "—",
                         sel.get("AvgAgeBand", ""),
                         sel.get("AvgAgeBandClass", "neutral"))
            + _fact_card("Max Age", sel.get("MaxMemberAge", "—"))
            + _fact_card("Client pays", sel.get("PaymentFrequency") or "—")
            + _fact_card("Current Insurer", sel.get("CurrentInsurer") or "—")
            + _fact_card("Premium / life (FHI)",
                         fmt_money(ppl) if ppl else "—",
                         sel.get("PremPerLifeBand", "").split(" ")[0] if ppl else "",
                         sel.get("PremPerLifeBandClass", "neutral"))
            + _fact_card("Dominant UW", sel.get("DominantUW") or "—")
            + _fact_card("Quote Created By", who, role)
            + _fact_card("Location", sel.get("Postcode") or sel.get("Town") or "—")
            + "</div>"
        )
        st.markdown(facts_html, unsafe_allow_html=True)

        st.markdown("#### 02 · Premium Comparison — annualised, per-member adjusted")
        pc = st.columns(3)
        pc[0].metric("FHI Quote", fmt_money(sel.get("OurAnnual")))
        pc[1].metric("Current Insurer", fmt_money(sel.get("CurAnnual")))
        pc[2].metric("Their Renewal", fmt_money(sel.get("RenAnnual")))
        pos_vs_ren = sel.get("PositionVsRenewal")
        true_incr  = sel.get("TrueRenewalIncrease")
        if pos_vs_ren is not None or true_incr is not None:
            pc2 = st.columns(3)
            pc2[0].metric("Position vs Renewal", f"{pos_vs_ren:+.1f}%" if pos_vs_ren is not None else "—")
            pc2[1].metric("True renewal incr", f"{true_incr:+.1f}%" if true_incr is not None else "—")
            pc2[2].metric("Discount", f"{sel.get('Discount'):.1f}%" if sel.get("Discount") else "None")

        sug_a = sel.get("SuggestedRelease_Annual")
        sug_m = sel.get("SuggestedRelease_Monthly")
        if sug_a or sug_m:
            st.markdown("<div class='section-label'>Suggested Release Pricing (§12 formula)</div>", unsafe_allow_html=True)
            sp = st.columns(2)
            if sug_a:
                sp[0].metric(f"Annual (binding: {sel.get('SuggestedRelease_Annual_Binding','')})", fmt_money(sug_a))
            if sug_m:
                sp[1].metric(f"Monthly (binding: {sel.get('SuggestedRelease_Monthly_Binding','')})", fmt_money(sug_m))

        flags = sel.get("flags", [])
        st.markdown("#### 03 · Rules Fired")
        if flags:
            for f in flags:
                render_flag(f)
        else:
            st.success("No rules fired — all automated checks passed.")

        checks = sel.get("checks", [])
        if checks:
            with st.expander("04 · Rules Checked (full checklist)", expanded=False):
                for c in checks:
                    render_check(c)

        det = detail.get(str(sel_qno), {})
        members = det.get("members", [])
        if members:
            with st.expander(f"05 · Member Data ({len(members)} members)", expanded=False):
                mdf = pd.DataFrame(members)
                mdf.columns = [c.title() for c in mdf.columns]
                if "Annual" in mdf.columns:
                    mdf["Annual"] = mdf["Annual"].apply(lambda v: f"£{v:,.2f}" if pd.notna(v) else "—")
                st.dataframe(mdf, use_container_width=True, hide_index=True)

        st.markdown("#### 06 · Manual Checks Required")
        st.warning("The following cannot be verified from data — **reviewer must check manually before acting:**")
        for ref, rule, detail_txt in [
            ("§3",  "Over-age dependants",      "Children covered until renewal following 30th birthday"),
            ("§4",  "Worldwide MHD size",        "If worldwide cover, minimum 20 members for MHD"),
            ("§5",  "MHD onboarding compliance", "New MHD members must be added within 30 days"),
            ("§6",  "6-week wait option",         "If current policy has 6-week wait, apply +25% loading"),
            ("§7",  "Occupation / industry",      "Check for Armed Forces, asbestos, mining, oil/gas, high-hazard"),
            ("§8",  "Loss ratio",                 "If claims info provided, loss ratio must be <60% to proceed"),
            ("§9",  "Duplicate quote",            "Check same group quoted by different broker or spelling variation"),
            ("§12", "Voluntary / employee-paid",  "DECLINE if scheme is voluntary joining or employee-paid"),
            ("§12", "Opt-in vs opt-out",           "REFER if opt-in (not opt-out) — note in UW comments"),
            ("§12", "Experience-rated",            "REFER if experience-rated — Senior UW authority required"),
        ]:
            st.markdown(
                f'<div class="flag-row flag-info" style="margin-bottom:4px">'
                f'<span class="sec-ref" style="margin-left:0;margin-right:8px">{ref}</span>'
                f'<strong>{rule}</strong><br>'
                f'<span style="color:#555;font-size:0.82rem">{detail_txt}</span></div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown("#### Reviewer Decision")

        try:
            existing_decision = (
                client.from_(T_LOG)
                      .select("reviewer_decision, reviewer, reviewer_decided_at, reviewer_reason")
                      .eq("reference_id", ref_id)
                      .execute()
            ).data
        except Exception:
            existing_decision = []

        if existing_decision and existing_decision[0].get("reviewer_decision"):
            d = existing_decision[0]
            dec_color = {"RELEASE": "#2a9d8f", "REFER": "#e9c46a", "DECLINE": "#e76f51"}.get(d["reviewer_decision"], "#aaa")
            st.markdown(
                f"<div style='background:#f0fff4;border-radius:8px;padding:14px 18px'>"
                f"<strong>Decision recorded</strong> — "
                f"<span style='background:{dec_color};color:white;padding:2px 10px;"
                f"border-radius:12px;font-weight:700'>{d['reviewer_decision']}</span>"
                f" by <strong>{d.get('reviewer','—')}</strong> at {str(d.get('reviewer_decided_at',''))[:16]}"
                + (f"<br><em>Reason: {d.get('reviewer_reason','')}</em>" if d.get("reviewer_reason") else "")
                + "</div>",
                unsafe_allow_html=True,
            )
            if st.button("Reopen decision", key=f"reopen_{sel_qno}"):
                try:
                    client.from_(T_LOG).update({
                        "reviewer_decision": None, "reviewer": None,
                        "reviewer_decided_at": None, "reviewer_override": False, "reviewer_reason": None,
                    }).eq("reference_id", ref_id).execute()
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not reopen: {e}")
        else:
            r_name = st.text_input("Your name (for audit log)",
                                   value=st.session_state.get("reviewer_name", ""),
                                   key=f"rname_{sel_qno}")
            if r_name:
                st.session_state["reviewer_name"] = r_name

            with st.expander("Override release premium (optional)", expanded=False):
                oc = st.columns(2)
                final_a = oc[0].number_input("Final annual premium (£)", min_value=0.0, step=100.0,
                                              value=float(sug_a) if sug_a else 0.0, key=f"fa_{sel_qno}")
                final_m = oc[1].number_input("Final monthly premium (£)", min_value=0.0, step=10.0,
                                              value=float(sug_m) if sug_m else 0.0, key=f"fm_{sel_qno}")
                use_override_prem = st.checkbox("Use these values in the audit record", key=f"use_prem_{sel_qno}")

            override_reason = ""
            pending = st.session_state.get(f"pending_decision_{sel_qno}")
            if pending and pending != rec:
                override_reason = st.text_area(
                    f"⚠️ You are overriding the system recommendation ({rec}). Please provide a reason (required):",
                    key=f"reason_{sel_qno}",
                )

            dcols = st.columns(3)
            if dcols[0].button("✅ Confirm & Release", key=f"btn_release_{sel_qno}", use_container_width=True,
                               type="primary" if rec == "RELEASE" else "secondary"):
                st.session_state[f"pending_decision_{sel_qno}"] = "RELEASE"
                if rec == "RELEASE" or override_reason:
                    record_reviewer_decision(client, ref_id, "RELEASE", rec, override_reason,
                                             final_a if use_override_prem else sug_a,
                                             final_m if use_override_prem else sug_m)
                    st.success(f"✅ RELEASE recorded. Reference: **{ref_id}**")
                    st.balloons()
                    st.rerun()
                else:
                    st.warning("This overrides the system recommendation. Please provide a reason above.")

            if dcols[1].button("⚠️ Confirm & Refer", key=f"btn_refer_{sel_qno}", use_container_width=True,
                               type="primary" if rec == "REFER" else "secondary"):
                st.session_state[f"pending_decision_{sel_qno}"] = "REFER"
                if rec == "REFER" or override_reason:
                    record_reviewer_decision(client, ref_id, "REFER", rec, override_reason)
                    st.warning(f"⚠️ REFER recorded. Reference: **{ref_id}**")
                    st.rerun()
                else:
                    st.warning("This overrides the system recommendation. Please provide a reason above.")

            if dcols[2].button("❌ Confirm & Decline", key=f"btn_decline_{sel_qno}", use_container_width=True,
                               type="primary" if rec == "DECLINE" else "secondary"):
                st.session_state[f"pending_decision_{sel_qno}"] = "DECLINE"
                if rec == "DECLINE" or override_reason:
                    record_reviewer_decision(client, ref_id, "DECLINE", rec, override_reason)
                    st.error(f"❌ DECLINE recorded. Reference: **{ref_id}**")
                    st.rerun()
                else:
                    st.warning("This overrides the system recommendation. Please provide a reason above.")

        with st.sidebar:
            st.markdown("### Settings")
            st.markdown(f"**Reviewer:** {st.session_state.get('reviewer_name','Not set')}")
            if st.button("🔄 Force data refresh"):
                st.cache_data.clear()
                st.rerun()
            st.markdown("---")
            st.markdown("**Audit trail**")
            st.caption(f"Engine: {ENGINE_VERSION}")
            st.caption(f"Ref ID: `{ref_id}`")
            if st.session_state.get("log_errors"):
                for e in st.session_state["log_errors"]:
                    st.error(e)
            st.markdown("---")
            if st.button("Sign out"):
                for k in list(st.session_state.keys()):
                    del st.session_state[k]
                st.rerun()


main()
