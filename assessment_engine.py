"""
Freedom Health Insurance — Quote Assessment Engine
Aligned to PMI Group New Business Quote Parameters v2.1 (effective 01 Apr 2026)

Pure functions. No I/O. Imported by refresh_dashboard.py.
"""
import re
import math
import pandas as pd

FREQ_MULT = {'Monthly': 12, 'Quarterly': 4, 'Annually': 1, 'Annual': 1}

# §11 — Authority / Licence Levels
AUTHORITY_TABLE = {
    'clare.smith':      ('Clare Smith',      'Assistant Underwriter',    'Level 4',           30_000),
    'Marcus.Artwell':   ('Marcus Artwell',   'Assistant Underwriter',    'Level 4',           30_000),
    'Lynne Heath':      ('Lynne Heath',      'Customer Service Manager', 'Level 8',           250_000),
    'Martin Pojur':     ('Martin Pojur',     'Senior Underwriter',       'Senior Underwriter', 500_000),
    'AlexandraRosu':    ('Alexandra Rosu',   'Assistant Underwriter',    'Level 4',           30_000),
    'Shannon.Bennett':  ('Shannon Bennett',  'Assistant Underwriter',    'Level 4',           30_000),
    'steve.hudson':     ('Steve Hudson',     'Sales Assistant',          'Level 4',           30_000),
    'Hoosh Mires':      ('Hoosh Mires',      'Chief Operating Officer',  'COO',               float('inf')),
}

# §12 — Per-life refer thresholds by underwriting type
PER_LIFE_THRESHOLDS = {
    'Moratorium':       271,
    'CPME':             838,
    'Switch Moratorium':687,
    'MHD':              753,
    'FMU':              271,
}

def age_band(avg_age):
    if avg_age is None: return ('—', 'neutral')
    if avg_age < 30:  return ('Excellent', 'good')
    if avg_age <= 40: return ('Good',      'good')
    if avg_age <= 50: return ('Fair',      'neutral')
    if avg_age <= 56: return ('Poor',      'warn')
    return ('Decline band', 'bad')

def renewal_band(incr):
    if incr is None: return ('—', 'neutral')
    if incr <= 0:    return ('Held / reduced — investigate', 'warn')
    if incr <= 10:   return ('Excellent', 'good')
    if incr <= 20:   return ('Good',      'good')
    if incr <= 35:   return ('Fair',      'neutral')
    if incr < 50:    return ('Poor',      'warn')
    return ('Decline (50%+)', 'bad')

def ppl_band(ppl):
    if ppl is None: return ('—', 'neutral')
    if ppl < 500:    return ('Poor (<£500)',           'warn')
    if ppl < 600:    return ('Fair (£500-600)',        'neutral')
    if ppl < 800:    return ('Good (£600-800)',        'good')
    if ppl < 1000:   return ('Very Good (£800-1000)',  'good')
    return ('Excellent (£1000+)', 'good')

def parse_money(v):
    """Parse £-formatted strings like '£8,861.69' to float."""
    if pd.isna(v): return None
    m = re.search(r'£?([\d,]+\.?\d*)', str(v))
    if not m: return None
    try: return float(m.group(1).replace(',', ''))
    except: return None

def to_annual(amount, frequency):
    """Annualise an amount based on payment frequency."""
    if amount is None or pd.isna(amount): return None
    return float(amount) * FREQ_MULT.get(frequency, 1)

def lookup_authority(who_created):
    if not who_created or pd.isna(who_created): return None
    s = str(who_created)
    if s in AUTHORITY_TABLE: return AUTHORITY_TABLE[s]
    norm = s.replace('.', '').replace(' ', '').lower()
    for k, v in AUTHORITY_TABLE.items():
        if k.replace('.', '').replace(' ', '').lower() == norm:
            return v
    return None

def assess_quote(q, m_sub, c_sub):
    """
    Assess a single quote against all checkable Quote Parameters v2.1 rules.
    Returns a dict with recommendation (RELEASE/REFER/DECLINE), flags, checks, and display fields.

    Arguments:
        q     : pandas Series (a row from CLAPA_tbl_PA_Quotes, with derived columns)
        m_sub : pandas DataFrame (members for this quote)
        c_sub : pandas DataFrame (categories for this quote)
    """
    is_unpriced = pd.isna(q.get('AnnualPremium_n'))
    pay_freq = q.get('Payment Frequency')

    our_annual  = float(q['AnnualPremium_n']) if not is_unpriced else None
    our_monthly = parse_money(q.get('MonthlyPremium') or q.get('Monthly Premium')) or (our_annual / 12 if our_annual else None)

    cur_raw = q.get('CurrentInsurerPremium'); ren_raw = q.get('RenewalInsurerPremium')
    cur_annual  = to_annual(cur_raw, pay_freq) if pd.notna(cur_raw) else None
    ren_annual  = to_annual(ren_raw, pay_freq) if pd.notna(ren_raw) else None
    cur_monthly = (cur_annual / 12) if cur_annual else None
    ren_monthly = (ren_annual / 12) if ren_annual else None

    mbrs_ly = q.get('NumberMembersCoveredLastYear')
    mbrs_ty = q.get('NumberMembersCoveredThisYear')
    avg_ly  = q.get('AveragePremiumLastYear')
    avg_ty  = q.get('AveragePremiumThisYear')
    pct_change = q.get('PercentChange')
    avg_ly_annual = to_annual(avg_ly, pay_freq) if pd.notna(avg_ly) else None
    avg_ty_annual = to_annual(avg_ty, pay_freq) if pd.notna(avg_ty) else None
    headcount_changed = (pd.notna(mbrs_ly) and pd.notna(mbrs_ty) and mbrs_ly != mbrs_ty)
    naive_incr = None
    if cur_annual and ren_annual and cur_annual > 0:
        naive_incr = (ren_annual - cur_annual) / cur_annual * 100

    discount = float(q['Discount']) if pd.notna(q.get('Discount')) else 0
    fhi_base = our_annual / (1 - discount/100) if (our_annual and discount and discount > 0) else our_annual
    fhi_monthly_base = our_monthly / (1 - discount/100) if (our_monthly and discount and discount > 0) else our_monthly

    postcode = str(q.get('Postcode') or '').strip().upper()
    town = str(q.get('Town') or '')
    is_iom_ci = bool(re.match(r'^(IM|JE|GY)\d', postcode)) or \
                any(s in town.lower() for s in ['isle of man', 'jersey', 'guernsey'])

    cur_insurer = q.get('CurrentInsurer')
    is_switch = pd.notna(cur_insurer) and str(cur_insurer).strip() != ''

    result = {
        'QuoteNo': int(q['QuoteNo']),
        'QuoteVer': q['QuoteVer'],
        'QuoteVerLink': int(q['QuoteVerLink']) if pd.notna(q.get('QuoteVerLink')) else None,
        'Broker': q['Broker'],
        'QuoteName': q.get('QuoteName'),
        'PolicyNumber': q.get('Policy Number'),
        'DateEntered': str(q.get('DateEntered_dt')),
        'StatusName': q.get('StatusName'),
        'NumMembers': int(len(m_sub)),
        'PaymentFrequency': pay_freq,
        'OurAnnual': our_annual, 'OurMonthly': our_monthly,
        'CurAnnual': cur_annual, 'CurMonthly': cur_monthly,
        'RenAnnual': ren_annual, 'RenMonthly': ren_monthly,
        'AnnualPremium': our_annual,
        'CurrentInsurerPrem': cur_annual,
        'RenewalInsurerPrem': ren_annual,
        'CurrentInsurer': str(cur_insurer) if pd.notna(cur_insurer) else None,
        'IsSwitch': is_switch,
        'MembersLastYear': int(mbrs_ly) if pd.notna(mbrs_ly) else None,
        'MembersThisYear': int(mbrs_ty) if pd.notna(mbrs_ty) else None,
        'HeadcountChanged': bool(headcount_changed),
        'AvgPremLY_perMember_Annual': avg_ly_annual,
        'AvgPremTY_perMember_Annual': avg_ty_annual,
        'TrueRenewalIncrease': round(float(pct_change), 1) if pd.notna(pct_change) else None,
        'NaiveRenewalIncrease': round(naive_incr, 1) if naive_incr is not None else None,
        'Discount': discount if discount > 0 else None,
        'MHDLoading': float(q['MHDLoading']) if pd.notna(q.get('MHDLoading')) else None,
        'EliteLondonHospitals': bool(q.get('EliteLondonHospitals', 0) or 0),
        '2YearFixedRate': bool(q.get('2YearFixedRate', 0) or 0),
        'CorpOrInd': int(q.get('CorpOrInd', 0) or 0),
        'WhoCreated': q.get('WhoCreated'),
        'UWComment': q.get('UWComment'),
        'BrokerComment': q.get('Comment'),
        'HoldingBroker': bool(q.get('HoldingBroker', False) or False),
        'Competitive': bool(q.get('Competitive', False) or False),
        'Postcode': postcode,
        'Town': town,
        'flags': [], 'checks': [],
        'recommendation': None, 'recommendation_reason': None,
        'is_unpriced': is_unpriced,
    }
    is_group = result['CorpOrInd'] == 1 and result['NumMembers'] >= 3

    # §6 Location
    if is_iom_ci:
        result['flags'].append({'severity': 'DECLINE', 'rule': 'Location (CI / IOM)', 'ref': '§6, §12',
            'detail': f"Postcode {postcode} indicates Channel Islands / Isle of Man — decline due to legal restrictions"})
    result['checks'].append({'rule': 'Location not CI/IOM', 'ref': '§6', 'status': 'fail' if is_iom_ci else 'pass', 'detail': postcode or '(no postcode)'})

    # §12 Switching with missing premium info
    if is_switch and (not cur_annual or not ren_annual):
        missing = []
        if not cur_annual: missing.append('current')
        if not ren_annual: missing.append('renewal')
        result['flags'].append({'severity': 'DECLINE', 'rule': 'Switch with missing premium info', 'ref': '§12',
            'detail': f"Switch quote from {cur_insurer} but {' & '.join(missing)} premium not provided"})
        result['checks'].append({'rule': 'Switch info complete', 'ref': '§12', 'status': 'fail', 'detail': f"missing: {', '.join(missing)}"})
    elif is_switch:
        result['checks'].append({'rule': 'Switch info complete', 'ref': '§12', 'status': 'pass', 'detail': f"vs {cur_insurer}"})

    # §4 Group size
    if is_group:
        result['checks'].append({'rule': 'Group Size ≥3', 'ref': '§4', 'status': 'pass', 'detail': f"{result['NumMembers']} members"})

    # §3 Weighted average age
    if not m_sub.empty and 'Insured Age' in m_sub.columns:
        ages = pd.to_numeric(m_sub['Insured Age'], errors='coerce')
        prems = pd.to_numeric(m_sub.get('Annual Premium'), errors='coerce') if 'Annual Premium' in m_sub.columns else pd.Series([], dtype=float)
        ages_v = ages.dropna()
        if len(ages_v):
            avg_age_simple = ages_v.mean()
            valid_mask = ages.notna() & prems.notna() & (prems > 0)
            if valid_mask.sum() and prems[valid_mask].sum() > 0:
                avg_age = (ages[valid_mask] * prems[valid_mask]).sum() / prems[valid_mask].sum()
                weighting = 'premium-weighted'
            else:
                avg_age = avg_age_simple
                weighting = 'simple (no premium data to weight by)'

            over_70 = (ages_v > 70).sum()
            result['AvgMemberAge'] = round(avg_age, 2)
            result['AvgMemberAgeSimple'] = round(avg_age_simple, 2)
            result['AvgAgeWeighting'] = weighting
            result['MaxMemberAge'] = int(ages_v.max())
            result['MembersOver70'] = int(over_70)
            band_name, band_class = age_band(avg_age)
            result['AvgAgeBand'] = band_name
            result['AvgAgeBandClass'] = band_class

            if avg_age >= 57:
                result['flags'].append({'severity': 'DECLINE', 'rule': 'Weighted Avg Age ≥57', 'ref': '§3, §12',
                    'detail': f"Weighted avg age {avg_age:.2f} (decline at ≥57; simple avg {avg_age_simple:.2f})"})
            elif avg_age > 55:
                result['flags'].append({'severity': 'REFER', 'rule': 'Weighted Avg Age >55', 'ref': '§3, §12',
                    'detail': f"Weighted avg age {avg_age:.2f} (refer above 55; simple avg {avg_age_simple:.2f})"})
            result['checks'].append({'rule': 'Weighted avg age <57', 'ref': '§3',
                'status': 'pass' if avg_age <= 55 else 'refer' if avg_age < 57 else 'fail',
                'detail': f"{avg_age:.2f} ({band_name})"})

            if is_group and over_70 > 0:
                if result['NumMembers'] < 10:
                    result['flags'].append({'severity': 'REFER', 'rule': 'Member(s) 70+ in small group', 'ref': '§3',
                        'detail': f"{over_70} member(s) over 70 in a {result['NumMembers']}-life group (<10)"})
                else:
                    result['flags'].append({'severity': 'REFER', 'rule': 'Member(s) 70+', 'ref': '§3',
                        'detail': f"{over_70} member(s) over 70 — acceptable in 10+ groups if premium strong"})
            result['checks'].append({'rule': 'No members 70+', 'ref': '§3', 'status': 'pass' if over_70 == 0 else 'refer', 'detail': f"{over_70} over 70"})

    # §5 Underwriting basis & mix
    uw_types = {}
    dominant_uw = None
    if not m_sub.empty and 'underwriting Type' in m_sub.columns:
        uw_types = m_sub['underwriting Type'].fillna('').replace('', pd.NA).dropna().value_counts().to_dict()
        result['uw_mix'] = uw_types
        n_total = len(m_sub); mhd_count = uw_types.get('MHD', 0)
        mhd_pct = mhd_count / n_total * 100 if n_total else 0
        result['MHD_pct'] = round(mhd_pct, 1)
        has_other = (n_total - mhd_count) > 0
        mixed = mhd_count > 0 and has_other
        pure_mhd = mhd_count > 0 and not has_other
        dominant_uw = max(uw_types, key=uw_types.get) if uw_types else None
        result['DominantUW'] = dominant_uw

        # §4/§12 — PURE MHD scheme size minimum (only applies when 100% MHD)
        if pure_mhd and is_group and n_total < 30:
            result['flags'].append({'severity': 'DECLINE', 'rule': 'Pure MHD scheme <30 (UK)', 'ref': '§4, §12',
                'detail': f"Pure MHD scheme has {n_total} members; UK minimum 30 (worldwide minimum 20 — verify manually)"})

        # §5/§12 — MIXED UW with MHD: decline if >25% MHD, refer otherwise
        if mixed:
            if mhd_pct > 25:
                result['flags'].append({'severity': 'DECLINE', 'rule': 'Mixed UW >25% MHD', 'ref': '§5, §12',
                    'detail': f"{mhd_count}/{n_total} on MHD ({mhd_pct:.0f}%) — exceeds 25% threshold"})
            else:
                result['flags'].append({'severity': 'REFER', 'rule': 'Mixed UW with MHD', 'ref': '§5',
                    'detail': f"{mhd_count} MHD + {n_total - mhd_count} other ({mhd_pct:.0f}% MHD ≤25%)"})

        # Check log entry summarising UW mix
        if pure_mhd and n_total < 30:
            uw_check_status = 'fail'
        elif mixed and mhd_pct > 25:
            uw_check_status = 'fail'
        elif mixed:
            uw_check_status = 'refer'
        else:
            uw_check_status = 'pass'
        result['checks'].append({'rule': 'UW mix', 'ref': '§5',
            'status': uw_check_status,
            'detail': f"{', '.join(f'{k}:{v}' for k,v in uw_types.items() if k)}"})

        # §5 — MHD on switch business (verify previous scheme was MHD)
        if mhd_count > 0 and is_switch:
            result['flags'].append({'severity': 'REFER', 'rule': 'MHD on switch business', 'ref': '§5',
                'detail': f"MHD requested with switch from {cur_insurer} — verify previous scheme was MHD for 3+ years"})

    # §2 Renewal increase
    true_incr = result['TrueRenewalIncrease']
    naive = result['NaiveRenewalIncrease']
    if true_incr is not None:
        band_name, band_class = renewal_band(true_incr)
        result['RenewalBand'] = band_name
        result['RenewalBandClass'] = band_class
        if true_incr >= 50:
            result['flags'].append({'severity': 'DECLINE', 'rule': 'Renewal Increase ≥50% (per-member)', 'ref': '§2, §12',
                'detail': f"+{true_incr:.1f}% per-member yr/yr"})
        elif true_incr <= 0:
            result['flags'].append({'severity': 'REFER', 'rule': 'Held / reduced renewal', 'ref': '§2',
                'detail': f"{true_incr:+.1f}% — investigate why"})
        result['checks'].append({'rule': 'Renewal incr <50% (per-mbr)', 'ref': '§2',
            'status': 'pass' if 0 < true_incr < 50 else 'refer' if true_incr <= 0 else 'fail',
            'detail': f"{true_incr:+.1f}% ({band_name})"})
        if headcount_changed and naive is not None and abs(true_incr - naive) > 5:
            result['flags'].append({'severity': 'INFO', 'rule': 'Headcount changed yr/yr', 'ref': '§2',
                'detail': f"Members {result['MembersLastYear']} → {result['MembersThisYear']}. Naive {naive:+.1f}% vs true per-member {true_incr:+.1f}%"})
        if our_annual and ren_annual:
            # Frequency-aware: monthly payers compared on monthly basis (matches how the client pays)
            if pay_freq == 'Monthly' and our_monthly and ren_monthly:
                pos = (our_monthly - ren_monthly) / ren_monthly * 100
            else:
                pos = (our_annual - ren_annual) / ren_annual * 100
            result['PositionVsRenewal'] = round(pos, 1)
            if is_group and pos < -20:
                result['flags'].append({'severity': 'REFER', 'rule': 'Discount vs renewal >20%', 'ref': '§4',
                    'detail': f"Our quote {pos:.1f}% under renewal (>20% requires Senior UW)"})

    if q.get('2YearFixedRate'):
        result['flags'].append({'severity': 'REFER', 'rule': '2-Year Fixed Rate', 'ref': '§2',
            'detail': 'Decline unless claims information is provided; verify and assess'})

    if discount > 0:
        if discount > 15:
            result['flags'].append({'severity': 'REFER', 'rule': 'Discount >15%', 'ref': '§4, §11',
                'detail': f"{discount}% exceeds Senior UW authority — refer to carrier"})
        elif discount > 10:
            result['flags'].append({'severity': 'REFER', 'rule': 'Discount >10%', 'ref': '§4',
                'detail': f"{discount}% — Senior UW authority required"})
        elif discount > 5:
            result['flags'].append({'severity': 'INFO', 'rule': 'Discount 5-10%', 'ref': '§4',
                'detail': f"{discount}% — Senior UW / COO authority required"})

    # §4 / §12 Premium per life and per-UW-type thresholds
    if is_group and result['NumMembers'] > 0 and (our_annual or our_monthly):
        # Use monthly x 12 when client pays monthly; annual figure otherwise.
        # E.g. monthly x 12 / members gives correct annualised cost-per-life.
        if pay_freq == 'Monthly' and our_monthly:
            ppl = (our_monthly * 12) / result['NumMembers']
        else:
            ppl = our_annual / result['NumMembers']
        result['PremPerLife'] = round(ppl, 0)
        band_name, band_class = ppl_band(ppl)
        result['PremPerLifeBand'] = band_name
        result['PremPerLifeBandClass'] = band_class
        if dominant_uw:
            threshold = PER_LIFE_THRESHOLDS.get(dominant_uw)
            if threshold and ppl < threshold:
                result['flags'].append({'severity': 'REFER',
                    'rule': f'Premium / life below {dominant_uw} threshold', 'ref': '§12',
                    'detail': f"£{ppl:,.0f} < £{threshold:,} (refer threshold for {dominant_uw})"})
                result['checks'].append({'rule': f'Prem/life ≥ {dominant_uw} threshold', 'ref': '§12',
                    'status': 'refer', 'detail': f"£{ppl:,.0f} / £{threshold:,}"})
            elif threshold:
                result['checks'].append({'rule': f'Prem/life ≥ {dominant_uw} threshold', 'ref': '§12',
                    'status': 'pass', 'detail': f"£{ppl:,.0f} ≥ £{threshold:,}"})

    # §11 Authority / licence level
    auth = lookup_authority(q.get('WhoCreated'))
    if auth:
        name, role, level, max_p = auth
        result['CreatorRole'] = role
        result['CreatorLicence'] = level
        result['CreatorMaxPremium'] = max_p if max_p != float('inf') else None
        if our_annual and our_annual > max_p:
            result['flags'].append({'severity': 'REFER', 'rule': 'Premium exceeds creator authority', 'ref': '§11',
                'detail': f"£{our_annual:,.0f} > £{max_p:,.0f} cap ({role}, {level})"})
    elif q.get('WhoCreated'):
        result['CreatorRole'] = 'Not on authority register'
        result['CreatorLicence'] = None
        result['CreatorMaxPremium'] = None

# ===== §12 Release Quote suggested price =====
    # The monthly figure is the un-discounted house reference. The annual figure is
    # derived from monthly by applying FHI's standard 6% annual-payment discount.
    # This guarantees monthly × 12 > annual — matching how FHI invoices clients.
    FHI_ANNUAL_DISCOUNT = 0.06
    fhi_monthly_base = our_monthly / (1 - discount/100) if (our_monthly and discount and discount > 0) else our_monthly

    if our_monthly and ren_monthly and fhi_monthly_base:
        m_aggressive = ren_monthly * 0.80           # R-20% (monthly)
        m_cap        = fhi_monthly_base * 0.90      # FHI base -10% (monthly)

        # Key Health Partnership arrangement: KHP holds a discretionary 10% discount
        # on top of any FHI quote. FHI must therefore quote at base rate (no -10% cap).
        # If R-20% would be binding, reduce to R-10% so that after KHP's 10% the
        # effective floor remains R-20% (not R-30%).
        broker_val = (result.get('Broker') or '').strip()
        is_khp = 'key health' in broker_val.lower()
        if is_khp:
            m_khp_aggressive = ren_monthly * 0.90   # R-10% for KHP (R-20% capped)
            m_khp_cap        = fhi_monthly_base      # FHI base rate (no -10% cap for KHP)
            m_suggested      = max(m_khp_aggressive, m_khp_cap)
            if m_khp_aggressive >= m_khp_cap:
                binding = 'R-10% (KHP: R-20% capped at R-10%)'
            else:
                binding = 'FHI base rate (KHP 10% discount arrangement)'
        else:
            m_suggested = max(m_aggressive, m_cap)
            binding     = 'R-20%' if m_aggressive >= m_cap else 'FHI base -10% cap'

        # Add a REFER flag when quoting for Key Health Partnership
        if is_khp:
            result['flags'].append({
                'severity': 'REFER',
                'rule': 'Key Health Partnership broker',
                'ref': 'KHP Agreement',
                'detail': (
                    'Quote referred: KHP holds a 10% discretionary discount. '
                    'FHI quoting at base rate; R-20% reduced to R-10%. '
                    'After KHP discount: effective floor is FHI base -10% / R-20%.'
                )
            })

        result['SuggestedRelease_Monthly']            = round(m_suggested, 2)
        result['SuggestedRelease_Monthly_Aggressive'] = round(m_aggressive, 2)
        result['SuggestedRelease_Monthly_Cap']        = round(m_cap, 2)
        result['SuggestedRelease_Monthly_Binding']    = binding

        # Annual figures.
        # R-20% is anchored to the CURRENT INSURER's renewal offer (their own
        # commercial premium). We must NOT apply FHI's 6% annual-payment
        # discount to it - the annual R-20% is simply a 20% reduction of the
        # annual renewal. The FHI base -10% cap IS FHI's own pricing, so the
        # 6% annual discount still applies to it.
        fhi_annual_factor = 12 * (1 - FHI_ANNUAL_DISCOUNT)
        a_cap = m_cap * fhi_annual_factor
        if is_khp:
            a_aggressive = (ren_annual * 0.90) if ren_annual else (m_aggressive * 12)
        else:
            a_aggressive = (ren_annual * 0.80) if ren_annual else (m_aggressive * 12)
        a_suggested = max(a_aggressive, a_cap)
        result['SuggestedRelease_Annual']            = round(a_suggested, 2)
        result['SuggestedRelease_Annual_Aggressive'] = round(a_aggressive, 2)
        result['SuggestedRelease_Annual_Cap']        = round(a_cap, 2)
        result['SuggestedRelease_Annual_Binding']    = binding

    if result['EliteLondonHospitals']:
        result['checks'].append({'rule': 'London hospitals selected (+35%)', 'ref': '§6', 'status': 'info', 'detail': 'Loading applies'})

    if is_unpriced:
        result['flags'].append({'severity': 'INFO', 'rule': 'Unpriced quote', 'detail': 'Awaiting CRM premium calculation'})

    severities = [f['severity'] for f in result['flags']]
    if 'DECLINE' in severities:
        result['recommendation'] = 'DECLINE'
        result['recommendation_reason'] = next(f['detail'] for f in result['flags'] if f['severity']=='DECLINE')
    elif 'REFER' in severities:
        result['recommendation'] = 'REFER'
        result['recommendation_reason'] = '; '.join(f['rule'] for f in result['flags'] if f['severity']=='REFER')
    else:
        result['recommendation'] = 'RELEASE'
        result['recommendation_reason'] = 'All checkable guideline rules satisfied'
    return result
