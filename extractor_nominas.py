import os
import json
import pandas as pd
import streamlit as st
from PyPDF2 import PdfReader, PdfWriter
from google.oauth2 import service_account
from google.cloud import documentai_v1beta3 as documentai

# --- Autenticación local ---
# Asegúrate de que esta línea esté al principio del archivo (o antes de crear el cliente)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/oscarvines/Downloads/lectornominas-04238e0ab172.json"

# ELIMINA O COMENTA estas líneas:
# info = json.loads(st.secrets["google"]["credentials"])
# creds = service_account.Credentials.from_service_account_info(info)

# MODIFICA el cliente para que quede SOLO así:
client = documentai.DocumentProcessorServiceClient(
    client_options={"api_endpoint": "eu-documentai.googleapis.com"}
)
# Configuración de Document AI
PROJECT_ID = "654011088"
LOCATION = "eu"
PROCESSOR_ID = "ff607a96112bfc11"
processor_name = client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)

# Rutas por defecto (pueden sobreescribirse al importar)
DEFAULT_INPUT_FOLDER = "/Users/oscarvines/Downloads/nominas"
DEFAULT_SPLIT_DIR = os.path.join(DEFAULT_INPUT_FOLDER, "split_temp")
DEFAULT_OUTPUT_EXCEL = "nominas_extraidas.xlsx"

def split_pdf(ruta_pdf: str, split_dir: str = DEFAULT_SPLIT_DIR) -> list[str]:
    """
    Divide un PDF en páginas individuales y devuelve la lista de rutas.
    """
    reader = PdfReader(ruta_pdf)
    archivos = []
    base = os.path.splitext(os.path.basename(ruta_pdf))[0]
    os.makedirs(split_dir, exist_ok=True)

    for i, page in enumerate(reader.pages):
        writer = PdfWriter()
        writer.add_page(page)
        chunk_name = f"{base}_page_{i+1}.pdf"
        chunk_path = os.path.join(split_dir, chunk_name)
        with open(chunk_path, "wb") as f:
            writer.write(f)
        archivos.append(chunk_path)

    return archivos

def procesar_documento(ruta_pdf: str) -> dict:
    """
    Procesa un PDF (ruta en disco) usando Document AI y devuelve
    un diccionario con los campos extraídos y suma de AportacionEmpresa.
    """
    with open(ruta_pdf, "rb") as f:
        contenido = f.read()

    request = {
        "name": processor_name,
        "raw_document": {"content": contenido, "mime_type": "application/pdf"}
    }
    resultado = client.process_document(request=request)
    doc = resultado.document

    # Diccionario de campos a extraer
    campos = {
        "Archivo": os.path.basename(ruta_pdf),
        "Nombre": "",
        "DNI": "",
        "MesNomina": "",
        "Anualidad": "",
        "Salario": "",
        "AportacionEmpresa": 0.0,
        "Empresa": "",
        "CIF": ""
    }

    # Recorre entidades y acumula valores
    for entidad in doc.entities:
        tipo = entidad.type_.strip()
        valor = entidad.mention_text.strip()

        if tipo == "AportacionEmpresa":
            trozos = valor.replace("\n", " ").split()
            for t in trozos:
                try:
                   # Quita puntos de miles y convierte coma decimal
                    t_limpio = t.replace(".", "").replace(",", ".")
                    campos["AportacionEmpresa"] += float(t_limpio)
                except ValueError:
                    continue
        elif tipo in campos:
            campos[tipo] = valor
    # Formatea AportacionEmpresa con 2 decimales
    campos["AportacionEmpresa"] = f"{campos['AportacionEmpresa']:.2f}"
    return campos

def procesar_folder(
    input_folder: str = DEFAULT_INPUT_FOLDER,
    split_dir: str = DEFAULT_SPLIT_DIR,
    output_excel: str = DEFAULT_OUTPUT_EXCEL
) -> pd.DataFrame:
    """
    Recorre todos los PDFs de una carpeta, los divide si son multi-página,
    procesa cada uno y guarda los resultados en un DataFrame.
    Además exporta el DataFrame a un archivo Excel.
    """
    resultados = []

    # Asegura existencia de split_dir
    os.makedirs(split_dir, exist_ok=True)

    for archivo in os.listdir(input_folder):
        if not archivo.lower().endswith(".pdf"):
            continue
        ruta_pdf = os.path.join(input_folder, archivo)
        reader = PdfReader(ruta_pdf)
        total_paginas = len(reader.pages)

        # Si tiene varias páginas, dividir; si no, procesar directo
        trozos = split_pdf(ruta_pdf, split_dir) if total_paginas > 1 else [ruta_pdf]

        for pdf_trozo in trozos:
            datos = procesar_documento(pdf_trozo)
            resultados.append(datos)

    df = pd.DataFrame(resultados)
    df.to_excel(output_excel, index=False)
    return df

if __name__ == "__main__":
    # Ejecuta procesamiento completo desde línea de comandos
    df = procesar_folder()
    print(f"Excel generado: {DEFAULT_OUTPUT_EXCEL}")
