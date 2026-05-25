import gzip

import requests
import streamlit as st

CONTENT_TYPES = [
    "application/json",
    "application/x-ndjson",
    "application/xml",
    "application/msgpack",
    "text/csv",
    "application/x-csv",
    "text/plain",
]


def build_url(customer_id: str, domain: str) -> str:
    subdomain = domain.strip() if domain.strip() else "collect"
    return f"https://{customer_id}.{subdomain}.observeinc.com/v1/http"


def post_to_observe(url: str, token: str, content_type: str, data: bytes) -> requests.Response:
    compressed = gzip.compress(data)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
        "Content-Encoding": "gzip",
    }
    resp = requests.post(url, headers=headers, data=compressed, timeout=60)
    resp.raise_for_status()
    return resp


st.subheader("Import File")
st.caption("Send data to Observe via HTTP ingest endpoint: `POST /v1/http`")

with st.container(border=True):
    col1, col2, col3 = st.columns([1, 0.5, 2])
    with col1:
        customer_id = st.text_input("Customer ID", placeholder="1234567890")
    with col2:
        domain = st.text_input("Domain (optional)", placeholder="collect", help="Defaults to 'collect' if left blank")
    with col3:
        token = st.text_input("Bearer Token", placeholder="Paste Observe token here", type="password")
    content_type = st.selectbox("Content Type", CONTENT_TYPES)

input_method = st.radio("Input Method", ["File Upload", "URL", "Paste Contents"], horizontal=True)

uploaded_file = None
url_input = None
pasted_text = None

if input_method == "File Upload":
    uploaded_file = st.file_uploader("Select a file")
elif input_method == "URL":
    url_input = st.text_input("Public File URL", placeholder="https://example.com/data.json")
else:
    pasted_text = st.text_area("Paste data here", height=300, placeholder="Paste your data here...")

if st.button("Submit", type="primary"):
    if not customer_id or not token:
        st.error("Customer ID and Bearer Token are required.")
        st.stop()

    data: bytes | None = None
    source_label = ""

    try:
        if input_method == "File Upload":
            if uploaded_file is None:
                st.error("Please select a file to upload.")
                st.stop()
            data = uploaded_file.read()
            source_label = uploaded_file.name

        elif input_method == "URL":
            if not url_input or not url_input.strip():
                st.error("Please enter a URL.")
                st.stop()
            with st.spinner("Fetching file from URL..."):
                fetch_resp = requests.get(url_input.strip(), timeout=60)
                fetch_resp.raise_for_status()
                data = fetch_resp.content
            source_label = url_input.strip()

        else:
            if not pasted_text or not pasted_text.strip():
                st.error("Please paste some data.")
                st.stop()
            data = pasted_text.encode("utf-8")
            source_label = f"{len(data):,} bytes pasted"

        endpoint = build_url(customer_id.strip(), domain.strip())

        with st.spinner(f"Sending to Observe ({len(data):,} bytes uncompressed)..."):
            resp = post_to_observe(endpoint, token.strip(), content_type, data)

        st.success(f"Sent successfully — HTTP {resp.status_code}  |  Source: {source_label}  |  Endpoint: `{endpoint}`")

    except requests.HTTPError as e:
        st.error(f"HTTP {e.response.status_code}: {e.response.text}")
    except Exception as e:
        st.error(str(e))
