import io
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import streamlit as st
import yaml

GRAPHQL_QUERY = """
query listDatasetsWithDetail {
    datasets: projects {
        datasets {
            id
            workspaceId
            name
            kind
            description
            iconUrl
            managedById
            transform {
                current {
                    query {
                        outputStage
                        stages {
                            id
                            pipeline
                            input {
                                inputName
                                datasetId
                                datasetPath
                                stageId
                            }
                        }
                    }
                }
            }
            correlationTagMappings {
                tag
                path {
                    column
                    path
                }
            }
        }
    }
}
"""


def _host(customer_id: str, domain: str) -> str:
    return f"{customer_id}.{domain}.observeinc.com" if domain else f"{customer_id}.observeinc.com"


def _headers(customer_id: str, token: str) -> dict:
    return {
        "Authorization": f"Bearer {customer_id} {token}",
        "Content-Type": "application/json",
    }


def fetch_datasets_graphql(customer_id: str, domain: str, token: str) -> list[dict]:
    url = f"https://{_host(customer_id, domain)}/v1/meta"
    resp = requests.post(url, json={"query": GRAPHQL_QUERY}, headers=_headers(customer_id, token), timeout=60)
    resp.raise_for_status()
    body = resp.json()
    if "errors" in body:
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    datasets: list[dict] = []
    for project in body.get("data", {}).get("datasets", []):
        datasets.extend(project.get("datasets", []))
    return datasets


def fetch_rest_state(customer_id: str, domain: str, token: str, dataset_id: str) -> dict:
    url = f"https://{_host(customer_id, domain)}/v1/dataset/{dataset_id}"
    try:
        resp = requests.get(url, headers=_headers(customer_id, token), timeout=30)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        data = resp.json().get("data", {})
        state = data.get("state", {})
        cfg = data.get("config", {})
        return {**state, "config_name": cfg.get("name"), "acceleration_disabled": cfg.get("accelerationDisabled")}
    except Exception:
        return {}


def fetch_all_rest_states(customer_id: str, domain: str, token: str, dataset_ids: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {
            pool.submit(fetch_rest_state, customer_id, domain, token, ds_id): ds_id
            for ds_id in dataset_ids
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


def build_sources(stages: list[dict], id_to_name: dict[str, str]) -> list[dict]:
    sources: list[dict] = []
    seen: set[str] = set()
    for stage in stages:
        for inp in stage.get("input", []) or []:
            ds_id = inp.get("datasetId")
            ds_path = inp.get("datasetPath")
            stage_id = inp.get("stageId")
            ref = ds_id or ds_path or stage_id
            if ref and ref not in seen:
                seen.add(ref)
                name = id_to_name.get(ds_id) if ds_id else (ds_path or None)
                entry: dict = {"id": ref}
                if name and name != ref:
                    entry["name"] = name
                sources.append(entry)
    return sources


def build_oql(stages: list[dict], output_stage: str | None) -> str | None:
    if not stages:
        return None
    if len(stages) == 1:
        raw = (stages[0].get("pipeline") or "").replace("\r\n", "\n").replace("\r", "\n")
        return "\n".join(line.rstrip() for line in raw.split("\n")).strip() or None
    parts: list[str] = []
    for stage in stages:
        alias = stage.get("id") or ""
        raw = (stage.get("pipeline") or "").replace("\r\n", "\n").replace("\r", "\n")
        pipeline = "\n".join(line.rstrip() for line in raw.split("\n")).strip()
        if alias:
            parts.append(f"# stage: {alias}")
        if pipeline:
            parts.append(pipeline)
    return "\n".join(parts).strip() or None


def build_correlation_tags(mappings: list[dict]) -> list[str]:
    tags = [m.get("tag") for m in (mappings or []) if m.get("tag")]
    return sorted(set(tags))


def dataset_to_dict(ds: dict, rest: dict, id_to_name: dict[str, str]) -> dict:
    query = ((ds.get("transform") or {}).get("current") or {}).get("query") or {}
    stages = query.get("stages") or []
    record = {
        "name": ds.get("name") or "",
        "id": ds.get("id") or "",
        "kind": ds.get("kind") or None,
        "description": ds.get("description") or None,
        "icon_url": ds.get("iconUrl") or None,
        "workspace_id": ds.get("workspaceId") or None,
        "config_name": rest.get("config_name") or None,
        "acceleration_disabled": rest.get("acceleration_disabled"),
        "created_by": rest.get("createdBy") or None,
        "created_date": rest.get("createdDate") or None,
        "updated_by": rest.get("updatedBy") or None,
        "updated_date": rest.get("updatedDate") or None,
        "sources": build_sources(stages, id_to_name) or None,
        "correlation_tags": build_correlation_tags(ds.get("correlationTagMappings") or []) or None,
        "interfaces": [i["path"] for i in (rest.get("interfaces") or []) if i.get("path")] or None,
        "columns": rest.get("columns") or None,
        "oql": build_oql(stages, query.get("outputStage")),
    }
    return {k: v for k, v in record.items() if v is not None}


def _literal_representer(dumper: yaml.Dumper, data: str):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, _literal_representer)


def build_combined_yaml(datasets: list[dict], rest_states: dict[str, dict], id_to_name: dict[str, str]) -> tuple[str, int]:
    records = []
    for ds in datasets:
        if ds.get("managedById"):
            continue
        records.append(dataset_to_dict(ds, rest_states.get(ds.get("id") or "", {}), id_to_name))
    stream = io.StringIO()
    yaml.dump_all(records, stream, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return stream.getvalue(), len(records)


st.subheader("Export Dataset Details (Unsupported)")
st.caption("UNSUPPORTED: Fetches all dataset definitions via the Observe GraphQL and REST APIs: `POST /v1/meta` · `GET /v1/dataset/{id}`")

with st.form("dataset_details_form"):
    col1, col2, col3 = st.columns([1, 0.5, 2])
    with col1:
        customer_id = st.text_input("Customer ID", placeholder="1234567890")
    with col2:
        domain = st.text_input("Domain (optional)", placeholder="abc")
    with col3:
        token = st.text_input("Bearer Token", placeholder="Paste Observe token here", type="password")
    submitted = st.form_submit_button("Fetch Dataset Details", type="primary")

if submitted:
    if not customer_id or not token:
        st.error("Customer ID and Bearer Token are required.")
    else:
        with st.spinner("Fetching datasets…"):
            try:
                cid, dom, tok = customer_id.strip(), domain.strip(), token.strip()
                datasets = fetch_datasets_graphql(cid, dom, tok)
                id_to_name = {ds["id"]: ds["name"] for ds in datasets if ds.get("id") and ds.get("name")}
                rest_states = fetch_all_rest_states(cid, dom, tok, [ds["id"] for ds in datasets if ds.get("id")])
                yaml_str, count = build_combined_yaml(datasets, rest_states, id_to_name)
                st.session_state["dataset_details_yaml"] = yaml_str
                st.session_state["dataset_details_count"] = count
                st.session_state["dataset_details_error"] = None
            except requests.HTTPError as e:
                st.session_state["dataset_details_yaml"] = None
                st.session_state["dataset_details_error"] = f"HTTP {e.response.status_code}: {e.response.text}"
            except Exception as e:
                st.session_state["dataset_details_yaml"] = None
                st.session_state["dataset_details_error"] = str(e)

if st.session_state.get("dataset_details_error"):
    st.error(st.session_state["dataset_details_error"])

if st.session_state.get("dataset_details_yaml"):
    yaml_str = st.session_state["dataset_details_yaml"]
    count = st.session_state["dataset_details_count"]

    btn_col, result_col = st.columns([1, 5])
    with btn_col:
        st.download_button(
            "Download YAML",
            yaml_str,
            file_name="observe_datasets.yaml",
            mime="text/yaml",
            icon=":material/download:",
        )
    with result_col:
        st.caption(f"{count} dataset{'s' if count != 1 else ''}")
    st.code(yaml_str, language="yaml")
