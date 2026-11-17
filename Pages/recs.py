"""Milestone 5 - Ocotillo Bay Lodges: where should the first birding lodge go?

One page, four panels, in the order the CEO needs them:
  1. Recommendation + lead decision visual (four regions x three forces)
  2. Forward-looking calendar: birders by month per region
  3. The "why" drill-down: specialties you can still see in every sampled month
  4. Caveats: both data traps (with counts and handling) and what the data can't say

Every number on the page is computed from the parquet at load time.
"""

import os

import altair as alt
import pandas as pd
import streamlit as st

try:
    from constants import BLUE, GRAY_DARK, GRAY_LIGHT, RED
except ImportError:  # running from inside milestone5/
    GRAY_LIGHT, GRAY_DARK, RED, BLUE = '#C2C6CC', '#6B7280', '#D62728', '#08519c'

# ---------------------------------------------------------------------------
# Settings - point DATA_PATH at the same parquet your other pages read.
# ---------------------------------------------------------------------------
DATA_PATH = os.environ.get(
        'BIRD_PARQUET', 'gs://cs329e-fall2026rocketlabs/processed/birddb_enriched.parquet')

# The call. Check it against the lead chart once the real numbers load.
PICK = 'Lower Rio Grande Valley'
RUNNER_UP = 'Upper Texas Coast'

REGIONS = ['Lower Rio Grande Valley', 'Upper Texas Coast',
           'Coastal Bend', 'Big Bend & Davis Mtns']
SHORT = {'Lower Rio Grande Valley': 'Rio Grande Valley',
         'Upper Texas Coast': 'Upper Coast',
         'Coastal Bend': 'Coastal Bend',
         'Big Bend & Davis Mtns': 'Big Bend'}
MONTHS = {1: 'Jan', 5: 'May', 10: 'Oct'}
MONTH_ORDER = ['Jan', 'May', 'Oct']

# The trade-off each region forces you to own (from the brief).
TRADEOFF = {
    'Lower Rio Grande Valley': 'a seasonal trough: fewer birders in the quietest month',
    'Upper Texas Coast': 'a thin unique draw: few birds you can only see there',
    'Coastal Bend': 'a January-heavy market around Rockport',
    'Big Bend & Davis Mtns': 'a small market: the fewest birders of the four',
}

DEDUP_KEYS = ['species', 'decimalLatitude', 'decimalLongitude',
              'eventDate', 'individualCount']
COLUMNS = ['species', 'recordedBy', 'month', 'eventDate', 'decimalLatitude',
           'decimalLongitude', 'individualCount', 'grid_lat', 'grid_lng',
           'county_name']


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def assign_region(lat: pd.Series, lng: pd.Series) -> pd.Series:
    """Brief's boxes, applied to grid_lat / grid_lng (never county_name)."""
    region = pd.Series(pd.NA, index=lat.index, dtype='object')
    region[(lat <= 26.6) & (lng >= -99.3)] = 'Lower Rio Grande Valley'
    region[lat.between(27.3, 28.5) & lng.between(-97.9, -96.5)] = 'Coastal Bend'
    region[lat.between(28.8, 29.7) & (lng >= -95.4)] = 'Upper Texas Coast'
    region[(lat <= 31.0) & (lng <= -102.6)] = 'Big Bend & Davis Mtns'
    return region


def load_raw(path: str) -> pd.DataFrame:
    try:
        df = pd.read_parquet(path, columns=COLUMNS + ['stateProvince'])
    except (KeyError, ValueError):  # stateProvince not kept in this file
        df = pd.read_parquet(path, columns=COLUMNS)
    return df


@st.cache_data(show_spinner='Crunching 2 million sightings...')
def build_tables(path: str) -> dict:
    """Return only small summary tables, so the cache stays light."""
    raw = load_raw(path)
    n_raw = len(raw)

    # Housekeeping: Texas only.
    if 'stateProvince' in raw.columns:
        df = raw[raw['stateProvince'] == 'Texas'].copy()
    else:
        df = raw.copy()
    n_non_tx = n_raw - len(df)
    del raw

    df['region'] = assign_region(df['grid_lat'], df['grid_lng'])

    # Trap 1: blank county_name (only cells with a ZIP centroid were matched).
    blank_county = df['county_name'].isna() | (df['county_name'].astype(str).str.strip() == '')
    trap1 = {
        'rows': int(blank_county.sum()),
        'share': float(blank_county.mean()),
        'by_region': (df.assign(blank=blank_county)
                        .dropna(subset=['region'])
                        .groupby('region')['blank'].mean()
                        .reindex(REGIONS).to_dict()),
    }

    # Trap 2: shared-checklist duplicates. Same sighting, several observers.
    dup_mask = df.duplicated(subset=DEDUP_KEYS, keep='first')
    trap2 = {
        'rows': int(dup_mask.sum()),
        'share': float(dup_mask.mean()),
        'by_region': (df.assign(dup=dup_mask)
                        .dropna(subset=['region'])
                        .groupby('region')['dup'].mean()
                        .reindex(REGIONS).to_dict()),
    }

    # Sightings (birds) use the de-duplicated table; people use every row.
    birds = df.loc[~dup_mask, ['species', 'region', 'month', 'grid_lat', 'grid_lng']]
    people = df.loc[df['region'].notna(), ['region', 'month', 'recordedBy']]

    # --- Unique draw: specialty species --------------------------------------
    tx_total = birds.groupby('species').size().rename('tx_sightings')
    in_reg = birds.dropna(subset=['region'])
    per_reg = in_reg.groupby(['region', 'species']).size().rename('sightings').reset_index()
    cells = (in_reg.drop_duplicates(['region', 'species', 'grid_lat', 'grid_lng'])
                   .groupby(['region', 'species']).size().rename('cells'))
    per_reg = per_reg.join(cells, on=['region', 'species'])
    per_reg = per_reg.join(tx_total, on='species')
    per_reg['share'] = per_reg['sightings'] / per_reg['tx_sightings']
    specialties = per_reg[(per_reg['share'] >= 0.5)
                          & (per_reg['sightings'] >= 25)
                          & (per_reg['cells'] >= 3)].copy()

    # Which months each specialty was seen in, inside its region.
    months_seen = (in_reg.merge(specialties[['region', 'species']], on=['region', 'species'])
                         .groupby(['region', 'species'])['month'].nunique()
                         .rename('n_months'))
    specialties = specialties.join(months_seen, on=['region', 'species'])
    n_sampled = birds['month'].nunique()
    specialties['year_round'] = specialties['n_months'] >= n_sampled

    # --- Market size + calendar ---------------------------------------------
    market = people.groupby('region')['recordedBy'].nunique().reindex(REGIONS)
    monthly = (people.groupby(['region', 'month'])['recordedBy'].nunique()
                     .rename('birders').reset_index())
    monthly['month_label'] = monthly['month'].map(MONTHS).fillna(monthly['month'].astype(str))
    steadiness = monthly.groupby('region')['birders'].agg(lambda s: s.min() / s.max())
    quiet_month = monthly.loc[monthly.groupby('region')['birders'].idxmin()].set_index('region')['month_label']

    forces = pd.DataFrame({
        'region': REGIONS,
        'specialties': specialties.groupby('region').size().reindex(REGIONS).fillna(0).astype(int).values,
        'year_round_specialties': specialties[specialties['year_round']].groupby('region').size()
                                      .reindex(REGIONS).fillna(0).astype(int).values,
        'birders': market.fillna(0).astype(int).values,
        'steadiness': steadiness.reindex(REGIONS).values,
        'quiet_month': quiet_month.reindex(REGIONS).values,
    })

    return {
        'forces': forces,
        'monthly': monthly,
        'specialties': specialties[['region', 'species', 'sightings', 'cells',
                                    'share', 'n_months', 'year_round']],
        'trap1': trap1,
        'trap2': trap2,
        'n_tx': len(df),
        'n_non_tx': n_non_tx,
        'n_birds': len(birds),
        'n_species': int(df['species'].nunique()),
        'n_birders': int(df['recordedBy'].nunique()),
        'months_sampled': [MONTHS.get(m, str(m)) for m in sorted(birds['month'].dropna().unique())],
    }


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def _highlight(field='region'):
    return alt.condition(alt.datum[field] == PICK, alt.value(BLUE), alt.value(GRAY_LIGHT))


def lead_chart(forces: pd.DataFrame) -> alt.HConcatChart:
    """Four regions x three forces. Same row order in every panel; pick in blue."""
    d = forces.copy()
    d['steady_pct'] = d['steadiness'] * 100
    order = [PICK] + [r for r in REGIONS if r != PICK]
    y = alt.Y('region:N', sort=order, title=None,
              axis=alt.Axis(labelFontSize=13, labelLimit=220, ticks=False, domain=False,
                            labelFontWeight=alt.expr(f"datum.value == '{PICK}' ? 'bold' : 'normal'"),
                            labelColor=alt.expr(f"datum.value == '{PICK}' ? '{BLUE}' : '{GRAY_DARK}'")))

    def panel(field, title, subtitle, fmt, show_y):
        base = alt.Chart(d).encode(
            y=y if show_y else y.axis(None),
            tooltip=[alt.Tooltip('region:N', title='Region'),
                     alt.Tooltip('specialties:Q', title='Specialty species'),
                     alt.Tooltip('birders:Q', title='Distinct birders', format=','),
                     alt.Tooltip('steady_pct:Q', title='Quietest month, % of busiest', format='.0f'),
                     alt.Tooltip('quiet_month:N', title='Quietest month')])
        bars = base.mark_bar(cornerRadiusEnd=4, height=26).encode(
            x=alt.X(f'{field}:Q', title=None, axis=None,
                    scale=alt.Scale(domain=[0, 100]) if field == 'steady_pct' else alt.Undefined),
            color=_highlight())
        enc = dict(x=f'{field}:Q', text=alt.Text(f'{field}:Q', format=fmt))
        others = base.mark_text(align='left', dx=5, fontSize=13, color=GRAY_DARK).encode(
            **enc).transform_filter(alt.datum.region != PICK)
        pick = base.mark_text(align='left', dx=5, fontSize=13, color=BLUE, fontWeight='bold').encode(
            **enc).transform_filter(alt.datum.region == PICK)
        return (bars + others + pick).properties(
            width=210, height=190,
            title=alt.TitleParams(title, subtitle=subtitle, anchor='start', fontSize=15,
                                  subtitleColor=GRAY_DARK, subtitleFontSize=12))

    return alt.hconcat(
        panel('specialties', 'Unique draw', 'Specialty species, mostly seen only here', 'd', True),
        panel('birders', 'Market size', 'Distinct birders reporting here', ',', False),
        panel('steady_pct', 'Year-round demand', 'Quietest month as % of busiest', '.0f', False),
        spacing=28,
    ).configure_view(stroke=None).configure_concat(spacing=28)


def calendar_chart(monthly: pd.DataFrame) -> alt.FacetChart:
    d = monthly.copy()
    d['label'] = d['region'].map(SHORT)
    order = [SHORT[PICK]] + [SHORT[r] for r in REGIONS if r != PICK]
    base = alt.Chart(d).encode(
        x=alt.X('month_label:N', sort=MONTH_ORDER, title=None,
                axis=alt.Axis(labelAngle=0, labelFontSize=12, ticks=False, domain=False)),
        tooltip=[alt.Tooltip('region:N', title='Region'),
                 alt.Tooltip('month_label:N', title='Month'),
                 alt.Tooltip('birders:Q', title='Distinct birders', format=',')])
    bars = base.mark_bar(cornerRadiusEnd=4, width=34).encode(
        y=alt.Y('birders:Q', title='Distinct birders',
                axis=alt.Axis(grid=True, gridColor='#EEF0F3', tickCount=4, domain=False, ticks=False)),
        color=_highlight())
    text = base.mark_text(dy=-7, fontSize=11, color=GRAY_DARK).encode(
        y='birders:Q', text=alt.Text('birders:Q', format=','))
    return (bars + text).properties(width=150, height=200).facet(
        column=alt.Column('label:N', sort=order, title=None,
                          header=alt.Header(labelFontSize=13, labelFontWeight='bold',
                                            labelOrient='top'))
    ).configure_view(stroke=None)


def drilldown_chart(forces: pd.DataFrame) -> alt.LayerChart:
    """Total specialties (light) with the subset seen in every sampled month (solid)."""
    d = forces.melt(id_vars='region', value_vars=['specialties', 'year_round_specialties'],
                    var_name='kind', value_name='n')
    order = [PICK] + [r for r in REGIONS if r != PICK]
    tip = [alt.Tooltip('region:N', title='Region'), alt.Tooltip('n:Q', title='Species')]
    y = alt.Y('region:N', sort=order, title=None,
              axis=alt.Axis(labelFontSize=13, labelLimit=220, ticks=False, domain=False))
    total = alt.Chart(d[d['kind'] == 'specialties']).mark_bar(
        cornerRadiusEnd=4, height=26, color='#E5E7EB').encode(
        y=y, x=alt.X('n:Q', title='Specialty species', axis=alt.Axis(grid=False, tickCount=5)),
        tooltip=tip)
    yr = alt.Chart(d[d['kind'] == 'year_round_specialties']).mark_bar(
        cornerRadiusEnd=4, height=26).encode(
        y=y, x='n:Q', color=_highlight(), tooltip=tip)
    yr_lbl = alt.Chart(d[d['kind'] == 'year_round_specialties']).mark_text(
        align='right', dx=-6, fontWeight='bold', fontSize=12).encode(
        y=y, x='n:Q', text='n:Q',
        color=alt.condition(alt.datum.region == PICK, alt.value('white'), alt.value('#374151'))
    ).transform_filter(alt.datum.n >= 3)
    tot_lbl = alt.Chart(d[d['kind'] == 'specialties']).mark_text(
        align='left', dx=5, color=GRAY_DARK, fontSize=12).encode(
        y=y, x='n:Q', text=alt.Text('n:Q', format='d'))
    return (total + yr + yr_lbl + tot_lbl).properties(width=560, height=190).configure_view(stroke=None)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def rank(forces, col, region):
    return int(forces[col].rank(ascending=False, method='min')[forces['region'] == region].iloc[0])


def pct(x):
    return f'{x * 100:.0f}%'


def render():
    t = build_tables(DATA_PATH)
    f = t['forces'].set_index('region')
    fr = t['forces']
    p, r = f.loc[PICK], f.loc[RUNNER_UP]

    # 1. Recommendation first --------------------------------------------------
    st.title(f'Build the lodge in the {PICK}')
    st.markdown(
        f"**{PICK}** has **{p.specialties} specialty species** (#{rank(fr, 'specialties', PICK)} of 4), "
        f"**{p.birders:,} birders** (#{rank(fr, 'birders', PICK)}), and its quietest month keeps "
        f"**{pct(p.steadiness)}** of its busiest (#{rank(fr, 'steadiness', PICK)}). "
        f"The trade-off we accept: {TRADEOFF[PICK]}.")

    st.subheader('No region wins on all three. Here is the trade-off.')
    st.altair_chart(lead_chart(t['forces']), width='content')
    st.caption('Specialty = at least half of its de-duplicated Texas sightings fall in the region, '
               '25+ sightings there, in 3+ grid cells. Birders = distinct eBird observer IDs.')

    # 2. Calendar --------------------------------------------------------------
    st.subheader('The calendar the lodge would live with')
    st.altair_chart(calendar_chart(t['monthly']), width='content')
    st.caption(f"Distinct birders per sampled month ({', '.join(t['months_sampled'])} 2024). "
               f"{PICK}'s quietest month is {p.quiet_month}, at {pct(p.steadiness)} of its peak; "
               f"the lender's off-season occupancy test lives in that bar.")

    # 3. Why ------------------------------------------------------------------
    st.subheader('Why it wins: birds worth the trip in every season')
    st.altair_chart(drilldown_chart(t['forces']), width='content')
    st.caption(f"Solid bar = specialties recorded in the region in all sampled months; "
               f"light bar = all specialties. {PICK}: {p.year_round_specialties} of "
               f"{p.specialties} specialties show up in every sampled month.")

    # 4. Recommendation + caveats -------------------------------------------
    st.subheader('Recommendation and what the data cannot tell you')
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'#### Pick: {PICK}')
        wins = [(lbl, p[col], r[col]) for col, lbl in
                [('specialties', 'specialty species'), ('birders', 'birders'),
                 ('steadiness', 'off-season share')]]
        fmt = lambda lbl, v: pct(v) if lbl == 'off-season share' else f'{v:,}'
        better = [f'{lbl} ({fmt(lbl, a)} vs {fmt(lbl, b)})' for lbl, a, b in wins if a > b]
        worse = [f'{lbl} ({fmt(lbl, b)} vs {fmt(lbl, a)})' for lbl, a, b in wins if a < b]
        st.markdown(f'**Runner-up rejected: {RUNNER_UP}.**')
        if worse:
            st.markdown(f'{RUNNER_UP} leads on ' + '; '.join(worse) + '.')
        if better:
            st.markdown(f'{PICK} leads on ' + '; '.join(better) + '.')
        st.markdown(f'Choosing {RUNNER_UP} means accepting {TRADEOFF[RUNNER_UP]}. '
                    f'Choosing {PICK} means accepting {TRADEOFF[PICK]}.')
    with c2:
        t1, t2 = t['trap1'], t['trap2']
        st.markdown('#### Two data traps, handled')
        st.markdown(
            f"**Blank county.** {t1['rows']:,} sightings ({pct(t1['share'])}) have no county, because "
            f"only grid cells with a ZIP centroid got one. Refuges and parks drop out "
            f"({pct(t1['by_region']['Big Bend & Davis Mtns'])} of Big Bend rows). "
            f"*Handling:* regions are built from grid_lat/grid_lng, never county_name, and the ZIP "
            f"summary is not used for any count.")
        st.markdown(
            f"**Shared checklists.** {t2['rows']:,} rows ({pct(t2['share'])}) repeat the same species, "
            f"place, date and count under another birder; {pct(t2['by_region']['Lower Rio Grande Valley'])} "
            f"of Valley rows. *Handling:* de-duplicated when counting sightings and specialties; "
            f"kept when counting birders, because each is a real person who went.")
        st.markdown('#### Limits')
        st.markdown(
            f"- **Birders are not guests.** A reporting birder could be a local or a day-tripper; "
            f"this data cannot say who needs a bed.\n"
            f"- **Three months, not twelve.** Only {', '.join(t['months_sampled'])} 2024 were sampled; "
            f"summer and the other off-season months are unseen.\n"
            f"- **One year.** 2024 only; no trend or weather-year effect.\n"
            f"- **Reporting is not visiting.** eBird users are a subset of birders and may report "
            f"more where cell coverage and popular hotspots are.\n"
            f"- **Counts ignored.** individualCount is never averaged (one wetland logs 2,000,000 "
            f"Barn Swallows).\n"
            f"- Housekeeping: {t['n_non_tx']:,} non-Texas rows dropped.")


render()