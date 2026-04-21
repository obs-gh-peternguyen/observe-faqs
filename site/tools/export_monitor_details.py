import json
import streamlit as st
import requests


def fetch_monitor(customer_id: str, domain: str, monitor_id: str, token: str) -> dict:
    host = f"{customer_id}.{domain}.observeinc.com" if domain else f"{customer_id}.observeinc.com"
    url = f"https://{host}/v1/monitors/{monitor_id}"
    headers = {
        "Authorization": f"Bearer {customer_id} {token}",
        "Content-Type": "application/json",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


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
            cleaned_stages = []
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
                cleaned_stages.append(stage)
            iq["stages"] = cleaned_stages
        defn["inputQuery"] = iq
    return defn


def transform_action_rule(rule: dict) -> dict:
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
        body["actionRules"] = [transform_action_rule(r) for r in body["actionRules"]]
    ordered = {}
    for k in ("name", "description", "disabled", "ruleKind", "definition", "actionRules"):
        if k in body:
            ordered[k] = body.pop(k)
    ordered.update(body)
    return ordered


def build_curl(data: dict, customer_id: str, domain: str, token: str) -> str:
    host = f"{customer_id}.{domain}.observeinc.com" if domain else f"{customer_id}.observeinc.com"
    body = transform_for_create(data)
    body_json = json.dumps(body, indent=2).replace("'", "'\\''")
    return (
        f"curl https://{host}/v1/monitors \\\n"
        f"  --request POST \\\n"
        f"  --header 'Content-Type: application/json' \\\n"
        f"  --header 'Authorization: Bearer {customer_id} {token}' \\\n"
        f"  --data '{body_json}'"
    )


_ACTION_ORDER = {"Email": 0, "Webhook": 1, "PagerDuty": 2, "Slack": 3}


def sort_action_rules(rules: list) -> list:
    return sorted(rules, key=lambda r: _ACTION_ORDER.get(
        (r.get("definition") or {}).get("type", ""), 4
    ))


def action_rule_icon_and_tooltip(rule: dict) -> tuple[str, str]:
    defn = rule.get("definition") or {}
    action_type = defn.get("type", "")
    if action_type == "PagerDuty":
        url = (defn.get("webhook") or {}).get("url", "")
        return ":material/smartphone:", url or "PagerDuty"
    elif action_type == "Email":
        addrs = (defn.get("email") or {}).get("addresses", [])
        return ":material/mail:", ", ".join(addrs) if addrs else "Email"
    elif action_type == "Webhook":
        url = (defn.get("webhook") or {}).get("url", "")
        return ":material/webhook:", url or "Webhook"
    elif action_type == "Slack":
        url = (defn.get("webhook") or {}).get("url", "")
        return ":material/chat:", url or "Slack"
    else:
        url = (defn.get("webhook") or {}).get("url", "")
        return ":material/chat:", url or defn.get("name") or action_type or "Action"


st.subheader("Export Monitor Details")
st.caption("Fetches a single monitor by ID and generates a curl command to recreate it: `GET /v1/monitors/{id}`")

with st.form("credentials_form"):
    col1, col2, col3, col4 = st.columns([1, 0.5, 0.5, 2])
    with col1:
        customer_id = st.text_input("Customer ID", placeholder="1234567890")
    with col2:
        domain = st.text_input("Domain (optional)", placeholder="abc")
    with col3:
        monitor_id = st.text_input("Monitor ID", placeholder="12345678")
    with col4:
        token = st.text_input("Bearer Token", placeholder="Paste Observe token here", type="password")
    submitted = st.form_submit_button("Get Monitor", type="primary")

if submitted:
    if not customer_id or not monitor_id or not token:
        st.error("Customer ID, Monitor ID, and Bearer Token are required.")
    else:
        with st.spinner("Fetching monitor…"):
            try:
                data = fetch_monitor(
                    customer_id.strip(), domain.strip(), monitor_id.strip(), token.strip()
                )
                st.session_state["monitor_data"] = data
                st.session_state["monitor_creds"] = (customer_id.strip(), domain.strip(), token.strip())
                st.session_state["monitor_error"] = None
            except requests.HTTPError as e:
                st.session_state["monitor_data"] = None
                st.session_state["monitor_error"] = f"HTTP {e.response.status_code}: {e.response.text}"
            except Exception as e:
                st.session_state["monitor_data"] = None
                st.session_state["monitor_error"] = str(e)

if st.session_state.get("monitor_error"):
    st.error(st.session_state["monitor_error"])

if st.session_state.get("monitor_data") is not None:
    data: dict = st.session_state["monitor_data"]
    cid, dom, tok = st.session_state["monitor_creds"]

    name = data.get("name", "Unknown")
    rule_kind = data.get("ruleKind", "")
    mid = data.get("id", "")
    disabled = data.get("disabled", False)
    action_rules = data.get("actionRules") or []

    st.markdown(f"**{name}**")

    status_label = "disabled" if disabled else "enabled"
    meta_cols = st.columns(4)

    with meta_cols[0]:
        st.caption("Monitor ID")
        st.markdown(f"`{mid}`")
    with meta_cols[1]:
        st.caption("Kind")
        st.markdown(f"`{rule_kind}`")
    with meta_cols[2]:
        st.caption("Status")
        st.markdown(f"`{status_label}`")
    with meta_cols[3]:
        st.caption("Action Rules")
        if action_rules:
            sorted_rules = sort_action_rules(action_rules)
            with st.container(horizontal=True):
                for i, rule in enumerate(sorted_rules):
                    icon, tooltip = action_rule_icon_and_tooltip(rule)
                    st.button(" ", icon=icon, help=tooltip, key=f"action_rule_{mid}_{i}")
        else:
            st.markdown("—")

    tab_json, tab_curl = st.tabs(["GET /v1/monitors/{id}", "POST /v1/monitors (recreate)"])

    with tab_json:
        st.code(json.dumps(data, indent=2), language="json")

    with tab_curl:
        curl_cmd = build_curl(data, cid, dom, tok)
        st.code(curl_cmd, language="bash")
