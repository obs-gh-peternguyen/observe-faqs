import streamlit as st

st.header("Frequently Asked Questions")
st.write("Common questions and answers about Observe.")

with st.expander("What is Observe?"):
    st.write(
        "Observe is a cloud-based observability platform that helps teams monitor, "
        "troubleshoot, and understand their applications and infrastructure."
    )

with st.expander("How do I create a monitor?"):
    st.write(
        "Navigate to the Monitors section in Observe, click **New Monitor**, "
        "select a monitor type (Threshold, Anomaly, etc.), configure your conditions, "
        "and save."
    )

with st.expander("How do I export data from Observe?"):
    st.write(
        "Use the **Tools** section in this app to export monitors, datasets, and alerts "
        "directly from the Observe API."
    )

with st.expander("What authentication do I need?"):
    st.write(
        "You need your **Customer ID**, **domain**, and an **API token** from your "
        "Observe account settings."
    )
