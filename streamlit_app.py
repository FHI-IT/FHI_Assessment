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


def _get_logged_in_display_name():
    """
    Returns a clean display name for the logged-in Streamlit Cloud user.
    Converts e.g. 'hoosh.mires@freedomhealthnet.co.uk' -> 'Hoosh Mires'.
    Returns empty string if no user info is available.
    """
    try:
        u = getattr(st, "user", None) or getattr(st, "experimental_user", None)
        email = getattr(u, "email", None) if u else None
        if not email:
            return ""
        username = email.split("@")[0]
        return " ".join(p.capitalize() for p in username.replace("_", ".").split("."))
    except Exception:
        return ""


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
    # Business rule: QuoteStatus = 1 corresponds to "Input - Awaiting assessment".
    # If the status table is ever reordered, fail loudly rather than filter silently wrong.
    if awaiting_id != 1:
        st.error(
            f"⚠️ Expected QuoteStatus = 1 for 'Input - Awaiting assessment' but got {awaiting_id}. "
            "The status lookup table may have been reordered. Check `CLAPA_tbl_PA_Quote_Status` in Supabase."
        )
        st.stop()
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


def get_decided_quote_ids(client, quote_nos):
    """
    Returns the set of quote_no values that already have a reviewer_decision recorded.
    Used to filter decided quotes out of the visible queue.
    """
    if not quote_nos:
        return set()
    try:
        result = (
            client.from_(T_LOG)
                  .select("quote_no")
                  .in_("quote_no", quote_nos)
                  .not_.is_("reviewer_decision", "null")
                  .execute()
        )
        return {r["quote_no"] for r in (result.data or [])}
    except Exception:
        return set()


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
    if "reviewer_name" not in st.session_state or not st.session_state.get("reviewer_name"):
        st.session_state["reviewer_name"] = _get_logged_in_display_name()

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

    # ── Filter out quotes that already have a recorded reviewer decision ──
    n_decided_recently = 0
    if assessments:
        quote_nos = [a["QuoteNo"] for a in assessments]
        decided_ids = get_decided_quote_ids(client, quote_nos)
        n_decided_recently = len(decided_ids)
        assessments = [a for a in assessments if a["QuoteNo"] not in decided_ids]

    if not assessments:
        if n_decided_recently:
            st.success(
                f"All {n_decided_recently} new-business quote(s) in the queue have been actioned. "
                "Queue is currently empty."
            )
        else:
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

        # ── Queue list — compact selectable cards ──────────────────────────────
        for a in visible:
            qno = a["QuoteNo"]
            rec = a["recommendation"]
            badge_color = {"RELEASE": "#2a9d8f", "REFER": "#e9c46a", "DECLINE": "#e76f51"}.get(rec, "#aaa")
            is_selected = st.session_state.get("selected_quote_no") == qno
            bg = "#f0f4ff" if is_selected else "white"
            avg_age = a.get("AvgMemberAge")
            avg_age_str = f"avg {avg_age:.1f}" if avg_age else ""
            mbrs = a.get("NumMembers", "?")
            broker_short = (a.get("Broker") or "")[:32]
            our_annual = fmt_money(a.get("OurAnnual"))

            card_html = (
                f'<div style="background:{bg};border-radius:8px;padding:9px 12px;'
                f'margin-bottom:5px;border-left:4px solid {badge_color};'
                f'box-shadow:0 1px 2px rgba(0,0,0,0.05);cursor:pointer">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">'
                f'<strong style="font-size:0.88rem;color:#282f4b;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1">'
                f'{a.get("QuoteName","—")}</strong>'
                f'<span style="background:{badge_color};color:white;padding:1px 7px;'
                f'border-radius:10px;font-size:0.66rem;font-weight:700;letter-spacing:0.04em;'
                f'flex-shrink:0">{rec}</span></div>'
                f'<div style="font-size:0.72rem;color:#888;margin-top:2px;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                f'#{qno} · {mbrs} mbrs · {avg_age_str} · {broker_short}</div>'
                f'<div style="font-size:0.8rem;color:#282f4b;font-weight:700;margin-top:1px">'
                f'{our_annual}/yr</div></div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

            if st.button("Select this quote", key=f"sel_{qno}", use_container_width=True):
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

        # ── 02 · Premium Comparison — full table layout (matches original HTML design) ──
        st.markdown(
            "#### 02 · Premium Comparison <span style='font-weight:400;color:#888;font-size:0.85rem'>— annualised, per-member adjusted</span>",
            unsafe_allow_html=True,
        )

        our_a = sel.get("OurAnnual");  our_m = sel.get("OurMonthly")
        cur_a = sel.get("CurAnnual");  cur_m = sel.get("CurMonthly")
        ren_a = sel.get("RenAnnual");  ren_m = sel.get("RenMonthly")
        mbrs_quote = sel.get("NumMembers")
        mbrs_curr  = sel.get("MembersLastYear")
        mbrs_renew = sel.get("MembersThisYear")
        true_incr  = sel.get("TrueRenewalIncrease")
        naive_incr = sel.get("NaiveRenewalIncrease")
        pos_vs_ren = sel.get("PositionVsRenewal")
        magenta    = "#990858"

        def _avg(total, n):
            return f"£{total/n:,.2f}" if (total is not None and n) else "—"

        def _td_money(v, color="#282f4b", weight="700"):
            return f'<td style="padding:10px 14px;text-align:right;color:{color};font-weight:{weight}">{fmt_money(v)}</td>'

        def _td_int(v):
            return f'<td style="padding:10px 14px;text-align:right;color:#282f4b;font-weight:700">{v if v is not None else "—"}</td>'

        def _td_label(label):
            return f'<td style="padding:10px 14px;color:#888;font-size:0.72rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase">{label}</td>'

        table_html = (
            '<table style="width:100%;border-collapse:collapse;background:white;border-radius:8px;'
            'box-shadow:0 1px 3px rgba(0,0,0,0.06);margin-bottom:14px;overflow:hidden">'
            '<thead><tr style="border-bottom:1px solid #eee">'
            '<th style="padding:14px"></th>'
            f'<th style="padding:14px;text-align:right;color:{magenta};font-size:0.72rem;font-weight:800;letter-spacing:0.08em">FHI QUOTE</th>'
            '<th style="padding:14px;text-align:right;color:#888;font-size:0.72rem;font-weight:800;letter-spacing:0.08em">CURRENT INSURER</th>'
            '<th style="padding:14px;text-align:right;color:#888;font-size:0.72rem;font-weight:800;letter-spacing:0.08em">THEIR RENEWAL</th>'
            '</tr></thead><tbody>'
            f'<tr style="border-bottom:1px solid #f5f5f5">{_td_label("Members")}'
            f'<td style="padding:10px 14px;text-align:right;color:#282f4b;font-weight:700">{mbrs_quote if mbrs_quote is not None else "—"} '
            f'<span style="font-size:0.7rem;color:#aaa;font-weight:400">(quote)</span></td>'
            f'{_td_int(mbrs_curr)}{_td_int(mbrs_renew)}</tr>'
            f'<tr style="border-bottom:1px solid #f5f5f5">{_td_label("Total Annual")}'
            f'{_td_money(our_a, magenta, "800")}{_td_money(cur_a)}{_td_money(ren_a)}</tr>'
            f'<tr style="border-bottom:1px solid #f5f5f5">{_td_label("Total Monthly")}'
            f'{_td_money(our_m, magenta, "800")}{_td_money(cur_m)}{_td_money(ren_m)}</tr>'
            f'<tr>{_td_label("Avg / Member / Yr")}'
            f'<td style="padding:10px 14px;text-align:right;color:{magenta};font-weight:800">{_avg(our_a, mbrs_quote)}</td>'
            f'<td style="padding:10px 14px;text-align:right;color:#282f4b;font-weight:700">{_avg(cur_a, mbrs_curr)}</td>'
            f'<td style="padding:10px 14px;text-align:right;color:#282f4b;font-weight:700">{_avg(ren_a, mbrs_renew)}</td></tr>'
            '</tbody></table>'
        )
        st.markdown(table_html, unsafe_allow_html=True)

        # ── Three comparison metrics below the table ──
        def _color_renewal(v):
            if v is None: return "#888"
            if v >= 50:   return "#e76f51"
            if v <= 0:    return "#e9c46a"
            return "#2a9d8f"

        def _color_position(v):
            if v is None: return "#888"
            if v < -20:   return "#e76f51"
            if v <= 0:    return "#2a9d8f"
            return "#888"

        def _delta(label, value, color):
            return (
                f'<div style="padding:0 14px">'
                f'<div style="font-size:0.7rem;color:#aaa;text-transform:uppercase;letter-spacing:0.08em;font-weight:700;margin-bottom:4px">{label}</div>'
                f'<div style="font-size:1.3rem;color:{color};font-weight:800">{value}</div></div>'
            )

        deltas_html = (
            '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:0;'
            'padding:12px 0;border-top:1px dashed #ddd;border-bottom:1px dashed #ddd;margin-bottom:20px">'
            + _delta("Renewal — Per-Member (true)",
                     f"{true_incr:+.1f}%" if true_incr is not None else "—",
                     _color_renewal(true_incr))
            + _delta("Renewal — Total (naive)",
                     f"{naive_incr:+.1f}%" if naive_incr is not None else "—",
                     _color_renewal(naive_incr))
            + _delta("FHI vs Renewal",
                     f"{pos_vs_ren:+.1f}%" if pos_vs_ren is not None else "—",
                     _color_position(pos_vs_ren))
            + '</div>'
        )
        st.markdown(deltas_html, unsafe_allow_html=True)

        # ── Suggested Release Pricing — styled card layout ────────────────────
        sug_a = sel.get("SuggestedRelease_Annual")
        sug_m = sel.get("SuggestedRelease_Monthly")
        if sug_a or sug_m:
            is_release = (rec == "RELEASE")
            border_col  = "#2a9d8f" if is_release else "#ccc"
            bg          = "#f0fff4" if is_release else "white"
            value_col   = "#2a9d8f" if is_release else "#282f4b"

            def _release_card(period, value, binding, aggressive, cap):
                return (
                    f'<div style="background:{bg};border:2px solid {border_col};'
                    f'border-radius:10px;padding:18px 22px;height:100%">'
                    f'<div style="font-size:0.7rem;color:#888;text-transform:uppercase;'
                    f'letter-spacing:0.1em;font-weight:700;margin-bottom:6px">'
                    f'Suggested {period} Release Price</div>'
                    f'<div style="font-size:1.9rem;color:{value_col};font-weight:800;'
                    f'letter-spacing:-0.02em">{value}</div>'
                    f'<div style="margin-top:12px;padding-top:10px;border-top:1px dashed #ddd;'
                    f'font-size:0.78rem">'
                    f'<div style="display:flex;justify-content:space-between;margin-bottom:3px">'
                    f'<span style="color:#888;font-weight:700">R−20%</span>'
                    f'<span style="font-weight:700;color:#282f4b">{aggressive}</span></div>'
                    f'<div style="display:flex;justify-content:space-between;margin-bottom:6px">'
                    f'<span style="color:#888;font-weight:700">FHI base −10% cap</span>'
                    f'<span style="font-weight:700;color:#282f4b">{cap}</span></div>'
                    f'<div style="display:flex;justify-content:space-between;'
                    f'padding-top:6px;border-top:1px dotted #eee">'
                    f'<span style="color:#888;font-weight:700">Binding</span>'
                    f'<span style="font-weight:800;color:#006f8e">{binding}</span></div>'
                    f'</div></div>'
                )

            st.markdown(
                "<div class='section-label'>Suggested Release Pricing — §12 formula, applied independently to monthly & annual</div>",
                unsafe_allow_html=True,
            )

            cards_html = "<div style='display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:12px'>"
            if sug_a:
                cards_html += _release_card(
                    "Annual",
                    fmt_money(sug_a),
                    sel.get("SuggestedRelease_Annual_Binding", "—"),
                    fmt_money(sel.get("SuggestedRelease_Annual_Aggressive")),
                    fmt_money(sel.get("SuggestedRelease_Annual_Cap")),
                )
            else:
                cards_html += '<div style="padding:18px;color:#aaa;background:#fafafa;border-radius:10px">No annual figure available</div>'
            if sug_m:
                cards_html += _release_card(
                    "Monthly",
                    fmt_money(sug_m),
                    sel.get("SuggestedRelease_Monthly_Binding", "—"),
                    fmt_money(sel.get("SuggestedRelease_Monthly_Aggressive")),
                    fmt_money(sel.get("SuggestedRelease_Monthly_Cap")),
                )
            else:
                cards_html += '<div style="padding:18px;color:#aaa;background:#fafafa;border-radius:10px">No monthly figure available</div>'
            cards_html += "</div>"
            st.markdown(cards_html, unsafe_allow_html=True)

            if sug_m:
                annual_equiv = sug_m * 12
                st.markdown(
                    f'<div style="padding:10px 14px;background:#e8f4f8;border-left:3px solid #006f8e;'
                    f'border-radius:0 6px 6px 0;font-size:0.82rem;color:#555;margin-bottom:10px">'
                    f'Calculations are <strong style="color:#282f4b">independent</strong> — '
                    f'annual reflects the 6% annual-payment discount; monthly does not. '
                    f'<strong>£{sug_m:,.2f} × 12 = £{annual_equiv:,.2f}</strong> '
                    f'(un-discounted monthly cost over the year).</div>',
                    unsafe_allow_html=True,
                )
            if not is_release:
                st.markdown(
                    f'<div style="padding:10px 14px;background:#fff8e1;border-left:3px solid #e9c46a;'
                    f'border-radius:0 6px 6px 0;font-size:0.82rem;color:#555;margin-bottom:10px">'
                    f'Quote is currently <strong>{rec}</strong> — suggested prices only applicable '
                    f'once any referral is cleared.</div>',
                    unsafe_allow_html=True,
                )
            our_a = sel.get("OurAnnual")
            if sug_a and our_a and sug_a > our_a * 1.5:
                st.markdown(
                    '<div style="padding:10px 14px;background:#fdecea;border-left:3px solid #e76f51;'
                    'border-radius:0 6px 6px 0;font-size:0.82rem;color:#555;margin-bottom:20px">'
                    '<strong>Anomalous result:</strong> formula returns a price far above our CRM quote. '
                    'Likely indicates inconsistent renewal data or current insurer\'s renewal is out of line. '
                    'Verify before applying.</div>',
                    unsafe_allow_html=True,
                )

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

            # ── Override reason — always visible so it's available before the click ──
            override_reason = st.text_area(
                "Override reason — required only if your decision differs from the system recommendation:",
                key=f"reason_{sel_qno}",
                height=80,
                placeholder="e.g. 'Senior UW authorised'; 'Additional broker context received'; ..."
            )

            # ── Brand the primary decision button (matches recommendation) in FHI magenta ──
            st.markdown("""
                <style>
                  div[data-testid="stButton"] > button[kind="primary"] {
                    background-color: #990858;
                    border-color: #990858;
                    color: white;
                    font-weight: 800;
                    letter-spacing: 0.02em;
                  }
                  div[data-testid="stButton"] > button[kind="primary"]:hover {
                    background-color: #7a0747;
                    border-color: #7a0747;
                    color: white;
                  }
                  div[data-testid="stButton"] > button[kind="secondary"] {
                    border-color: #ddd;
                    color: #555;
                  }
                </style>
            """, unsafe_allow_html=True)

            def _attempt_decision(decision):
                """One-click decision recording. Override requires reason, otherwise shows warning."""
                reason = (override_reason or "").strip()
                is_override = (decision != rec)
                if is_override and not reason:
                    st.warning(
                        f"⚠️ You are overriding the system recommendation ({rec} → {decision}). "
                        "Please type a reason in the box above, then click the button again."
                    )
                    return
                record_reviewer_decision(
                    client, ref_id, decision, rec,
                    override_reason=reason if is_override else "",
                    final_annual=(final_a if use_override_prem else sug_a),
                    final_monthly=(final_m if use_override_prem else sug_m),
                )
                if decision == "RELEASE":
                    st.success(f"✅ RELEASE recorded. Reference: **{ref_id}**")
                    st.balloons()
                elif decision == "REFER":
                    st.warning(f"⚠️ REFER recorded. Reference: **{ref_id}**")
                else:
                    st.error(f"❌ DECLINE recorded. Reference: **{ref_id}**")
                st.session_state.pop("selected_quote_no", None)
                st.rerun()

            dcols = st.columns(3)
            if dcols[0].button("✅ Confirm & Release", key=f"btn_release_{sel_qno}",
                               use_container_width=True,
                               type="primary" if rec == "RELEASE" else "secondary"):
                _attempt_decision("RELEASE")

            if dcols[1].button("⚠️ Confirm & Refer", key=f"btn_refer_{sel_qno}",
                               use_container_width=True,
                               type="primary" if rec == "REFER" else "secondary"):
                _attempt_decision("REFER")

            if dcols[2].button("❌ Confirm & Decline", key=f"btn_decline_{sel_qno}",
                               use_container_width=True,
                               type="primary" if rec == "DECLINE" else "secondary"):
                _attempt_decision("DECLINE")

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
