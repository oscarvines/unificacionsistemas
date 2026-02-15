import pdfplumber
import pandas as pd
import re
import os

def limpiar_monto(texto):
    if not texto: return 0.0
    limpio = re.sub(r'[^0-9,.]', '', texto)
    if not limpio: return 0.0
    limpio = limpio.replace('.', '').replace(',', '.')
    try:
        return float(limpio)
    except:
        return 0.0

def extraer_por_instancia(bloque, etiqueta, instancia):
    try:
        matches = [m.start() for m in re.finditer(re.escape(etiqueta), bloque)]
        if len(matches) >= instancia:
            punto_inicio = matches[instancia-1]
            fragmento = bloque[punto_inicio:punto_inicio+200]
            num_match = re.search(r'(\d{1,3}(\.\d{3})*,\d{2})', fragmento)
            if num_match:
                return limpiar_monto(num_match.group(1))
    except:
        pass
    return 0.0

def extraer_datos_190(file_object):
    resultados = []
    
    if hasattr(file_object, 'name'):
        nombre_archivo = file_object.name
    else:
        nombre_archivo = os.path.basename(file_object)
    
    with pdfplumber.open(file_object) as pdf:
        for page in pdf.pages:
            texto = page.extract_text()
            if not texto: continue
            
            bloques = re.split(r'Percepción\s+\d+', texto)
            
            for bloque in bloques[1:]:
                # --- RIGOR EN NIF/NIE/CIF ---
                # Acepta: 8núm+letra O letra+7/8 caracteres (cubre E de notarías, XYZ de extranjeros, etc.)
                match_id = re.search(r'([A-Z0-9][0-9A-Z]{7,8})\s+(.*?)\s+(\d{2})', bloque)
                if not match_id: continue
                
                nif = match_id.group(1)
                nombre = match_id.group(2).strip()
                
                # --- EXTRACCIÓN DE CLAVES ---
                clave_match = re.search(r'Clave:\s*([A-Z])', bloque)
                clave = clave_match.group(1) if clave_match else ""
                
                subclave_match = re.search(r'Subclave:\s*(\d{2})', bloque)
                subclave = subclave_match.group(1) if subclave_match else ""
                
                # --- TU LÓGICA DE IMPORTES ORIGINAL ---
                d_no_il = extraer_por_instancia(bloque, "Percepción íntegra", 1)
                e_no_il = extraer_por_instancia(bloque, "Valoración", 1)
                d_il = extraer_por_instancia(bloque, "Percepción íntegra", 2)
                e_il = extraer_por_instancia(bloque, "Valoración", 2)

                resultados.append({
                    "Archivo": nombre_archivo,
                    "NIF": nif,
                    "Nombre": nombre,
                    "Clave": clave,
                    "Subclave": subclave,
                    "Dinerarias NO IL": d_no_il,
                    "Especie NO IL": e_no_il,
                    "Dinerarias IL": d_il,
                    "Especie IL": e_il
                })
    return resultados