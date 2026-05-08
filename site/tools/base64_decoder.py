import base64
import json

import streamlit as st

st.subheader("Base64 Decoder")
st.caption("Paste a base64-encoded string to decode it.")

encoded = st.text_area("Encoded String", height=200, placeholder="Paste base64-encoded string here...")

decode_clicked = st.button("Decode", type="primary", icon=":material/lock_open:")

if decode_clicked and encoded.strip():
    try:
        raw = base64.b64decode(encoded.strip()).decode("utf-8")
        try:
            parsed = json.loads(raw)
            st.session_state["decoded_output"] = json.dumps(parsed, indent=2)
            st.session_state["decoded_is_json"] = True
        except (json.JSONDecodeError, ValueError):
            st.session_state["decoded_output"] = raw
            st.session_state["decoded_is_json"] = False
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

    copy_clicked = st.button("Copy Decoded String", icon=":material/content_copy:", type="secondary")
    if copy_clicked:
        js = f"""
        <script>
        const text = {json.dumps(decoded)};
        navigator.clipboard.writeText(text);
        </script>
        """
        st.components.v1.html(js, height=0)
        st.success("Copied to clipboard!")
