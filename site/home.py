import streamlit as st

st.header("Welcome to Observe FAQs")
st.write(
    "This app provides resources and tools for working with Observe. "
    "Use the navigation on the left to explore FAQs or use the export tools."
)

st.subheader("What's available")
col1, col2 = st.columns(2)
with col1:
    st.info("**FAQs**\nFrequently asked questions about Observe.")
with col2:
    st.info("**Tools**\nExport monitors, datasets, and alerts from Observe.")
