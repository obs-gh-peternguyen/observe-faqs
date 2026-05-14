from otel_setup import init_otel
init_otel()

import streamlit as st

st.set_page_config(page_title="Observe FAQs", page_icon=":material/visibility:", layout="wide")

page = st.navigation(
    {
        "": [
            st.Page("site/home.py", title="Home", icon=":material/home:"),
            st.Page("site/faqs.py", title="FAQs", icon=":material/help:"),
        ],
        "Tools": [
            st.Page("site/tools/export_monitor_list.py", title="Export Monitor List", icon=":material/monitor:"),
            st.Page("site/tools/export_monitor_details.py", title="Export Monitor Details", icon=":material/notifications:"),
            st.Page("site/tools/export_all_monitor_details.py", title="Export All Monitor Details", icon=":material/table_rows:"),
            st.Page("site/tools/export_dataset.py", title="Export Dataset", icon=":material/dataset:"),
            st.Page("site/tools/export_dataset_details.py", title="Export Dataset Details", icon=":material/schema:"),
            st.Page("site/tools/base64_decoder.py", title="Base64 Decoder", icon=":material/lock_open:"),
        ],
    },
    position="sidebar",
)

page.run()
