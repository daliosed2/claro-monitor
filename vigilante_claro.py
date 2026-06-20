# -*- coding: utf-8 -*-
"""
Vigilante de documentos Claro (Versión Híbrida Inteligente - Producción)
- Intenta leer jsonDoc del HTML estático de forma elástica.
- Si falla, extrae los enlaces PDF directamente del HTML y busca fechas con Regex.
- Traduce automáticamente timestamps de 13 dígitos en las URLs a fechas reales.
- Notifica documentos Vigentes del mes actual por Discord.
"""

import json
import os
import re
import hashlib
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# --- Configuración ---
URL = "https://www.claro.com.ec/personas/legal-y-regulatorio/"
STATE_FILE = Path("claro_docs.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

load_dotenv()
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")


# ── Helpers de Notificación y Fechas ─────────────────────────────────────────

def notify(msg: str):
    """Imprime el mensaje en consola y lo envía a Discord si el Webhook está configurado."""
    ts = datetime.now().strftime("[%d/%m %H:%M] ")
    print(ts + msg)
    if DISCORD_WEBHOOK:
        try:
            requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=10)
        except requests.RequestException as e:
            print("Error Discord:", e)


def parsear_fecha(fecha_str: str) -> datetime or None:
    """
    Intenta parsear una fecha en múltiples formatos (ISO, latino, timestamp, etc.).
    Retorna un objeto datetime o None si es imposible de identificar.
    """
    if not fecha_str:
        return None
    
    fecha_str = str(fecha_str).strip()
    
    # Caso 1: Identificar si es un timestamp unix/milisegundos puro (10 a 13 dígitos)
    if re.match(r"^\d{10,13}$", fecha_str):
        try:
            val = int(fecha_str)
            if val > 10000000000:  # Convertir milisegundos a segundos
                val = val / 1000
            return datetime.fromtimestamp(val)
        except Exception:
            pass

    # Caso 2: Formatos de fecha de texto comunes
    formatos = [
        "%d-%m-%Y", "%Y-%m-%d",
        "%d/%m/%Y", "%Y/%m/%d",
        "%d-%m-%y", "%y-%m-%d",
        "%d/%m/%y", "%y/%m/%d"
    ]
    for fmt in formatos:
        try:
            return datetime.strptime(fecha_str, fmt)
        except ValueError:
            continue
            
    return None


def es_mes_actual(fecha_str: str) -> bool:
    """True si la fecha corresponde al mes y año del sistema en curso."""
    dt = parsear_fecha(fecha_str)
    if not dt:
        return False
    hoy = datetime.now()
    return dt.year == hoy.year and dt.month == hoy.month


def extraer_fecha_documento(doc: dict) -> str:
    """
    Estrategia de extracción de fecha multinivel.
    Si el campo 'publicado' no es válido, busca timestamps o fechas en la propia URL del PDF.
    """
    # 1. Intentar usar la fecha declarada directamente en el JSON
    pub = doc.get("publicado")
    if pub and parsear_fecha(str(pub)):
        return str(pub)
    
    # 2. Buscar si la URL contiene un timestamp de 13 dígitos (milisegundos como 1781710323264)
    url = doc.get("url", "")
    ts_match = re.search(r"(\d{13})", url)
    if ts_match:
        return ts_match.group(1)
        
    # 3. Buscar si la URL contiene una fecha formateada (YYYY-MM-DD o DD-MM-YYYY)
    fecha_match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})|(\d{2}[-/]\d{2}[-/]\d{4})", url)
    if fecha_match:
        return fecha_match.group(0)
        
    return ""


def es_valido(doc: dict) -> bool:
    """Filtra únicamente documentos vigentes y publicados en el mes actual."""
    vig = (doc.get("vigencia") or "").lower().strip()
    # Si no tiene etiqueta de vigencia, por seguridad lo consideramos vigente
    es_vigente = "vigente" in vig or vig == "" or "html" in vig
    
    fecha_evaluar = extraer_fecha_documento(doc)
    return es_vigente and es_mes_actual(fecha_evaluar)


# ── Parseo Elástico de Datos (Tolerante a fallos de sintaxis JS) ─────────────

def parsear_js_rustico(raw_str: str) -> list[dict]:
    """
    Parsea de forma manual estructuras JS de objetos cuando fallan los deserializadores de JSON.
    Extrae pares clave-valor utilizando expresiones regulares.
    """
    objetos = re.findall(r'\{([^}]+)\}', raw_str, re.S)
    resultado = []
    for obj_content in objetos:
        item = {}
        # Busca cualquier patrón del tipo clave : 'valor' o clave : "valor" o clave : 123
        pares = re.findall(r'(?:"?([a-zA-Z0-9_]+)"?)\s*:\s*(?:"([^"]*)"|\'([^\']*)\'|([0-9.]+)|(true|false|null))', obj_content)
        for k, val_double, val_single, val_num, val_bool in pares:
            if val_double:
                item[k] = val_double
            elif val_single:
                item[k] = val_single
            elif val_num:
                item[k] = int(val_num) if '.' not in val_num else float(val_num)
            elif val_bool:
                item[k] = True if val_bool == 'true' else False if val_bool == 'false' else None
        if item:
            resultado.append(item)
    return resultado


def safe_json_loads(raw_str: str) -> list[dict]:
    """Intenta deserializar un JSON de forma segura, reparando fallos comunes de JavaScript."""
    try:
        return json.loads(raw_str)
    except json.JSONDecodeError:
        pass
    
    # Reparar claves sin comillas típicas de objetos JS ({titulo: "hola"} -> {"titulo": "hola"})
    reparado = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', raw_str)
    # Reparar comillas simples externas a comillas dobles
    reparado = re.sub(r"'\s*([^']*?)\s*'", r'"\1"', reparado)
    
    try:
        return json.loads(reparado)
    except json.JSONDecodeError:
        # Último recurso: Parseo regex elástico
        return parsear_js_rustico(raw_str)


# ── Extracción Híbrida ───────────────────────────────────────────────────────

def obtener_documentos() -> list[dict]:
    """Obtiene los documentos usando extracción por JSON (primario) o HTML (secundario)."""
    try:
        respuesta = requests.get(URL, timeout=30, headers=HEADERS)
        respuesta.raise_for_status()
        html = respuesta.text
    except requests.RequestException as e:
        raise RuntimeError(f"Error de conexión con la página de Claro: {e}")

    soup = BeautifulSoup(html, "html.parser")
    docs = []

    # === INTENTO 1: Buscar variable jsonDoc (JS Dinámico) ===
    for script in soup.find_all("script", string=True):
        texto = script.string or ""
        if "jsonDoc" in texto:
            # Captura ultra-flexible sin importar si declara con var/let/const/window ni el espaciado
            match = re.search(r"jsonDoc\s*=\s*(\[.*?\])\s*(?:;|\n|$)", texto, re.S | re.I)
            if not match:
                continue

            try:
                raw = match.group(1)
                # Reparar encoding latin1 mal interpretado (evita caracteres corruptos)
                raw = raw.encode("latin1", errors="replace").decode("utf-8", errors="replace")
                docs_raw = safe_json_loads(raw)
                
                for d in docs_raw:
                    url_doc = d.get("fc_url_documento", "")
                    # Normalizar construcción de URL absoluta
                    if url_doc and not url_doc.startswith("http"):
                        if not url_doc.startswith("/"):
                            url_doc = "/" + url_doc
                        url_completa = "https://www.claro.com.ec" + url_doc
                    else:
                        url_completa = url_doc

                    docs.append({
                        "id": str(d.get("fi_documento") or hashlib.md5(url_completa.encode("utf-8")).hexdigest()[:12]),
                        "titulo": d.get("fc_titulo"),
                        "publicado": d.get("fd_fecha_publicacion"),
                        "vigencia": d.get("fc_vigencia_descripcion"),
                        "tema": d.get("fc_tema_descripcion"),
                        "url": url_completa,
                        "metodo": "JSON"
                    })
                
                notify("🎯 Éxito: Se parseó el repositorio legal usando la estructura jsonDoc.")
                return docs
            except Exception as json_err:
                print(f"[Aviso] Fallo al parsear JSON interno: {json_err}. Probando otras opciones...")

    # === INTENTO 2: Fallback Robusto (Scraping directo del DOM) ===
    notify("⚠️ Advertencia: No se pudo extraer la variable jsonDoc. Iniciando scraping directo de enlaces HTML...")
    
    enlaces = soup.find_all("a", href=True)
    for link in enlaces:
        href = link["href"]
        if ".pdf" in href.lower():
            # Construir URL absoluta robusta
            url_completa = href
            if href.startswith("/"):
                url_completa = "https://www.claro.com.ec" + href
            elif not href.startswith("http"):
                url_completa = "https://www.claro.com.ec/personas/legal-y-regulatorio/" + href

            texto_enlace = link.get_text(strip=True)
            texto_padre = link.parent.get_text(strip=True) if link.parent else ""
            texto_analizar = f"{texto_enlace} {texto_padre}"

            # Intentar buscar fechas en el texto adyacente (ej. 15-06-2026)
            fecha_match = re.search(r"\b(\d{2})[-/](\d{2})[-/](\d{4})\b", texto_analizar)
            if fecha_match:
                fecha_doc = f"{fecha_match.group(1)}-{fecha_match.group(2)}-{fecha_match.group(3)}"
            else:
                fecha_doc = ""

            titulo = texto_enlace
            if not titulo:
                titulo = href.split("/")[-1].replace(".pdf", "").replace("-", " ").replace("_", " ").title()

            doc_id = hashlib.md5(url_completa.encode("utf-8")).hexdigest()[:12]

            docs.append({
                "id": doc_id,
                "titulo": titulo,
                "publicado": fecha_doc,
                "vigencia": "Vigente (HTML)",
                "tema": "Regulatorio",
                "url": url_completa,
                "metodo": "HTML"
            })

    if docs:
        notify(f"🎯 Éxito: Se extrajeron {len(docs)} enlaces PDF directamente desde el HTML estático.")
        return docs

    raise RuntimeError("No se pudo extraer ningún documento legal ni por JSON ni por estructura HTML.")


# ── Gestión de Historial (Estado) ────────────────────────────────────────────

def cargar_estado() -> set:
    """Carga los IDs de documentos ya procesados para evitar alertas duplicadas."""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if data and isinstance(data[0], dict):
                return {d["id"] for d in data}
            return set(data)
        except Exception:
            return set()
    return set()


def guardar_estado(docs: list[dict]):
    """Guarda los documentos válidos actuales en el archivo de estado."""
    validos = [d for d in docs if es_valido(d)]
    STATE_FILE.write_text(
        json.dumps(validos, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Controlador Principal ────────────────────────────────────────────────────

def main():
    conocidos = cargar_estado()
    notify(f"🟢 Monitor Claro Iniciado. Registros conocidos en caché: {len(conocidos)}")

    try:
        docs = obtener_documentos()
        notify(f"📄 Documentos totales procesados en el portal: {len(docs)}")

        # Filtrar documentos que correspondan al mes actual y no estén registrados en caché
        nuevos = [d for d in docs if d["id"] not in conocidos and es_valido(d)]

        if nuevos:
            for d in nuevos:
                fecha_limpia = parsear_fecha(extraer_fecha_documento(d))
                fecha_mostrar = fecha_limpia.strftime("%d-%m-%Y") if fecha_limpia else "No identificada"
                
                notify(
                    f"🆕 **Nuevo documento legal encontrado (Claro)**\n"
                    f"📌 **Título:** {d['titulo']}\n"
                    f"🗂️ **Tema:** {d['tema']}\n"
                    f"📅 **Publicación:** {fecha_mostrar} *(Método: {d['metodo']})*\n"
                    f"🔗 **Enlace directo:** {d['url']}"
                )
            guardar_estado(docs)
        else:
            notify("✅ Sin novedades en esta pasada para Claro.")

    except Exception as e:
        notify(f"⚠️ Error crítico en el monitor de Claro: {e}")


if __name__ == "__main__":
    main()
