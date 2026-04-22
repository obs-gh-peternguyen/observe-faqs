import streamlit as st
import requests
import pandas as pd
from datetime import datetime


def get_nested(obj: dict, dotted_key: str):
    for k in dotted_key.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def iso_to_str(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%Y-%b-%d %I:%M:%S %p %Z")
    except Exception:
        return str(iso)


def fetch_datasets(customer_id: str, domain: str, token: str) -> list[dict]:
    host = f"{customer_id}.{domain}.observeinc.com" if domain else f"{customer_id}.observeinc.com"
    url = f"https://{host}/v1/dataset"
    headers = {
        "Authorization": f"Bearer {customer_id} {token}",
        "Content-Type": "application/json",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    return body.get("data", []) if isinstance(body, dict) else []


def datasets_to_df(datasets: list[dict]) -> pd.DataFrame:
    rows = []
    for d in datasets:
        pk = get_nested(d, "config.primaryKey")
        pk_str = ", ".join(pk) if isinstance(pk, list) else (pk or "")
        rows.append({
            "ID": get_nested(d, "meta.id") or "",
            "Workspace ID": get_nested(d, "meta.workspaceId") or "",
            "Customer ID": get_nested(d, "meta.customerId") or "",
            "Name": get_nested(d, "config.name") or "",
            "Label Field": get_nested(d, "config.labelField") or "",
            "Primary Key": pk_str,
            "URL Path": get_nested(d, "state.urlPath") or "",
            "Kind": get_nested(d, "state.kind") or "",
            "Created By": get_nested(d, "state.createdBy") or "",
            "Created Date": iso_to_str(get_nested(d, "state.createdDate")),
            "Updated By": get_nested(d, "state.updatedBy") or "",
            "Updated Date": iso_to_str(get_nested(d, "state.updatedDate")),
        })
    return pd.DataFrame(rows)


st.subheader("Export Dataset (Legacy)")
st.caption("Fetches all dataset via the Observe v1 API: `GET /v1/dataset` (legacy)")

with st.form("credentials_form"):
    col1, col2, col3 = st.columns([1, 0.5, 2])
    with col1:
        customer_id = st.text_input("Customer ID", placeholder="1234567890")
    with col2:
        domain = st.text_input("Domain (optional)", placeholder="abc")
    with col3:
        token = st.text_input("Bearer Token", placeholder="Paste Observe token here", type="password")
    submitted = st.form_submit_button("List Datasets", type="primary")

if submitted:
    if not customer_id or not token:
        st.error("Customer ID and Bearer Token are required.")
    else:
        with st.spinner("Fetching datasets…"):
            try:
                datasets = fetch_datasets(customer_id.strip(), domain.strip(), token.strip())
                st.session_state["datasets_df"] = datasets_to_df(datasets)
                st.session_state["datasets_error"] = None
            except requests.HTTPError as e:
                st.session_state["datasets_df"] = None
                st.session_state["datasets_error"] = f"HTTP {e.response.status_code}: {e.response.text}"
            except Exception as e:
                st.session_state["datasets_df"] = None
                st.session_state["datasets_error"] = str(e)

if st.session_state.get("datasets_error"):
    st.error(st.session_state["datasets_error"])

if st.session_state.get("datasets_df") is not None:
    df: pd.DataFrame = st.session_state["datasets_df"]

    if df.empty:
        st.info("No datasets found.")
    else:
        st.caption(f"{len(df)} result{'s' if len(df) != 1 else ''}")

        st.dataframe(df, hide_index=True)
