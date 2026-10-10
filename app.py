"""Streamlit UI: filters, status table, charts, and a reviewed weekly report export."""
import io
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from initiative_tracker.data import STATUSES, load_initiatives
from initiative_tracker.metrics import (
    HEALTH_ORDER, compute_health, default_as_of, portfolio_summary, rollup,
)
from initiative_tracker.report import build_report, get_rephraser

SAMPLE = Path(__file__).parent / "data" / "initiatives.csv"
HEALTH_COLORS = {"Red": "#d03b3b", "Amber": "#fab219", "Green": "#0ca30c", "Done": "#898781"}
HEALTH_SCALE = alt.Scale(domain=list(HEALTH_COLORS), range=list(HEALTH_COLORS.values()))

st.set_page_config(page_title="Initiative Tracker", layout="wide")


@st.cache_data
def load(data: bytes | None) -> pd.DataFrame:
    return load_initiatives(io.BytesIO(data) if data else SAMPLE)


@st.cache_resource
def rephraser():
    return get_rephraser()


# --- data & filters -----------------------------------------------------------

st.sidebar.header("Data")
upload = st.sidebar.file_uploader("CSV (blank = sample data)", type="csv")
try:
    df = load(upload.getvalue() if upload else None)
except ValueError as e:
    st.error(f"Could not load CSV: {e}")
    st.stop()

as_of = pd.Timestamp(st.sidebar.date_input(
    "As of", value=default_as_of(df).date(), help="Defaults to the latest update in the data."))
h = compute_health(df, as_of)

st.sidebar.header("Filters")
filters = {
    "workstream": st.sidebar.multiselect("Workstream", sorted(h["workstream"].unique())),
    "owner": st.sidebar.multiselect("Owner", sorted(h["owner"].unique())),
    "status": st.sidebar.multiselect("Status", [s for s in STATUSES if s in set(h["status"])]),
    "health": st.sidebar.multiselect("Health", [x for x in HEALTH_ORDER if x in set(h["health"])]),
}
view = h
for col, chosen in filters.items():
    if chosen:
        view = view[view[col].isin(chosen)]
scope = "; ".join(f"{c.title()}: {', '.join(v)}" for c, v in filters.items() if v) or "All initiatives"

st.title("Initiative Tracker")
st.caption(f"As of {as_of:%Y-%m-%d} · {scope}")
if view.empty:
    st.warning("No initiatives match the filters.")
    st.stop()

# --- headline numbers -----------------------------------------------------------

s = portfolio_summary(view)
cols = st.columns(6)
for c, (label, key) in zip(cols, [("Open", "open"), ("Red", "red"), ("Amber", "amber"),
                                  ("Overdue", "overdue"), ("Slipping", "slipping"), ("Stale", "stale")]):
    c.metric(label, s[key])

# --- status table ---------------------------------------------------------------

st.subheader("Status")
table = view.assign(_o=view["health"].map({k: i for i, k in enumerate(HEALTH_ORDER)}))
table = table.sort_values(["_o", "days_overdue", "schedule_gap"], ascending=[True, False, True])
st.dataframe(
    table[["health", "initiative", "workstream", "owner", "status", "percent_complete",
           "expected_pct", "due", "days_since_update", "flags", "risk_note"]],
    hide_index=True,
    width="stretch",
    column_config={
        "percent_complete": st.column_config.ProgressColumn("% complete", min_value=0, max_value=100, format="%d%%"),
        "expected_pct": st.column_config.NumberColumn("% expected", format="%.0f%%"),
        "due": st.column_config.DateColumn("Due"),
        "days_since_update": st.column_config.NumberColumn("Days since update"),
    },
)

# --- charts ---------------------------------------------------------------------

health_legend = alt.Legend(title="Health", orient="top")


def stacked_health_bar(data: pd.DataFrame, by: str, x_title: str) -> alt.Chart:
    counts = data.groupby([by, "health"]).size().reset_index(name="initiatives")
    counts["rank"] = counts["health"].map(HEALTH_ORDER.index)
    return alt.Chart(counts).mark_bar().encode(
        y=alt.Y(f"{by}:N", title=None, sort="-x"),
        x=alt.X("initiatives:Q", title=x_title, axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("health:N", scale=HEALTH_SCALE, legend=health_legend),
        order=alt.Order("rank:Q"),
        tooltip=[by, "health", "initiatives"],
    )


c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("**Health by workstream**")
    st.altair_chart(stacked_health_bar(view, "workstream", "Initiatives"), width="stretch")

with c2:
    st.markdown("**Progress vs plan (open items)**")
    open_ = view[view["status"] != "Done"]
    diag = alt.Chart(pd.DataFrame({"x": [0, 100], "y": [0, 100]})).mark_line(
        color="#898781", strokeDash=[4, 4], strokeWidth=1).encode(x="x:Q", y="y:Q")
    dots = alt.Chart(open_).mark_circle(size=90, opacity=0.9).encode(
        x=alt.X("expected_pct:Q", title="% expected by now", scale=alt.Scale(domain=[0, 100])),
        y=alt.Y("percent_complete:Q", title="% complete", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("health:N", scale=HEALTH_SCALE, legend=health_legend),
        tooltip=["initiative", "owner", "status", "percent_complete", "expected_pct", "flags"],
    )
    st.altair_chart(diag + dots, width="stretch")
    st.caption("Below the dashed line = behind a linear plan.")

with c3:
    st.markdown("**Items needing attention by owner**")
    attn = view[view["health"].isin(["Red", "Amber"])]
    if attn.empty:
        st.caption("No red or amber items.")
    else:
        st.altair_chart(stacked_health_bar(attn, "owner", "Red + Amber initiatives"), width="stretch")

with st.expander("Rollups"):
    a, b = st.columns(2)
    a.markdown("**By workstream**")
    a.dataframe(rollup(view, "workstream"), hide_index=True, width="stretch")
    b.markdown("**By owner**")
    b.dataframe(rollup(view, "owner"), hide_index=True, width="stretch")

# --- weekly report: generate -> edit -> approve -> export --------------------------

st.subheader("Weekly report")


def generate():
    model, note = rephraser()
    r = build_report(view, as_of, scope, rephraser=model)
    st.session_state.draft = r.markdown
    st.session_state.report_info = (r.backend, r.note or note)
    st.session_state.approved = False


def unapprove():
    st.session_state.approved = False


st.button("Generate weekly report", type="primary", on_click=generate)

if "draft" in st.session_state:
    backend, note = st.session_state.report_info
    st.caption(f"Summary wording: {backend}. Tables and numbers are computed, not generated.")
    if note:
        st.info(note)
    edit, preview = st.tabs(["Edit", "Preview"])
    with edit:
        st.text_area("Review and edit before export", key="draft", height=480, on_change=unapprove)
    with preview:
        st.markdown(st.session_state.draft)
    st.checkbox("I have reviewed this report and approve it for distribution", key="approved")
    st.download_button(
        "Export markdown",
        data=st.session_state.draft,
        file_name=f"weekly-status-{as_of:%Y-%m-%d}.md",
        mime="text/markdown",
        disabled=not st.session_state.approved,
    )
