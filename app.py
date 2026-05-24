import streamlit as st

st.set_page_config(
    page_title="Aion",
    layout="wide"
)

st.title("🌌 Aion")
st.subheader("Your Local AI Second Brain")

st.write("Aion V1 is now running locally.")

from core.document_loader import DocumentLoader

loader = DocumentLoader()

doc = loader.load("Sample.pdf")

print(doc.filename)
print(doc.file_type)
print(doc.content[:500])
print(doc.metadata)