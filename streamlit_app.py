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
            st.Page("site/tools/export_datasets.py", title="Export Datasets", icon=":material/dataset:"),
            st.Page("site/tools/export_monitor_details.py", title="Export Monitor Details", icon=":material/notifications:"),
        ],
    },
    position="sidebar",
)

page.run()
