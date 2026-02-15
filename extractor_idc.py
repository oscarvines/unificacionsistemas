import pdfplumber
import re
from datetime import datetime, timedelta

def extraer_datos_idc(file_object):
    resultados = []
    # Obtenemos el nombre del archivo para usarlo en caso de error en la lectura
    nombre_archivo_raw = getattr(file_object, 'name', 'Archivo desconocido')
    
    with pdfplumber.open(file_object) as pdf:
        texto_completo = ""
        for page in pdf.pages: texto_completo += page.extract_text() + "\n"

        # Detección de Autónomos
        es_autonomo = any(x in texto_completo for x in ["Cuenta Propia", "AUTÓNOMOS"])

        if es_autonomo:
            # Procesamiento por páginas para autónomos
            for page in pdf.pages:
                texto_pag = page.extract_text()
                if not texto_pag: continue
                
                nombre_m = re.search(r"NOMBRE Y APELLIDOS:\s*([^\n]*)", texto_pag)
                # AJUSTE: Si no hay nombre, indica el archivo
                nombre = nombre_m.group(1).strip() if nombre_m else f"DESCONOCIDO ({nombre_archivo_raw})"
                
                dni_m = re.search(r"DOC\.\s*IDENTIFICATIVO:.*?NÚM\.:\s*([A-Z0-9]+)", texto_pag, re.DOTALL)
                dni_trabajador = dni_m.group(1).strip() if dni_m else "N/A"
                per_m = re.search(r"PERIODO LIQUIDACIÓN:.*?(\d{2})/(\d{4})", texto_pag)
                if per_m:
                    mes, anio = int(per_m.group(1)), int(per_m.group(2))
                    f_desde = datetime(anio, mes, 1)
                    f_hasta = (datetime(anio, mes, 28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                    resultados.append({
                        "Nombre": nombre, "DNI_Trabajador": dni_trabajador, "NIF_Empresa": "PENDIENTE",
                        "Empresa": "PENDIENTE", "CTP": 0, "Es_Autonomo": True,
                        "Desde_Info": f_desde, "Hasta_Info": f_hasta, "Inicio_Contrato": f_desde,
                        "Tramos_IT": [], "Alta": f_desde.strftime("%d-%m-%Y"), "Baja": "ACTIVO"
                    })
        else:
            # TU LÓGICA ORIGINAL DE PRODUCCIÓN
            # 1. Nombre (AJUSTE: Ahora incluye nombre de archivo si falla el Regex)
            nombre_m = re.search(r"NOMBRE Y APELLIDOS:\s*(.*)", texto_completo)
            nombre = nombre_m.group(1).strip() if nombre_m else f"DESCONOCIDO ({nombre_archivo_raw})"

            # 2. DNI Trabajador
            dni_m = re.search(r"NUM:\s*([A-Z0-9]+)", texto_completo)
            dni_trabajador = dni_m.group(1).strip() if dni_m else "N/A"

            # 3. Empresa
            empresa_m = re.search(r"RAZÓN SOCIAL:\s*(.*?)\s*CCC:", texto_completo)
            razon_social = empresa_m.group(1).strip() if empresa_m else "DESCONOCIDA"

            # 4. CIF Empresa
            cif_emp_m = re.search(r"DNI/NIE/CIF:\s*[\d\s]*([A-Z0-9]{9})", texto_completo)
            nif_empresa = cif_emp_m.group(1).strip() if cif_emp_m else "N/A"

            # 5. Alta (Evita error si no encuentra la palabra ALTA)
            alta_m = re.search(r"ALTA:\s*(\d{2}-\d{2}-\d{4})", texto_completo)
            alta = alta_m.group(1).strip() if alta_m else "01-01-2000"
            
            # Captura de Inicio Contrato según el patrón de Claudia
            inicio_con_m = re.search(r"INICIO CONTRATO DE TRABAJO.*?FECHA:\s*(\d{2}-\d{2}-\d{4})", texto_completo, re.DOTALL)
            inicio_contrato = inicio_con_m.group(1).strip() if inicio_con_m else alta

            baja_m = re.search(r"BAJA:\s*(\d{2}-\d{2}-\d{4})", texto_completo)
            baja = baja_m.group(1).strip() if baja_m else "ACTIVO"
            ctp = 0
            ctp_m = re.search(r"COEF\.?\s*TIEMPO\s*PARCIAL:\s*(\d+)", texto_completo, re.IGNORECASE)
            if ctp_m: ctp = int(ctp_m.group(1))

            per_m = re.search(r"PERIODO:\s*DESDE\s*(\d{2}-\d{2}-\d{4})(?:\s*HASTA\s*(\d{2}-\d{2}-\d{4}))?", texto_completo)
            f_desde_info = datetime.strptime(per_m.group(1), "%d-%m-%Y") if per_m else datetime.strptime(alta, "%d-%m-%Y")
            f_hasta_info = datetime.strptime(per_m.group(2), "%d-%m-%Y") if (per_m and per_m.group(2)) else datetime(2099, 12, 31)

            tramos_it = []
            if "TIPO DE PECULIARIDAD" in texto_completo:
                bloque = texto_completo.split("TIPO DE PECULIARIDAD")[1].split("***")[0]
                for linea in bloque.split("\n"):
                    if any(x in linea.upper() for x in ["IT.", "ENFERMEDAD", "ACCIDENTE", "22 ", "29 ", "BUI"]):
                        fechas = re.findall(r"(\d{2}-\d{2}-\d{4})", linea)
                        if len(fechas) >= 2:
                            tramos_it.append((datetime.strptime(fechas[-2], "%d-%m-%Y"), datetime.strptime(fechas[-1], "%d-%m-%Y")))

            resultados.append({
                "Nombre": nombre, "DNI_Trabajador": dni_trabajador, "NIF_Empresa": nif_empresa,
                "Empresa": razon_social, "CTP": ctp, "Es_Autonomo": False,
                "Desde_Info": f_desde_info, "Hasta_Info": f_hasta_info,
                "Inicio_Contrato": datetime.strptime(inicio_contrato, "%d-%m-%Y"),
                "Tramos_IT": tramos_it, "Alta": alta, "Baja": baja
            })
    return resultados, texto_completo