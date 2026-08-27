import csv
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
import yaml

_ACTION_ORDER = {"Email": 0, "Webhook": 1, "PagerDuty": 2, "Slack": 3}
_DETAIL_BATCH_SIZE = 500
_DETAIL_BATCH_WORKERS = 20
_DETAIL_BATCH_PAUSE_SECONDS = 30


def _literal_representer(dumper: yaml.Dumper, data: str):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, _literal_representer)


def _host(customer_id: str, domain: str) -> str:
    return f"{customer_id}.{domain}.observeinc.com" if domain else f"{customer_id}.observeinc.com"


def _headers(customer_id: str, token: str) -> dict:
    return {
        "Authorization": f"Bearer {customer_id} {token}",
        "Content-Type": "application/json",
    }


def nano_to_datetime(ns: int | str | None) -> str:
    if not ns:
        return ""
    try:
        ms = int(ns) // 1_000_000
        dt = datetime.fromtimestamp(ms / 1000).astimezone()
        return dt.strftime("%Y-%b-%d %I:%M:%S %p %Z")
    except Exception:
        return str(ns)


def fetch_monitor_list(customer_id: str, domain: str, token: str) -> list[dict]:
    url = f"https://{_host(customer_id, domain)}/v1/monitors"
    resp = requests.get(url, headers=_headers(customer_id, token), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def fetch_monitor_detail(customer_id: str, domain: str, token: str, monitor_id: str) -> dict:
    url = f"https://{_host(customer_id, domain)}/v1/monitors/{monitor_id}"
    resp = requests.get(url, headers=_headers(customer_id, token), timeout=30)
    resp.raise_for_status()
    return resp.json()


def sort_action_rules(rules: list) -> list:
    return sorted(rules, key=lambda r: _ACTION_ORDER.get(
        (r.get("definition") or {}).get("type", ""), 4
    ))


def action_rule_icon(rule: dict) -> tuple[str, str]:
    defn = rule.get("definition") or {}
    action_type = defn.get("type", "")
    if action_type == "PagerDuty":
        url = (defn.get("webhook") or {}).get("url", "")
        return "smartphone", url or "PagerDuty"
    elif action_type == "Email":
        addrs = (defn.get("email") or {}).get("addresses", [])
        return "mail", ", ".join(addrs) if addrs else "Email"
    elif action_type == "Webhook":
        url = (defn.get("webhook") or {}).get("url", "")
        return "webhook", url or "Webhook"
    elif action_type == "Slack":
        url = (defn.get("webhook") or {}).get("url", "")
        return "chat", url or "Slack"
    else:
        url = (defn.get("webhook") or {}).get("url", "")
        return "chat", url or defn.get("name") or action_type or "Action"


def extract_dataset_ids(detail: dict | None) -> list[str]:
    if not detail:
        return []
    stages = ((detail.get("definition") or {}).get("inputQuery") or {}).get("stages") or []
    seen: set[str] = set()
    ids: list[str] = []
    for stage in stages:
        inputs = stage.get("input")
        if isinstance(inputs, dict):
            inputs = [inputs]
        if not isinstance(inputs, list):
            continue
        for inp in inputs:
            ds_id = (inp or {}).get("datasetId")
            if ds_id and ds_id not in seen:
                seen.add(ds_id)
                ids.append(ds_id)
    return ids


def strip_nulls(obj):
    if isinstance(obj, list):
        return [strip_nulls(v) for v in obj]
    if isinstance(obj, dict):
        return {k: strip_nulls(v) for k, v in obj.items() if v is not None}
    return obj


def clean_definition(defn: dict) -> dict:
    defn = dict(defn)
    defn.pop("layout", None)
    if "inputQuery" in defn:
        iq = dict(defn["inputQuery"])
        iq.pop("layout", None)
        if "stages" in iq:
            cleaned = []
            for stage in iq["stages"]:
                stage = dict(stage)
                stage.pop("layout", None)
                if isinstance(stage.get("input"), list):
                    stage["input"] = stage["input"][0]
                if isinstance(stage.get("input"), dict):
                    inp = dict(stage["input"])
                    inp.pop("datasetPath", None)
                    inp.pop("stageId", None)
                    stage["input"] = inp
                cleaned.append(stage)
            iq["stages"] = cleaned
        defn["inputQuery"] = iq
    return defn


def _transform_action_rule(rule: dict) -> dict:
    out = {}
    if "definition" in rule:
        d = strip_nulls(dict(rule["definition"]))
        d.pop("actionId", None)
        if not d.get("name") and d.get("type"):
            t = d["type"]
            if t == "Email" and d.get("email"):
                addrs = d["email"].get("addresses", [])
                d["name"] = f"Email {addrs[0] if addrs else 'action'}"
            elif t == "Webhook":
                d["name"] = "Webhook action"
            else:
                d["name"] = f"{t} action"
        out["definition"] = d
    elif "actionId" in rule:
        out["actionId"] = rule["actionId"]
    for k in ("levels", "conditions", "sendEndNotifications", "sendRemindersInterval"):
        if rule.get(k) is not None:
            out[k] = rule[k]
    return out


def transform_for_create(data: dict) -> dict:
    body = strip_nulls(json.loads(json.dumps(data)))
    for k in ("id", "monitorVersion", "effectiveScheduling"):
        body.pop(k, None)
    body["name"] = (body.get("name") or "") + " (auto-generated)"
    if "definition" in body:
        body["definition"] = clean_definition(body["definition"])
    if isinstance(body.get("actionRules"), list):
        body["actionRules"] = [_transform_action_rule(r) for r in body["actionRules"]]
    ordered = {}
    for k in ("name", "description", "disabled", "ruleKind", "definition", "actionRules"):
        if k in body:
            ordered[k] = body.pop(k)
    ordered.update(body)
    return ordered


def build_curl_cmd(post_body: dict, host: str, customer_id: str, token: str) -> str:
    body_json = json.dumps(post_body, indent=2).replace("'", "'\\''")
    return (
        f"curl https://{host}/v1/monitors \\\n"
        f"  --request POST \\\n"
        f"  --header 'Content-Type: application/json' \\\n"
        f"  --header 'Authorization: Bearer {customer_id} {token}' \\\n"
        f"  --data '{body_json}'"
    )


def build_ps_cmd(post_body: dict, host: str, customer_id: str, token: str) -> str:
    body_json = json.dumps(post_body, indent=2).replace("`", "``").replace("'", "''")
    return (
        f"Invoke-RestMethod `\n"
        f"  -Uri 'https://{host}/v1/monitors' `\n"
        f"  -Method Post `\n"
        f"  -Headers @{{\n"
        f"    'Content-Type' = 'application/json'\n"
        f"    'Authorization' = 'Bearer {customer_id} {token}'\n"
        f"  }} `\n"
        f"  -Body '{body_json}'"
    )


def monitors_to_df(monitors: list[dict]) -> pd.DataFrame:
    rows = []
    for m in monitors:
        rows.append({
            "Name": m.get("name", ""),
            "Monitor ID": m.get("id", ""),
            "Description": m.get("description", ""),
            "Type": m.get("ruleKind", ""),
            "Status": "Disabled" if m.get("disabled") else "Enabled",
            "Last Modified": nano_to_datetime(m.get("monitorVersion")),
        })
    return pd.DataFrame(rows)


def _esc(s) -> str:
    return (str(s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def build_yaml(details_map: dict[str, dict | None]) -> str:
    records = [v for v in details_map.values() if v is not None]
    stream = io.StringIO()
    yaml.dump_all(records, stream, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return stream.getvalue()


def build_enriched_table_html(
    monitors: list[dict],
    details_map: dict[str, dict | None],
    customer_id: str,
    domain: str,
    token: str,
) -> str:
    host = _host(customer_id, domain)
    post_data: dict[str, dict] = {}
    rows_html: list[str] = []

    for m in monitors:
        mid = m.get("id", "")
        detail = details_map.get(mid)
        action_rules = (detail or {}).get("actionRules") or []
        dataset_ids = extract_dataset_ids(detail)
        dataset_ids_html = (
            "<br>".join(f"<span class='mono dim'>{_esc(d)}</span>" for d in dataset_ids)
            if dataset_ids else "<span class='dim'>—</span>"
        )

        # Build POST commands and stash in JS data object
        if detail:
            post_body = transform_for_create(detail)
            post_data[mid] = {
                "curl": build_curl_cmd(post_body, host, customer_id, token),
                "ps":   build_ps_cmd(post_body, host, customer_id, token),
            }

        # Destination icons with title tooltip
        dest_parts = []
        for rule in sort_action_rules(action_rules):
            icon_name, tooltip = action_rule_icon(rule)
            tip = (_esc(tooltip))
            dest_parts.append(
                f'<span class="mat-icon" title="{tip}">{icon_name}</span>'
            )
        dest_html = "".join(dest_parts) if dest_parts else "<span class='dim'>—</span>"

        # Monitor type badge — CSS class drives light/dark colors via media query
        rule_kind = m.get("ruleKind", "")
        type_class = rule_kind.lower() if rule_kind in ("Promote", "Anomaly", "Count", "Threshold") else "other"
        type_html = f'<span class="type-badge {type_class}">{_esc(rule_kind)}</span>'

        # Status
        disabled = m.get("disabled", False)
        status_class = "disabled" if disabled else "enabled"
        status_html = f'<span class="status-badge {status_class}">{"Disabled" if disabled else "Enabled"}</span>'

        # Timestamp — color only the TZ abbreviation
        ts_full = nano_to_datetime(m.get("monitorVersion"))
        if ts_full:
            parts = ts_full.rsplit(" ", 1)
            ts_html = (
                f"{_esc(parts[0])} <span class='tz-badge'>{_esc(parts[1])}</span>"
                if len(parts) == 2 else _esc(ts_full)
            )
        else:
            ts_html = ""

        # POST column
        mid_esc = _esc(mid)
        if detail:
            post_html = (
                f'<button class="btn-curl" data-mid="{mid_esc}">Copy cURL</button>'
                f'<button class="btn-ps"   data-mid="{mid_esc}">Copy PowerShell</button>'
            )
        else:
            post_html = '<span class="dim sm">fetch failed</span>'

        rows_html.append(
            f"<tr>"
            f"<td>{_esc(m.get('name', ''))}</td>"
            f"<td class='mono dim'>{_esc(mid)}</td>"
            f"<td class='dim sm'>{_esc(m.get('description', ''))}</td>"
            f"<td>{dataset_ids_html}</td>"
            f"<td>{type_html}</td>"
            f"<td>{status_html}</td>"
            f"<td class='sm nowrap'>{ts_html}</td>"
            f"<td class='dest'>{dest_html}</td>"
            f"<td><div class='post-btns'>{post_html}</div></td>"
            f"</tr>"
        )

    headers = ["Name", "Monitor ID", "Description", "Dataset ID(s)", "Type", "Status", "Last Modified", "Destination", "POST"]
    thead = "".join(f"<th>{h}</th>" for h in headers)
    tbody = "".join(rows_html)
    post_data_js = json.dumps(post_data)

    return f"""<!DOCTYPE html>
<html><head>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20,400,0,0" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          font-size: 0.875rem; background: #fff; color: #24292f; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; padding: 8px 12px; border-bottom: 2px solid #e0e0e0;
        font-size: 0.75rem; font-weight: 600; color: #57606a; white-space: nowrap; }}
  td {{ padding: 7px 12px; border-bottom: 1px solid #f0f0f0; vertical-align: middle; }}
  tr:hover td {{ background: #f6f8fa; }}
  .mono   {{ font-family: monospace; font-size: 0.82em; }}
  .dim    {{ opacity: 0.55; }}
  .sm     {{ font-size: 0.85em; }}
  .nowrap {{ white-space: nowrap; }}
  .mat-icon {{
    font-family: 'Material Symbols Rounded', sans-serif;
    font-feature-settings: "liga"; -webkit-font-feature-settings: "liga";
    font-size: 1.1rem; line-height: 1; cursor: help; vertical-align: middle;
  }}
  .tz-badge {{ background:#fff3e0; color:#e65100;
    padding:1px 5px; border-radius:10px; font-size:0.78em; font-weight:600; }}
  .type-badge, .status-badge {{
    padding: 2px 8px; border-radius: 10px;
    font-size: 0.78em; font-weight: 500; white-space: nowrap;
  }}
  .type-badge.promote   {{ background:#dbeafe; color:#1d4ed8; }}
  .type-badge.anomaly   {{ background:#ede9fe; color:#6d28d9; }}
  .type-badge.count     {{ background:#fce7f3; color:#9d174d; }}
  .type-badge.threshold {{ background:#ccfbf1; color:#0f766e; }}
  .type-badge.other     {{ background:#f1f5f9; color:#475569; }}
  .status-badge.enabled  {{ background:#dcfce7; color:#15803d; }}
  .status-badge.disabled {{ background:#fee2e2; color:#b91c1c; }}
  .post-btns {{ display: flex; gap: 5px; align-items: center; flex-wrap: nowrap; }}
  .btn-curl, .btn-ps {{
    border: none; border-radius: 5px;
    padding: 3px 9px; font-size: 0.75rem; font-weight: 500;
    cursor: pointer; transition: background 0.15s; white-space: nowrap;
  }}
  .btn-curl {{ background:#dbeafe; color:#1d4ed8; }}
  .btn-curl:hover {{ background:#bfdbfe; }}
  .btn-ps   {{ background:#ede9fe; color:#6d28d9; }}
  .btn-ps:hover   {{ background:#ddd6fe; }}
  .btn-curl.ok, .btn-ps.ok   {{ background:#dcfce7; color:#15803d; }}
  .btn-curl.err, .btn-ps.err {{ background:#fee2e2; color:#b91c1c; }}

  /* \u2500\u2500 Dark mode (applied via JS reading the parent Streamlit page) \u2500\u2500 */
  [data-theme="dark"] body {{ background:#0d1117; color:#c9d1d9; }}
  [data-theme="dark"] th   {{ color:#8b949e; border-bottom-color:#30363d; }}
  [data-theme="dark"] td   {{ border-bottom-color:#21262d; }}
  [data-theme="dark"] tr:hover td {{ background:#161b22; }}
  [data-theme="dark"] .dim {{ opacity: 0.65; }}
  [data-theme="dark"] .tz-badge {{ background:#2b1e0a; color:#e3a44a; }}
  [data-theme="dark"] .type-badge.promote   {{ background:#1a2332; color:#79c0ff; }}
  [data-theme="dark"] .type-badge.anomaly   {{ background:#271a32; color:#d2a8ff; }}
  [data-theme="dark"] .type-badge.count     {{ background:#2b1028; color:#f778ba; }}
  [data-theme="dark"] .type-badge.threshold {{ background:#0d2626; color:#2dd4bf; }}
  [data-theme="dark"] .type-badge.other     {{ background:#30363d; color:#8b949e; }}
  [data-theme="dark"] .status-badge.enabled  {{ background:#0d2818; color:#3fb950; }}
  [data-theme="dark"] .status-badge.disabled {{ background:#2d1115; color:#f85149; }}
  [data-theme="dark"] .btn-curl {{ background:#1a2332; color:#79c0ff; }}
  [data-theme="dark"] .btn-curl:hover {{ background:#1f3548; }}
  [data-theme="dark"] .btn-ps   {{ background:#271a32; color:#d2a8ff; }}
  [data-theme="dark"] .btn-ps:hover   {{ background:#3a2448; }}
  [data-theme="dark"] .btn-curl.ok, [data-theme="dark"] .btn-ps.ok  {{ background:#0d2818; color:#3fb950; }}
  [data-theme="dark"] .btn-curl.err,[data-theme="dark"] .btn-ps.err {{ background:#2d1115; color:#f85149; }}
</style>
</head><body>
<table>
  <thead><tr>{thead}</tr></thead>
  <tbody>{tbody}</tbody>
</table>
<script>
(function() {{
  function isDarkPage() {{
    try {{
      var el = window.parent.document.querySelector('[data-testid="stApp"]')
               || window.parent.document.body;
      var bg = window.parent.getComputedStyle(el).backgroundColor;
      var m = bg.match(/[0-9.]+/g);
      if (m && m.length >= 3) return (+m[0] + +m[1] + +m[2]) / 3 < 128;
    }} catch(e) {{}}
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }}
  if (isDarkPage()) document.documentElement.setAttribute('data-theme', 'dark');
}})();

const POST_DATA = {post_data_js};

function copyText(text) {{
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    return navigator.clipboard.writeText(text).catch(function() {{ return fallback(text); }});
  }}
  return fallback(text);
}}

function fallback(text) {{
  return new Promise(function(resolve, reject) {{
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0;width:1px;height:1px';
    document.body.appendChild(ta);
    ta.focus(); ta.select();
    document.execCommand('copy') ? resolve() : reject();
    document.body.removeChild(ta);
  }});
}}

function flash(btn, ok) {{
  var orig = btn.textContent;
  btn.classList.add(ok ? 'ok' : 'err');
  btn.textContent = ok ? 'Copied!' : 'Failed';
  setTimeout(function() {{ btn.classList.remove('ok','err'); btn.textContent = orig; }}, 1500);
}}

document.addEventListener('click', function(e) {{
  var btn = e.target;
  var mid = btn.getAttribute('data-mid');
  if (!mid) return;
  var d = POST_DATA[mid];
  if (!d) return;
  var text = btn.classList.contains('btn-curl') ? d.curl : (btn.classList.contains('btn-ps') ? d.ps : null);
  if (!text) return;
  copyText(text).then(function() {{ flash(btn, true); }}).catch(function() {{ flash(btn, false); }});
}});
</script>
</body></html>"""


def build_csv(monitors: list[dict], details_map: dict[str, dict | None]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Name", "Monitor ID", "Description", "Dataset ID(s)", "Type", "Status", "Last Modified", "Destinations", "GET Response (JSON)"])
    for m in monitors:
        mid = m.get("id", "")
        detail = details_map.get(mid)
        action_rules = (detail or {}).get("actionRules") or []
        dests = [
            (r.get("definition") or {}).get("type", "Action")
            for r in sort_action_rules(action_rules)
        ]
        writer.writerow([
            m.get("name", ""),
            mid,
            m.get("description", ""),
            ", ".join(extract_dataset_ids(detail)),
            m.get("ruleKind", ""),
            "Disabled" if m.get("disabled") else "Enabled",
            nano_to_datetime(m.get("monitorVersion")),
            ", ".join(dests),
            json.dumps(detail) if detail else "",
        ])
    return out.getvalue()


# ── UI ────────────────────────────────────────────────────────────────────────

st.subheader("Export All Monitor Details")
st.caption(
    "Two-step export: fetch the monitor list, then retrieve full details for each. "
    "Uses `GET /v1/monitors` and `GET /v1/monitors/{id}`"
)

with st.form("all_mon_form"):
    col1, col2, col3 = st.columns([1, 0.5, 2])
    with col1:
        customer_id = st.text_input("Customer ID", placeholder="1234567890")
    with col2:
        domain = st.text_input("Domain (optional)", placeholder="abc")
    with col3:
        token = st.text_input("Bearer Token", placeholder="Paste Observe token here", type="password")
    submitted = st.form_submit_button("Fetch Monitor List", type="primary")

if submitted:
    if not customer_id or not token:
        st.error("Customer ID and Bearer Token are required.")
    else:
        with st.spinner("Fetching monitor list…"):
            try:
                monitors = fetch_monitor_list(customer_id.strip(), domain.strip(), token.strip())
                st.session_state["all_mon_list"] = monitors
                st.session_state["all_mon_creds"] = (customer_id.strip(), domain.strip(), token.strip())
                st.session_state["all_mon_details"] = None
                st.session_state["all_mon_list_error"] = None
                st.session_state["all_mon_details_error"] = None
            except requests.HTTPError as e:
                st.session_state["all_mon_list"] = None
                st.session_state["all_mon_list_error"] = f"HTTP {e.response.status_code}: {e.response.text}"
            except Exception as e:
                st.session_state["all_mon_list"] = None
                st.session_state["all_mon_list_error"] = str(e)

if st.session_state.get("all_mon_list_error"):
    st.error(st.session_state["all_mon_list_error"])

if st.session_state.get("all_mon_list") is not None:
    monitors: list[dict] = st.session_state["all_mon_list"]
    cid, dom, tok = st.session_state["all_mon_creds"]
    details_ready = st.session_state.get("all_mon_details") is not None

    if not monitors:
        st.info("No monitors found.")
    else:
        btn_col, cnt_col = st.columns([1, 5])
        with btn_col:
            fetch_details_clicked = st.button(
                "Fetch All Details",
                icon=":material/sync:",
                type="secondary" if details_ready else "primary",
            )
        with cnt_col:
            st.caption(f"{len(monitors)} monitor{'s' if len(monitors) != 1 else ''}")

        if not details_ready:
            st.dataframe(monitors_to_df(monitors), hide_index=True)

        if fetch_details_clicked:
            details_map: dict[str, dict | None] = {}
            total = len(monitors)
            progress_bar = st.progress(0, text="Starting…")
            done = 0
            batches = [
                monitors[i:i + _DETAIL_BATCH_SIZE]
                for i in range(0, total, _DETAIL_BATCH_SIZE)
            ]
            for batch_idx, batch in enumerate(batches):
                with ThreadPoolExecutor(max_workers=_DETAIL_BATCH_WORKERS) as pool:
                    futures = {
                        pool.submit(fetch_monitor_detail, cid, dom, tok, m.get("id", "")): m
                        for m in batch
                    }
                    for future in as_completed(futures):
                        m = futures[future]
                        mid = m.get("id", "")
                        try:
                            details_map[mid] = future.result()
                        except Exception:
                            details_map[mid] = None
                        done += 1
                        progress_bar.progress(done / total, text=f"{done}/{total} fetched…")
                is_last_batch = batch_idx == len(batches) - 1
                if not is_last_batch:
                    for remaining in range(_DETAIL_BATCH_PAUSE_SECONDS, 0, -1):
                        progress_bar.progress(
                            done / total,
                            text=f"{done}/{total} fetched — pausing {remaining}s before next batch…",
                        )
                        time.sleep(1)
            progress_bar.progress(1.0, text="Done!")
            st.session_state["all_mon_details"] = details_map
            failed = sum(1 for v in details_map.values() if v is None)
            st.session_state["all_mon_details_error"] = (
                f"{failed} monitor(s) failed to fetch details." if failed else None
            )
            st.rerun()

if st.session_state.get("all_mon_details_error"):
    st.warning(st.session_state["all_mon_details_error"])

if st.session_state.get("all_mon_details") is not None:
    monitors = st.session_state.get("all_mon_list", [])
    details_map = st.session_state["all_mon_details"]
    cid, dom, tok = st.session_state["all_mon_creds"]
    failed = sum(1 for v in details_map.values() if v is None)

    csv_col, yaml_col, cnt_col = st.columns([1, 1, 4])
    with csv_col:
        st.download_button(
            "Download CSV",
            build_csv(monitors, details_map),
            file_name="observe_all_monitor_details.csv",
            mime="text/csv",
            icon=":material/download:",
        )
    with yaml_col:
        st.download_button(
            "Download YAML",
            build_yaml(details_map),
            file_name="observe_all_monitor_details.yaml",
            mime="text/yaml",
            icon=":material/download:",
        )
    with cnt_col:
        label = (
            f"{len(monitors) - failed} fetched, {failed} failed"
            if failed else
            f"{len(monitors)} monitor{'s' if len(monitors) != 1 else ''}"
        )
        st.caption(label)

    table_html = build_enriched_table_html(monitors, details_map, cid, dom, tok)
    table_height = min(700, max(250, len(monitors) * 40 + 80))
    st.iframe(table_html, height=table_height)
