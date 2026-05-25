import base64
import json
import re

import streamlit as st

OBSERVE_START = "/* Observe!Start "
OBSERVE_END = " Observe!End */"


def decode_observe_dashboard(text: str) -> tuple[str, bool]:
    match = re.search(r"(/\* Observe!Start )(.*?)( Observe!End \*/)", text, re.DOTALL)
    if not match:
        return None, False

    before = text[: match.start()]
    b64_token = match.group(2).strip()
    after = text[match.end() :]

    raw = base64.b64decode(b64_token).decode("utf-8")
    try:
        parsed = json.loads(raw)
        decoded_inner = json.dumps(parsed, indent=2)
        is_json = True
    except (json.JSONDecodeError, ValueError):
        decoded_inner = raw
        is_json = False

    return decoded_inner, is_json


def decode_plain(text: str) -> tuple[str, bool]:
    raw = base64.b64decode(text.strip()).decode("utf-8")
    try:
        parsed = json.loads(raw)
        return json.dumps(parsed, indent=2), True
    except (json.JSONDecodeError, ValueError):
        return raw, False


st.subheader("Base64 Decoder")
st.caption("Paste a base64-encoded string or an Observe copied dashboard to decode it.")

encoded = st.text_area("Encoded String", height=200, placeholder="Paste base64-encoded string or Observe dashboard here...")

decode_clicked = st.button("Decode", type="primary", icon=":material/lock_open:")

if decode_clicked and encoded.strip():
    try:
        if OBSERVE_START in encoded and OBSERVE_END in encoded:
            decoded, is_json = decode_observe_dashboard(encoded)
        else:
            decoded, is_json = decode_plain(encoded)

        st.session_state["decoded_output"] = decoded
        st.session_state["decoded_is_json"] = is_json
        st.session_state["decode_error"] = None
    except Exception as e:
        st.session_state["decode_error"] = str(e)
        st.session_state["decoded_output"] = None
elif decode_clicked and not encoded.strip():
    st.warning("Paste a base64-encoded string first.")

if st.session_state.get("decode_error"):
    st.error(f"Failed to decode: {st.session_state['decode_error']}")

if st.session_state.get("decoded_output"):
    decoded = st.session_state["decoded_output"]
    if st.session_state.get("decoded_is_json"):
        st.code(decoded, language="json")
    else:
        st.code(decoded, language="text")


