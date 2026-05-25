import base64
import json

import streamlit as st

OBSERVE_HEADER = "Observe Copied Dashboard\nOpenTelemetry - Host Metrics\n/* Observe!Start "
OBSERVE_FOOTER = " Observe!End */"


st.subheader("Base64 Encoder")
st.caption("Paste JSON or text to encode it as base64 for importing into Observe dashboards.")

raw = st.text_area("Content to Encode", height=300, placeholder="Paste dashboard JSON or text here...")

encode_clicked = st.button("Encode", type="primary", icon=":material/lock:")

if encode_clicked and raw.strip():
    try:
        try:
            parsed = json.loads(raw.strip())
            normalized = json.dumps(parsed, separators=(",", ":"))
            input_bytes = normalized.encode("utf-8")
        except (json.JSONDecodeError, ValueError):
            input_bytes = raw.strip().encode("utf-8")

        b64 = base64.b64encode(input_bytes).decode("ascii")
        result = f"{OBSERVE_HEADER}{b64}{OBSERVE_FOOTER}"

        st.session_state["encoded_output"] = result
        st.session_state["encode_error"] = None
    except Exception as e:
        st.session_state["encode_error"] = str(e)
        st.session_state["encoded_output"] = None
elif encode_clicked and not raw.strip():
    st.warning("Paste some content to encode first.")

if st.session_state.get("encode_error"):
    st.error(f"Failed to encode: {st.session_state['encode_error']}")

if st.session_state.get("encoded_output"):
    result = st.session_state["encoded_output"]
    st.code(result, language="text")


