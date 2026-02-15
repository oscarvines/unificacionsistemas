import streamlit as st
import pandas as pd
import io
import os
import shutil
from datetime import datetime, timedelta

# --- IMPORTACIONES DE TUS EXTRACTORES ---
from extractor_idc import extraer_datos_idc
from extractor_190 import extraer_datos_190
from extractor_nominas import procesar_documento, split_pdf 

SPLIT_DIR = "split_temp"
if not os.path.exists(SPLIT_DIR):
    os.makedirs(SPLIT_DIR, exist_ok=True)

# --- 1. FUNCIÓN DE NORMALIZACIÓN (Regla 8 números + 1 letra) ---
def normalizar_dni_final(valor):
    if pd.isna(valor) or str(valor).strip() == "": return None
    # Dejar solo letras y números
    s = "".join(filter(str.isalnum, str(valor))).upper()
    # Tomamos los últimos 9 caracteres (ej: 016095080W -> 16095080W)
    return s[-9:] if len(s) >= 9 else s

def limpiar_valor_numerico(valor):
    if pd.isna(valor) or valor == "" or valor == "N/A": return 0.0
    if isinstance(valor, (int, float)): return float(valor)
    s = str(valor).strip().replace('.', '').replace(',', '.')
    try: return float(s)
    except ValueError: return 0.0

def to_excel(df, sheet_name='Datos'):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

def ejecutar_super_extractor():
    # --- INICIALIZACIÓN CRÍTICA (Evita el AttributeError) ---
    if 'raw_idc' not in st.session_state: st.session_state.raw_idc = []
    if 'raw_190' not in st.session_state: st.session_state.raw_190 = []
    if 'raw_nom' not in st.session_state: st.session_state.raw_nom = []
    if 'errores_idc' not in st.session_state: st.session_state.errores_idc = []
    
    # Inicializamos los DataFrames finales como vacíos para que el Cuadro de Mando no falle al arrancar
    if 'df_final_idc' not in st.session_state: st.session_state.df_final_idc = pd.DataFrame()
    if 'df_final_190' not in st.session_state: st.session_state.df_final_190 = pd.DataFrame()
    if 'df_final_nom' not in st.session_state: st.session_state.df_final_nom = pd.DataFrame()

    # --- BARRA LATERAL ---
    with st.sidebar:
        st.header("📂 Carga de Documentos")
        
        st.subheader("1. Auditoría IDC")
        f_idc = st.file_uploader("Subir IDCs", type="pdf", accept_multiple_files=True, key="up_idc")
        anio_audit = st.selectbox("Año Auditoría IDC:", [2024, 2025, 2023, 2026], index=0)
        h_conv = st.number_input("Horas Convenio Anual:", value=1800.0)
        emp_manual = st.text_input("Empresa Cliente (Autónomos):", value="")
        cif_manual = st.text_input("CIF Empresa (Autónomos):", value="")
        
        st.divider()
        st.subheader("2. Modelo 190")
        f_190 = st.file_uploader("Subir Modelos 190", type="pdf", accept_multiple_files=True, key="up_190")
        anio_190 = st.number_input("Año del Modelo 190:", value=2024, format="%d")
        
        st.divider()
        st.subheader("3. Nóminas")
        f_nom = st.file_uploader("Subir Nóminas", type="pdf", accept_multiple_files=True, key="up_nom")
        
        if st.button("🚀 PROCESAR TODO", use_container_width=True):
            # Reiniciamos datos
            st.session_state.raw_idc, st.session_state.raw_190, st.session_state.raw_nom = [], [], []
            st.session_state.errores_idc = []
            st.session_state.df_final_idc = pd.DataFrame()
            st.session_state.df_final_190 = pd.DataFrame()
            st.session_state.df_final_nom = pd.DataFrame()

            if f_idc:
                for f in f_idc:
                    datos, _ = extraer_datos_idc(f)
                    if datos: st.session_state.raw_idc.extend(datos)

            if f_190:
                for f in f_190:
                    datos = extraer_datos_190(f)
                    for d in datos: d["Año_190"] = anio_190
                    st.session_state.raw_190.extend(datos)

            if f_nom:
                temp_paths = []
                for uploaded in f_nom:
                    tmp_path = os.path.join(SPLIT_DIR, uploaded.name)
                    with open(tmp_path, "wb") as f_tmp: f_tmp.write(uploaded.getbuffer())
                    temp_paths.append(tmp_path)
                for path in temp_paths:
                    paginas = split_pdf(path, split_dir=SPLIT_DIR)
                    for pagina in paginas:
                        datos = procesar_documento(pagina)
                        st.session_state.raw_nom.append(datos)
                shutil.rmtree(SPLIT_DIR)
                os.makedirs(SPLIT_DIR, exist_ok=True)
            st.success("✅ Procesamiento completado.")

    # --- PESTAÑAS DE RESULTADOS ---
    tab_idc, tab_190, tab_nom, tab_maestra = st.tabs(["📊 IDC", "📄 190", "💰 Nóminas", "🎯 Cuadro de Mando"])

    # 1. PESTAÑA IDC
    with tab_idc:
        if st.session_state.raw_idc:
            nombres_dis = sorted(list({r['Nombre'] for r in st.session_state.raw_idc if "DESCONOCIDO" not in r['Nombre']}))
            if nombres_dis:
                seleccion = st.multiselect("Filtrar Trabajadores:", options=nombres_dis, default=nombres_dis)
                dias_anio = 366 if (anio_audit % 4 == 0) else 365
                v_h_d = h_conv / dias_anio
                f_limite_ini = datetime(anio_audit, 1, 1)
                res_final_idc = []
                for p in seleccion:
                    idcs_p = sorted([r for r in st.session_state.raw_idc if r['Nombre'] == p], key=lambda x: x['Desde_Info'])
                    h_t, h_i, d_it, d_alta = 0.0, 0.0, 0, 0
                    primer_dia, ultimo_dia = None, None
                    es_aut = idcs_p[0].get('Es_Autonomo', False)
                    for d in range(dias_anio):
                        dia = f_limite_ini + timedelta(days=d)
                        vig = next((i for i in reversed(idcs_p) if i['Desde_Info'] <= dia <= i['Hasta_Info']), None)
                        if vig:
                            try:
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
                            except: continue
                    if d_alta > 0:
                        dni_ok = normalizar_dni_final(idcs_p[0]['DNI_Trabajador'])
                        res_final_idc.append({
                            "Nombre": p, "DNI": dni_ok,
                            "Horas Efectivas": round(h_t - h_i, 2), "Días IT": int(d_it),
                            "CIF Empresa": cif_manual if es_aut else idcs_p[0]['NIF_Empresa'],
                            "Empresa": emp_manual if es_aut else idcs_p[0]['Empresa']
                        })
                st.session_state.df_final_idc = pd.DataFrame(res_final_idc)
                st.dataframe(st.session_state.df_final_idc, use_container_width=True)
                st.download_button("📥 Excel IDC", to_excel(st.session_state.df_final_idc, 'Auditoria'), f"Auditoria_IDC_{anio_audit}.xlsx")

    # 2. PESTAÑA 190
    with tab_190:
        if st.session_state.raw_190:
            df_190 = pd.DataFrame(st.session_state.raw_190)
            for col in ['Percepciones', 'Retenciones']:
                if col in df_190.columns: df_190[col] = df_190[col].apply(limpiar_valor_numerico)
            
            col_id = 'NIF' if 'NIF' in df_190.columns else ('DNI' if 'DNI' in df_190.columns else None)
            if col_id: df_190[col_id] = df_190[col_id].apply(normalizar_dni_final)
            
            st.session_state.df_final_190 = df_190
            c1, c2 = st.columns([1, 3])
            with c1: sel_clv = st.multiselect("Clave:", options=sorted(df_190['Clave'].unique()))
            df_t = df_190[df_190['Clave'].isin(sel_clv)] if sel_clv else df_190
            with c2: sel_nom = st.multiselect("Trabajador:", options=sorted(df_t['Nombre'].unique()))
            df_f_190 = df_t[df_t['Nombre'].isin(sel_nom)] if sel_nom else df_t
            st.dataframe(df_f_190, use_container_width=True)
            st.download_button("📥 Excel 190", to_excel(df_f_190, '190'), f"Modelo_190_{anio_190}.xlsx")

    # 3. PESTAÑA NÓMINAS
    with tab_nom:
        if st.session_state.raw_nom:
            df_nom = pd.DataFrame(st.session_state.raw_nom)
            if 'DNI' in df_nom.columns: df_nom['DNI'] = df_nom['DNI'].apply(normalizar_dni_final)
            st.session_state.df_final_nom = df_nom
            st.dataframe(df_nom, use_container_width=True)
            
            df_export = df_nom.copy()
            if "AportacionEmpresa" in df_export.columns:
                df_export["AportacionEmpresa"] = df_export["AportacionEmpresa"].astype(str).map(lambda x: x.replace(".", ","))
            towrite = io.BytesIO()
            df_export.to_excel(towrite, index=False, engine="openpyxl")
            towrite.seek(0)
            st.download_button("📥 Excel Nóminas", towrite, "nominas_extraidas.xlsx")

    # 4. CUADRO DE MANDO (UNIFICACIÓN TOTAL)
    with tab_maestra:
        st.header("🎯 Cuadro de Mando Unificado")
        
        # Leemos los DataFrames que inicializamos al principio (ya no darán AttributeError)
        df_i = st.session_state.df_final_idc
        df_1 = st.session_state.df_final_190
        df_n = st.session_state.df_final_nom

        if not df_i.empty or not df_1.empty or not df_n.empty:
            
            # Normalización para el cruce
            for df, col in [(df_i, 'DNI'), (df_1, 'DNI'), (df_1, 'NIF'), (df_n, 'DNI')]:
                if not df.empty and col in df.columns:
                    df['DNI_JOIN'] = df[col]

            def consolidar(df):
                if df.empty: return df
                agg_dict = {c: ('sum' if pd.api.types.is_numeric_dtype(df[c]) else 'first') 
                            for c in df.columns if c != 'DNI_JOIN'}
                return df.groupby('DNI_JOIN').agg(agg_dict).reset_index()

            idc_c = consolidar(df_i)
            i190_c = consolidar(df_1)
            nom_c = consolidar(df_n)

            resultado = pd.DataFrame()
            if not idc_c.empty: resultado = idc_c
            
            if not i190_c.empty:
                if resultado.empty: resultado = i190_c
                else: resultado = pd.merge(resultado, i190_c, on='DNI_JOIN', how='outer', suffixes=('', '_190'))

            if not nom_c.empty:
                if resultado.empty: resultado = nom_c
                else: resultado = pd.merge(resultado, nom_c, on='DNI_JOIN', how='outer', suffixes=('', '_NOM'))

            if not resultado.empty:
                resultado.rename(columns={'DNI_JOIN': 'DNI_UNIFICADO'}, inplace=True)
                cols_drop = [c for c in resultado.columns if c in ['DNI', 'NIF', 'DNI_190', 'NIF_190', 'DNI_NOM']]
                resultado = resultado.drop(columns=cols_drop)
                st.dataframe(resultado, use_container_width=True)
                st.download_button("📥 Excel Cuadro Mando", to_excel(resultado, 'Consolidado'), "Cuadro_Mando.xlsx")
        else:
            st.info("💡 Sube y procesa documentos para ver la unificación.")