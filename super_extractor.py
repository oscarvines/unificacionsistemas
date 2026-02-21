import streamlit as st
import pandas as pd
import io
import os
import shutil
from datetime import datetime, timedelta
def obtener_tipo_desempleo(codigo_contrato):
    grupo_5_5 = ["100", "109", "130", "139", "150", "189", "200", "209", "230", "250", "289", "300", "389"]
    grupo_6_7 = ["401", "402", "410", "421", "430", "441", "450", "501", "502", "510", "530", "541"]
    
    if str(codigo_contrato) in grupo_5_5:
        return 5.5
    elif str(codigo_contrato) in grupo_6_7:
        return 6.7
    return 0.0
# --- IMPORTACIONES DE TUS EXTRACTORES ---
from extractor_idc import extraer_datos_idc
from extractor_190 import extraer_datos_190
from extractor_nominas import procesar_documento, split_pdf
from rnt_reader import extraer_bases_rnt 

SPLIT_DIR = "split_temp"
if not os.path.exists(SPLIT_DIR):
    os.makedirs(SPLIT_DIR, exist_ok=True)

# --- FUNCIÓN DE NORMALIZACIÓN ---
def normalizar_dni_final(valor):
    if pd.isna(valor) or str(valor).strip() == "": return None
    s = "".join(filter(str.isalnum, str(valor))).upper()
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
    # --- INICIALIZACIÓN ---
    for key in ['raw_idc', 'raw_190', 'raw_nom', 'raw_rnt_det', 'raw_rnt_res', 'errores_idc']:
        if key not in st.session_state: st.session_state[key] = []
    
    if 'df_final_idc' not in st.session_state: st.session_state.df_final_idc = pd.DataFrame()
    if 'df_final_190' not in st.session_state: st.session_state.df_final_190 = pd.DataFrame()
    if 'df_final_nom' not in st.session_state: st.session_state.df_final_nom = pd.DataFrame()
    if 'df_final_rnt' not in st.session_state: st.session_state.df_final_rnt = pd.DataFrame()

    with st.sidebar:
        st.header("📂 Carga de Documentos")
        f_idc = st.file_uploader("Subir IDCs", type="pdf", accept_multiple_files=True, key="up_idc")
        anio_audit = st.selectbox("Año Auditoría IDC:", [2026, 2025, 2024, 2023], index=0)
        tipo_general = st.number_input("Tipo Cotización General (%):", value=25.07, step=0.01)
        h_conv = st.number_input("Horas Convenio Anual:", value=1800.0)
        emp_manual = st.text_input("Empresa Cliente (Autónomos):", value="")
        cif_manual = st.text_input("CIF Empresa (Autónomos):", value="")
        
        st.divider()
        f_190 = st.file_uploader("Subir Modelos 190", type="pdf", accept_multiple_files=True, key="up_190")
        anio_190 = st.number_input("Año del Modelo 190:", value=2024, format="%d")
        
        st.divider()
        f_nom = st.file_uploader("Subir Nóminas", type="pdf", accept_multiple_files=True, key="up_nom")
        st.divider()
        f_rnt = st.file_uploader("Subir RNTs", type="pdf", accept_multiple_files=True, key="up_rnt")
        
        if st.button("🚀 PROCESAR TODO", use_container_width=True):
            st.session_state.raw_idc, st.session_state.raw_190, st.session_state.raw_nom, st.session_state.raw_rnt_det, st.session_state.raw_rnt_res = [], [], [], [], []
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
            if f_rnt:
                for f in f_rnt:
                    # Guardamos temporalmente para que el lector RNT pueda abrirlo
                    with open("temp_rnt.pdf", "wb") as tmp:
                        tmp.write(f.read())
                    det, res, errs = extraer_bases_rnt("temp_rnt.pdf")
                    if det: st.session_state.raw_rnt_det.extend(det)
                    if res: st.session_state.raw_rnt_res.extend(res)
            st.success("✅ Procesamiento completado.")

    tab_idc, tab_190, tab_nom, tab_rnt, tab_maestra = st.tabs(["📊 IDC", "📄 190", "💰 Nóminas", "📑 RNT", "🎯 Cuadro de Mando"])

    # 1. PESTAÑA IDC
    with tab_idc:
        if st.session_state.raw_idc:

            nombres_dis = sorted(list({
                r['Nombre'] for r in st.session_state.raw_idc
                if "DESCONOCIDO" not in r['Nombre']
            }))

            if nombres_dis:

                seleccion = st.multiselect(
                    "Filtrar Trabajadores (IDC):",
                    options=nombres_dis,
                    default=nombres_dis
                )

                dias_anio = 366 if (anio_audit % 4 == 0 and (anio_audit % 100 != 0 or anio_audit % 400 == 0)) else 365
                v_h_d = h_conv / dias_anio
                f_limite_ini = datetime(anio_audit, 1, 1)

                res_final_idc = []

                for p in seleccion:

                    idcs_p = sorted(
                        [r for r in st.session_state.raw_idc if r['Nombre'] == p],
                        key=lambda x: x['Desde_Info']
                    )

                    if not idcs_p:
                        continue

                    h_t, h_i, d_it, d_alta = 0.0, 0.0, 0, 0
                    primer_dia, ultimo_dia = None, None
                    hay_hueco = False

                    es_aut = idcs_p[0].get('Es_Autonomo', False)
                    f_contrato_orig = idcs_p[0]['Inicio_Contrato']

                    for d in range(dias_anio):

                        dia = f_limite_ini + timedelta(days=d)

                        vig = next(
                            (i for i in reversed(idcs_p)
                            if i['Desde_Info'] <= dia <= i['Hasta_Info']),
                            None
                        )

                        deberia_haber_datos = f_contrato_orig <= dia

                        if vig:

                            try:
                                f_a = datetime.strptime(vig['Alta'], "%d-%m-%Y")
                                f_b = datetime.strptime(vig['Baja'], "%d-%m-%Y") if vig['Baja'] != "ACTIVO" else datetime(2099, 1, 1)

                                if f_a <= dia <= f_b:

                                    d_alta += 1

                                    if primer_dia is None:
                                        primer_dia = dia
                                    ultimo_dia = dia

                                    ctp_val = vig.get('CTP', 0)
                                    factor = 1.0 if (es_aut or ctp_val in [0, 1000]) else ctp_val / 1000.0

                                    h_t += v_h_d * factor

                                    if not es_aut and any(it[0] <= dia <= it[1] for it in vig['Tramos_IT']):
                                        d_it += 1
                                        h_i += v_h_d * factor

                            except:
                                continue

                        elif deberia_haber_datos:
                            hay_hueco = True

                    if d_alta > 0:
                        # 1. Recuperamos el código de contrato y calculamos desempleo
                        cod_contrato = idcs_p[0].get('Tipo_Contrato', 'N/A')
                        tipo_des_auto = obtener_tipo_desempleo(cod_contrato)
                        
                        # 2. Calculamos el Total (General + Desempleo)
                        total_cotiz_final = round(tipo_general + tipo_des_auto, 2)

                        # 3. Dedicación
                        ultimo_ctp = idcs_p[-1].get('CTP', 0)
                        dedicacion_texto = "100%" if (es_aut or ultimo_ctp in [0, 1000]) else f"{(ultimo_ctp/10):.2f}%"

                        dni_ok = normalizar_dni_final(idcs_p[0]['DNI_Trabajador'])

                        res_final_idc.append({
                            "Nombre": p,
                            "DNI": dni_ok,
                            "CIF Empresa": cif_manual if es_aut else idcs_p[0]['NIF_Empresa'],
                            "Empresa": emp_manual if es_aut else idcs_p[0]['Empresa'],
                            "Estado": "⚠️ INCOMPLETO" if hay_hueco else "✅ OK",
                            "Contrato": cod_contrato, # <--- NUEVA COLUMNA
                            "Inicio Contrato": f_contrato_orig.strftime("%d-%m-%Y"),
                            "Inicio Auditado": primer_dia.strftime("%d-%m-%Y") if primer_dia else "N/A",
                            "Fin Auditado": ultimo_dia.strftime("%d-%m-%Y") if ultimo_dia else "N/A",
                            "Días IT": int(d_it),
                            "Horas Teóricas": round(h_t, 2),
                            "Horas IT": round(h_i, 2),
                            "Horas Efectivas": round(h_t - h_i, 2),
                            "Dedicación": dedicacion_texto,
                            # --- NUEVAS COLUMNAS DE COTIZACIÓN ---
                            "Cotiz. Gral (%)": tipo_general,
                            "Cotiz. Desempleo (%)": tipo_des_auto,
                            "Total Cotización (%)": total_cotiz_final
                        })

                st.session_state.df_final_idc = pd.DataFrame(res_final_idc)

                st.dataframe(
                    st.session_state.df_final_idc,
                    use_container_width=True
                )
    
    # 2. PESTAÑA 190
    with tab_190:
        if st.session_state.raw_190:
            df_190 = pd.DataFrame(st.session_state.raw_190)
            for col in ['Percepciones', 'Retenciones', 'Dinerarias NO IL', 'Especie NO IL']:
                if col in df_190.columns: df_190[col] = df_190[col].apply(limpiar_valor_numerico)
            
            col_id = 'NIF' if 'NIF' in df_190.columns else ('DNI' if 'DNI' in df_190.columns else None)
            if col_id: df_190[col_id] = df_190[col_id].apply(normalizar_dni_final)
            
            st.session_state.df_final_190 = df_190
            c1, c2 = st.columns([1, 3])
            with c1: sel_clv = st.multiselect("Clave (190):", options=sorted(df_190['Clave'].unique()))
            df_t = df_190[df_190['Clave'].isin(sel_clv)] if sel_clv else df_190
            with c2: sel_nom = st.multiselect("Trabajador (190):", options=sorted(df_t['Nombre'].unique()))
            df_f_190 = df_t[df_t['Nombre'].isin(sel_nom)] if sel_nom else df_t
            st.dataframe(df_f_190, use_container_width=True)

    # 3. PESTAÑA RNT
    with tab_rnt:
        # Generamos el DF desde la lista cruda acumulada en el procesamiento
        if st.session_state.raw_rnt_res:
            df_rnt_v = pd.DataFrame(st.session_state.raw_rnt_res)
            # Aseguramos que el DNI esté limpio para mostrar
            df_rnt_v['DNI'] = df_rnt_v['DNI'].apply(normalizar_dni_final)
            
            st.session_state.df_final_rnt = df_rnt_v # Guardamos para la Tab Maestra
            
            st.subheader("Bases de Cotización Anuales (RNT)")
            st.dataframe(df_rnt_v, use_container_width=True)
            
            with st.expander("Ver Detalle Mensual"):
                if st.session_state.raw_rnt_det:
                    st.dataframe(pd.DataFrame(st.session_state.raw_rnt_det), use_container_width=True)
        else:
            st.info("No hay datos de RNT procesados.")

    # 4. CUADRO DE MANDO (UNIFICACIÓN MEJORADA CON FILTROS)
    with tab_maestra:
        st.header("🎯 Cuadro de Mando Unificado")
        
        # Trabajamos con los Dataframes base cargados
        df_i = st.session_state.df_final_idc.copy()
        df_1 = st.session_state.df_final_190.copy()
        df_n = st.session_state.df_final_nom.copy()
        df_r = st.session_state.df_final_rnt.copy()

        if not df_1.empty:
            # --- FILTROS PARA EL CUADRO DE MANDO ---
            st.subheader("Filtros de Análisis")
            f1, f2 = st.columns([1, 3])
            with f1:
                claves_disp = sorted(df_1['Clave'].unique())
                sel_clv_m = st.multiselect("Seleccionar Claves:", options=claves_disp, default=claves_disp)
            
            # Filtramos el Modelo 190 base antes de unir
            df_1_filtered = df_1[df_1['Clave'].isin(sel_clv_m)]
            
            with f2:
                nombres_disp = sorted(df_1_filtered['Nombre'].unique()) if not df_1_filtered.empty else []
                sel_nom_m = st.multiselect("Seleccionar Trabajadores:", options=nombres_disp)
            
            if sel_nom_m:
                df_1_filtered = df_1_filtered[df_1_filtered['Nombre'].isin(sel_nom_m)]
            
            # --- LÓGICA DE UNIÓN ---
            # Para el match, normalizamos el DNI en todas
            for df_temp, col_temp in [(df_i, 'DNI'), (df_1_filtered, 'NIF'), (df_1_filtered, 'DNI'), (df_n, 'DNI'), (df_r, 'DNI')]:
                if not df_temp.empty and col_temp in df_temp.columns:
                    df_temp['DNI_JOIN'] = df_temp[col_temp].apply(normalizar_dni_final)

            # UNIÓN: El IDC no tiene clave, así que lo pegamos por DNI a cada registro del 190
            if not df_i.empty:
                # Quitamos columnas de nombre del IDC para no duplicar. 
                # AÑADIMOS: 'Contrato' y 'Total Cotización (%)' para el análisis final.
                df_i_min = df_i[[
                    'DNI_JOIN', 
                    'Horas Efectivas', 
                    'Días IT', 
                    'Empresa', 
                    'CIF Empresa', 
                    'Contrato', 
                    'Total Cotización (%)'
                ]]
                resultado = pd.merge(df_1_filtered, df_i_min, on='DNI_JOIN', how='left')
            else:
                resultado = df_1_filtered

            #  --- NUEVA UNIÓN RNT ---
            if not df_r.empty and 'DNI_JOIN' in df_r.columns:
                # Borramos restos de columnas RNT si existieran por re-ejecución
                cols_rnt_limpiar = [c for c in resultado.columns if any(p in c for p in ['Base_CC', 'Base_AT', 'Solidaridad'])]
                resultado = resultado.drop(columns=cols_rnt_limpiar)

                # Preparamos el RNT sumando SOLO la Base CC
                df_r_min = df_r.groupby('DNI_JOIN')[['Base_CC_Anual']].sum().reset_index()
                resultado = pd.merge(resultado, df_r_min, on='DNI_JOIN', how='left')
           
            # 3. UNIÓN NÓMINAS
            if not df_n.empty:
                # Aseguramos normalización del DNI en nóminas
                df_n['DNI_JOIN'] = df_n['DNI'].apply(normalizar_dni_final)
                df_n_min = df_n.groupby('DNI_JOIN')[['AportacionEmpresa']].sum().reset_index()
                # Limpieza preventiva de columna de nómina si ya existe
                if 'AportacionEmpresa' in resultado.columns:
                    resultado = resultado.drop(columns=['AportacionEmpresa'])
                resultado = pd.merge(resultado, df_n_min, on='DNI_JOIN', how='left')

            if not resultado.empty:
                # --- 1. CÁLCULO DE LA SS TEÓRICA ---
                if 'Base_CC_Anual' in resultado.columns and 'Total Cotización (%)' in resultado.columns:
                    # Fórmula: (Base RNT * Porcentaje IDC) / 100
                    resultado['SS a cargo Empresa'] = round(
                        (resultado['Base_CC_Anual'] * resultado['Total Cotización (%)']) / 100, 2
                    )
                # --- 2. CÁLCULO DE COSTES POR HORA ---
                # Verificamos que existan las horas y no sean cero para evitar errores
                if 'Horas Efectivas' in resultado.columns:
                    # Creamos primero 'Coste hora' simple (Percepciones / Horas) para tener la referencia
                    if 'Percepciones' in resultado.columns:
                        resultado['Coste hora'] = round(resultado['Percepciones'] / resultado['Horas Efectivas'], 2)
                    
                    # NUEVA COLUMNA: Coste Hora Real (Dinerarias + SS) / Horas
                    if 'Dinerarias NO IL' in resultado.columns and 'SS a cargo Empresa' in resultado.columns:
                        resultado['Coste Hora Real'] = round(
                            (resultado['Dinerarias NO IL'] + resultado['SS a cargo Empresa']) / resultado['Horas Efectivas'], 2
                        )
                # Limpieza final de columnas técnicas
                if 'DNI_JOIN' in resultado.columns: 
                    resultado.drop(columns=['DNI_JOIN'], inplace=True)
                    
                # --- 🎯 NUEVO: FILTRO DE COLUMNAS PARA DESCARGA ---
                st.markdown("---")
                st.subheader("🛠️ Configuración de Columnas")
                todas_las_columnas = resultado.columns.tolist()
                
                columnas_seleccionadas = st.multiselect(
                    "Selecciona las columnas que deseas incluir en el informe:",
                    options=todas_las_columnas,
                    default=todas_las_columnas  # Por defecto todas están marcadas
                )

                if columnas_seleccionadas:
                    df_exportar = resultado[columnas_seleccionadas]
                    
                    st.subheader("📋 Vista Previa del Informe Personalizado")
                    st.dataframe(df_exportar, use_container_width=True)
                    
                    st.download_button(
                        label="📥 Descargar Informe Personalizado (Excel)",
                        data=to_excel(df_exportar, 'Consolidado'),
                        file_name=f"Auditoria_Personalizada_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        use_container_width=True
                    )
                else:
                    st.warning("⚠️ Selecciona al menos una columna para generar el informe.")

            else:
                st.warning("No hay datos que coincidan con los filtros seleccionados.")
        else:
            st.info("💡 Procesa IDCs y Modelos 190 para ver la unificación detallada.")