import streamlit as st
from super_extractor import ejecutar_super_extractor

st.set_page_config(page_title="Audit Suite Pro", layout="wide")

# --- MENÚ LATERAL ---
with st.sidebar:
    st.title("🛡️ Auditoría Hub")
    opcion = st.selectbox("Menú Principal", ["Súper Extractor", "Configuración"])

if opcion == "Súper Extractor":
    ejecutar_super_extractor()
else:
    st.write("Configuración del sistema...")