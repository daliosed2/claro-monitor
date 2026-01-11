# -*- coding: utf-8 -*-
"""
Vigilante de documentos Claro (sin navegador)
• Notifica SOLO documentos cuya vigencia sea "Vigente"
  y publicados en el mes / año actuales.
• Envía las alertas por consola y por webhook de Discord.

REQUISITOS:
    pip install requests beautifulsoup4 python-dotenv

ARCHIVO .env (en la misma carpeta): 
    DISCORD_WEBHOOK=https://discord.com/api/webhooks/XXXXXXXXXX
"""

import ast
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ---------- CONFIGURACIÓN BÁSICA ---------------------------------------------
URL = "https://www.claro.com.ec/personas/legal-y-regulatorio/"
STATE_FILE = Path("claro_docs.json")
CHECK_INTERVAL = 60 * 60  # segundos (1 h)

# ---------- CARGA VARIABLES DE ENTORNO (.env) --------------------------------
load_dotenv()  # lee .env en la misma carpeta
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

# ---------- FUNCIONES AUXILIARES --------------------------------------------
def es_mes_actual(fecha_dd_mm_yyyy: str) -> bool:
    """True si la fecha (dd-mm-aaaa) está en el mes y año actuales."""
    try:
        f = datetime.strptime(fecha_dd_mm_yyyy, "%d-%m-%Y")
        hoy = datetime.now()
        return f.year == hoy.year and f.month == hoy.month
    except ValueError:
        return False


def es_valido(doc: dict) -> bool:
    """Documento con vigencia 'Vigente' y fecha del mes/año actual."""
    vig = doc.get("vigencia", "").lower().strip()
    return vig.startswith("vigente") and es_mes_actual(doc["publicado"])


def obtener_documentos() -> list[dict]:
    """Extrae los documentos del bloque catalogoArr del HTML."""
    html = requests.get(URL, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", string=lambda t: t and "catalogoArr[" in t)
    if not scripts:
        raise RuntimeError("No se encontró catalogoArr en el HTML")

    patron = re.compile(r"catalogoArr\[\w+\]\s*=\s*({.*?});", re.S)
    docs = []
    for scr in scripts:
        for bloque in patron.findall(scr.string):
            limpio = re.sub(r",\s*}", "}", bloque)  # quita coma colgante
            d_js = ast.literal_eval(limpio)         # dict Python
            docs.append(
                {
                    "id":        d_js.get("fi_documento"),
                    "titulo":    d_js.get("fc_titulo"),
                    "publicado": d_js.get("fd_fecha_publicacion"),
                    "vigencia":  d_js.get("fc_vigencia_descripcion"),
                    "url":       "https://www.claro.com.ec" + d_js.get("fc_url_documento", ""),
                }
            )
    return docs

# ---------- NOTIFICACIÓN: CONSOLA + DISCORD ----------------------------------
def notify(msg: str):
    ts = datetime.now().strftime("[%d/%m %H:%M] ")

    # 👉 Consola: versión sin caracteres raros
    console_msg = re.sub(r"[^\x00-\x7F]", " ", msg)
    print(ts + console_msg)

    # 👉 Discord: mensaje original (UTF-8 completo)
    if DISCORD_WEBHOOK:
        try:
            requests.post(
                DISCORD_WEBHOOK,
                json={"content": msg},          # ← usa msg, no console_msg
                timeout=10,
            )
        except requests.RequestException as e:
            print("Error Discord:", e)

# ---------- MANEJO DE ESTADO -------------------------------------------------
def cargar_estado() -> list[dict]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return []


def guardar_estado(lista: list[dict]):
    actuales = [d for d in lista if es_valido(d)]
    STATE_FILE.write_text(
        json.dumps(actuales, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

# ---------- BUCLE PRINCIPAL --------------------------------------------------
def main():
    conocidos = {d["id"] for d in cargar_estado() if es_valido(d)}
    notify(f"Monitor iniciado. Docs válidos conocidos: {len(conocidos)}")

    try:
        docs = obtener_documentos()
        nuevos = [d for d in docs if d["id"] not in conocidos and es_valido(d)]

        for d in nuevos:
            notify(f"Nuevo documento: {d['titulo']} ({d['publicado']})\n{d['url']}")
            conocidos.add(d["id"])

        if nuevos:
            guardar_estado(docs)
        else:
            notify("Sin novedades en esta pasada")
    except Exception as e:
        notify(f"⚠️ Error general: {e}")

if __name__ == "__main__":
    main()
