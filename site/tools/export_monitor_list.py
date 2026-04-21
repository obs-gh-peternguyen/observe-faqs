import streamlit as st
import requests
import pandas as pd
from datetime import datetime


def nano_to_datetime(ns: int | str | None) -> str:
    if not ns:
        return ""
    try:
        ms = int(ns) // 1_000_000
        dt = datetime.fromtimestamp(ms / 1000).astimezone()
        return dt.strftime("%Y-%b-%d %I:%M:%S %p %Z")
    except Exception:
        return str(ns)


def fetch_monitors(customer_id: str, domain: str, token: str) -> list[dict]:
    host = f"{customer_id}.{domain}.observeinc.com" if domain else f"{customer_id}.observeinc.com"
    url = f"https://{host}/v1/monitors"
    headers = {
        "Authorization": f"Bearer {customer_id} {token}",
        "Content-Type": "application/json",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def monitors_to_df(monitors: list[dict]) -> pd.DataFrame:
    rows = []
    for m in monitors:
        rows.append({
            "Name": m.get("name", ""),
            "Monitor ID": m.get("id", ""),
            "Description": m.get("description", ""),
            "Monitor Type": m.get("ruleKind", ""),
            "Status": "Disabled" if m.get("disabled") else "Enabled",
            "Last Modified": nano_to_datetime(m.get("monitorVersion")),
        })
    return pd.DataFrame(rows)


st.subheader("Export Monitor List")
st.caption("Fetches all monitors via the Observe v1 API: `GET /v1/monitors`")

with st.form("credentials_form"):
    col1, col2, col3 = st.columns([1, 0.5, 2])
    with col1:
        customer_id = st.text_input("Customer ID", placeholder="1234567890")
    with col2:
        domain = st.text_input("Domain (optional)", placeholder="abc")
    with col3:
        token = st.text_input("Bearer Token", placeholder="Paste Observe token here", type="password")
    submitted = st.form_submit_button("List Monitors", type="primary")

if submitted:
    if not customer_id or not token:
        st.error("Customer ID and Bearer Token are required.")
    else:
        with st.spinner("Fetching monitors..."):
            try:
                monitors = fetch_monitors(customer_id.strip(), domain.strip(), token.strip())
                st.session_state["monitors_df"] = monitors_to_df(monitors)
                st.session_state["monitors_error"] = None
            except requests.HTTPError as e:
                st.session_state["monitors_df"] = None
                st.session_state["monitors_error"] = f"HTTP {e.response.status_code}: {e.response.text}"
            except Exception as e:
                st.session_state["monitors_df"] = None
                st.session_state["monitors_error"] = str(e)

if st.session_state.get("monitors_error"):
    st.error(st.session_state["monitors_error"])

if st.session_state.get("monitors_df") is not None:
    df: pd.DataFrame = st.session_state["monitors_df"]

    if df.empty:
        st.info("No monitors found.")
    else:
        st.caption(f"{len(df)} result{'s' if len(df) != 1 else ''}")

        st.dataframe(
            df,
            hide_index=True,
            column_config={
                "Status": st.column_config.TextColumn(
                    "Status",
                    help="Whether the monitor is enabled or disabled",
                ),
            },
        )
