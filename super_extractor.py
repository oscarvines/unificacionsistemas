import streamlit as st
import pandas as pd
import io
import os
import shutil
import pdfplumber
from datetime import datetime, timedelta

# --- IMPORTACIONES DE TUS EXTRACTORES VALIDADOS ---
from extractor_idc import extraer_datos_idc
from extractor_190 import extraer_datos_190
from extractor_nominas import procesar_documento, split_pdf 

# Directorio temporal para el split de nóminas
SPLIT_DIR = "split_temp"
if not os.path.exists(SPLIT_DIR):
    os.makedirs(SPLIT_DIR, exist_ok=True)

def limpiar_valor_numerico(valor):
    """Convierte formatos '1.234,56' a floats sumables en Excel."""
    if pd.isna(valor) or valor == "" or valor == "N/A":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip().replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0

def to_excel(df, sheet_name='Datos'):
    """Genera un archivo Excel en memoria con formato numérico real."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

def ejecutar_super_extractor():
    # --- ESTADO DE SESIÓN PARA PERSISTENCIA ---
    if 'raw_idc' not in st.session_state: st.session_state.raw_idc = []
    if 'raw_190' not in st.session_state: st.session_state.raw_190 = []
    if 'raw_nom' not in st.session_state: st.session_state.raw_nom = []
    if 'errores_idc' not in st.session_state: st.session_state.errores_idc = []

    # --- BARRA LATERAL CON 3 CARGADORES INDEPENDIENTES ---
    with st.sidebar:
        st.header("📂 Carga de Documentos")
        
        # 1. BLOQUE IDC
        st.subheader("1. Auditoría IDC")
        f_idc = st.file_uploader("Subir IDCs", type="pdf", accept_multiple_files=True, key="up_idc")
        anio_audit = st.selectbox("Año Auditoría IDC:", [2024, 2025, 2023, 2026], index=0)
        h_conv = st.number_input("Horas Convenio Anual:", value=1800.0)
        emp_manual = st.text_input("Empresa Cliente (Autónomos):", value="")
        cif_manual = st.text_input("CIF Empresa (Autónomos):", value="")
        
        st.divider()
        
        # 2. BLOQUE 190
        st.subheader("2. Modelo 190")
        f_190 = st.file_uploader("Subir Modelos 190", type="pdf", accept_multiple_files=True, key="up_190")
        anio_190 = st.number_input("Año del Modelo 190:", value=2024, format="%d")
        
        st.divider()
        
        # 3. BLOQUE NÓMINAS
        st.subheader("3. Nóminas")
        f_nom = st.file_uploader("Subir Nóminas", type="pdf", accept_multiple_files=True, key="up_nom")
        
        st.divider()
        
        if st.button("🚀 PROCESAR TODO", use_container_width=True):
            # Reiniciamos estados para nueva carga
            st.session_state.raw_idc, st.session_state.raw_190, st.session_state.raw_nom = [], [], []
            st.session_state.errores_idc = []

            # A. Procesar IDCs
            if f_idc:
                for f in f_idc:
                    datos, _ = extraer_datos_idc(f)
                    if datos:
                        if "DESCONOCIDO" in str(datos[0].get("Nombre", "")):
                            st.session_state.errores_idc.append(f.name)
                        st.session_state.raw_idc.extend(datos)

            # B. Procesar 190
            if f_190:
                for f in f_190:
                    datos = extraer_datos_190(f)
                    for d in datos: d["Año_190"] = anio_190
                    st.session_state.raw_190.extend(datos)

            # C. Procesar Nóminas (Lógica de Producción con Split)
            if f_nom:
                temp_paths = []
                for uploaded in f_nom:
                    tmp_path = os.path.join(SPLIT_DIR, uploaded.name)
                    with open(tmp_path, "wb") as f_tmp:
                        f_tmp.write(uploaded.getbuffer())
                    temp_paths.append(tmp_path)

                pdfs_paginas = []
                total_paginas = 0
                for path in temp_paths:
                    paginas = split_pdf(path, split_dir=SPLIT_DIR)
                    pdfs_paginas.append((os.path.basename(path), paginas))
                    total_paginas += len(paginas)

                progreso = st.progress(0.0)
                cont = 0
                with st.spinner("Extrayendo Nóminas con Google AI..."):
                    for nombre, paginas in pdfs_paginas:
                        for idx, pagina in enumerate(paginas, 1):
                            datos = procesar_documento(pagina)
                            st.session_state.raw_nom.append(datos)
                            cont += 1
                            progreso.progress(cont / total_paginas)
                
                shutil.rmtree(SPLIT_DIR)
                os.makedirs(SPLIT_DIR, exist_ok=True)
            
            st.success("✅ Procesamiento completado.")

    # --- ALERTAS DE ERROR (IDC) ---
    if st.session_state.errores_idc:
        st.warning(f"⚠️ Se han detectado {len(st.session_state.errores_idc)} archivos IDC que parecen ser escaneos y no se han podido leer.")
        with st.expander("Ver lista de archivos no leídos"):
            for err in st.session_state.errores_idc:
                st.write(f"❌ {err}")

    # --- PESTAÑAS DE RESULTADOS ---
    tab_idc, tab_190, tab_nom = st.tabs(["📊 Auditoría IDC", "📄 Modelo 190", "💰 Nóminas"])

    with tab_idc:
        if st.session_state.raw_idc:
            nombres_dis = sorted(list({r['Nombre'] for r in st.session_state.raw_idc if "DESCONOCIDO" not in r['Nombre']}))
            if nombres_dis:
                seleccion = st.multiselect("Filtrar Trabajadores:", options=nombres_dis, default=nombres_dis)
                dias_anio = 366 if (anio_audit % 4 == 0 and (anio_audit % 100 != 0 or anio_audit % 400 == 0)) else 365
                v_h_d = h_conv / dias_anio
                f_limite_ini = datetime(anio_audit, 1, 1)

                res_final_idc = []
                for p in seleccion:
                    idcs_p = sorted([r for r in st.session_state.raw_idc if r['Nombre'] == p], key=lambda x: x['Desde_Info'])
                    h_t, h_i, d_it, d_alta = 0.0, 0.0, 0, 0
                    primer_dia, ultimo_dia = None, None
                    hay_hueco = False
                    
                    es_aut = idcs_p[0].get('Es_Autonomo', False)
                    f_contrato_orig = idcs_p[0]['Inicio_Contrato']

                    for d in range(dias_anio):
                        dia = f_limite_ini + timedelta(days=d)
                        vig = next((i for i in reversed(idcs_p) if i['Desde_Info'] <= dia <= i['Hasta_Info']), None)
                        if vig:
                            f_a = datetime.strptime(vig['Alta'], "%d-%m-%Y")
                            f_b = datetime.strptime(vig['Baja'], "%d-%m-%Y") if vig['Baja'] != "ACTIVO" else datetime(2099,1,1)
                            if f_a <= dia <= f_b:
                                d_alta += 1
                                if primer_dia is None: primer_dia = dia
                                ultimo_dia = dia
                                ctp_val = vig.get('CTP', 0)
                                factor = 1.0 if (es_aut or ctp_val in [0, 1000]) else ctp_val / 1000.0
                                h_t += v_h_d * factor
                                if not es_aut and any(it[0] <= dia <= it[1] for it in vig['Tramos_IT']):
                                    d_it += 1
                                    h_i += v_h_d * factor
                        elif f_contrato_orig <= dia: hay_hueco = True

                    if d_alta > 0:
                        ultimo_ctp = idcs_p[-1].get('CTP', 0)
                        dedicacion_texto = "100%" if (es_aut or ultimo_ctp in [0, 1000]) else f"{(ultimo_ctp/10):.2f}%"
                        res_final_idc.append({
                            "Nombre": p, "DNI": idcs_p[0]['DNI_Trabajador'],
                            "CIF Empresa": cif_manual if es_aut else idcs_p[0]['NIF_Empresa'],
                            "Empresa": emp_manual if es_aut else idcs_p[0]['Empresa'],
                            "Estado": "⚠️ INCOMPLETO" if hay_hueco else "✅ OK",
                            "Inicio Contrato": f_contrato_orig.strftime("%d-%m-%Y"),
                            "Inicio Auditado": primer_dia.strftime("%d-%m-%Y") if primer_dia else "N/A",
                            "Fin Auditado": ultimo_dia.strftime("%d-%m-%Y") if ultimo_dia else "N/A",
                            "Días IT": int(d_it), "Horas Teóricas": round(h_t, 2),
                            "Horas IT": round(h_i, 2), "Horas Efectivas": round(h_t - h_i, 2),
                            "Dedicación": dedicacion_texto
                        })
                df_idc = pd.DataFrame(res_final_idc)
                st.subheader(f"✅ Informe Auditoría {anio_audit}")
                st.dataframe(df_idc, use_container_width=True)
                st.download_button("📥 Descargar Excel IDC", to_excel(df_idc, 'Auditoria'), f"Auditoria_IDC_{anio_audit}.xlsx")

    with tab_190:
        if st.session_state.raw_190:
            df_190 = pd.DataFrame(st.session_state.raw_190)
            for col in ['Percepciones', 'Retenciones']:
                if col in df_190.columns: df_190[col] = df_190[col].apply(limpiar_valor_numerico)
            
            st.subheader(f"📄 Registros Modelo 190 ({anio_190})")
            c1, c2 = st.columns([1, 3])
            with c1:
                sel_clv = st.multiselect("Clave:", options=sorted(df_190['Clave'].unique()))
            df_t = df_190[df_190['Clave'].isin(sel_clv)] if sel_clv else df_190
            with c2:
                sel_nom = st.multiselect("Trabajador:", options=sorted(df_t['Nombre'].unique()))
            df_f_190 = df_t[df_t['Nombre'].isin(sel_nom)] if sel_nom else df_t
            st.dataframe(df_f_190, use_container_width=True)
            st.download_button("📥 Descargar Excel 190", to_excel(df_f_190, '190'), f"Modelo_190_{anio_190}.xlsx")

    with tab_nom:
        if st.session_state.raw_nom:
            df_nom = pd.DataFrame(st.session_state.raw_nom)
            
            st.subheader("💰 Resumen Nóminas")
            st.dataframe(df_nom, use_container_width=True)
            
            # --- AJUSTE EXPORTACIÓN NÓMINAS (Tu lógica original de producción) ---
            df_export = df_nom.copy()
            if "AportacionEmpresa" in df_export.columns:
                df_export["AportacionEmpresa"] = (
                    df_export["AportacionEmpresa"]
                    .astype(str)
                    .map(lambda x: x.replace(".", ","))
                )
            
            towrite = io.BytesIO()
            df_export.to_excel(towrite, index=False, engine="openpyxl")
            towrite.seek(0)
            
            st.download_button(
                label="📥 Descargar Excel Nóminas",
                data=towrite,
                file_name="nominas_extraidas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )