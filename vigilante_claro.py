# -*- coding: utf-8 -*-
import json, os, re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

URL = "https://www.claro.com.ec/personas/legal-y-regulatorio/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

load_dotenv()
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")


def notify(msg: str):
    ts = datetime.now().strftime("[%d/%m %H:%M] ")
    print(ts + msg)
    if DISCORD_WEBHOOK:
        try:
            requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=10)
        except requests.RequestException as e:
            print("Error Discord:", e)


def diagnosticar_pagina():
    html = requests.get(URL, timeout=30, headers=HEADERS).text
    soup = BeautifulSoup(html, "html.parser")

    # ── 1. Buscar palabras clave del nuevo formato ───────────────────
    notify("🔎 **=== PALABRAS CLAVE NUEVAS ===**")
    claves = [
        "fc_titulo", "fi_documento", "fd_fecha", "fc_vigencia",
        "vigente", "Vigente", "fc_url_documento",
        "fecha_publicacion", "documentos", "regulatorio",
        "\"titulo\"", "\"vigencia\"", "\"publicado\"",
        "XMLHttpRequest", "url:", "endpoint",
    ]
    for clave in claves:
        count = html.count(clave)
        if count > 0:
            notify(f"  ✅ '{clave}' aparece {count} veces")
        else:
            notify(f"  ❌ '{clave}' no encontrado")

    # ── 2. Buscar en scripts inline palabras relacionadas ────────────
    notify("📝 **=== SCRIPTS CON 'legal' o 'documento' ===**")
    for i, s in enumerate(soup.find_all("script", string=True)):
        texto = s.string or ""
        if any(k in texto.lower() for k in ["legal", "documento", "vigencia", "regulatorio", "xhr", "xmlhttprequest"]):
            snippet = texto.strip()[:500].replace("\n", " ")
            notify(f"  [script {i}]: {snippet}")

    # ── 3. Buscar tablas o divs con documentos ───────────────────────
    notify("📋 **=== TABLAS EN LA PÁGINA ===**")
    tablas = soup.find_all("table")
    notify(f"  Tablas encontradas: {len(tablas)}")
    for i, t in enumerate(tablas[:3]):
        snippet = t.get_text(separator=" | ", strip=True)[:300]
        notify(f"  tabla[{i}]: {snippet}")

    # ── 4. Buscar divs o elementos con clase relacionada ────────────
    notify("🗂️ **=== DIVS CON CLASE 'legal' o 'doc' ===**")
    for tag in soup.find_all(True, class_=re.compile(r"legal|doc|regulat|vigencia", re.I)):
        snippet = tag.get_text(strip=True)[:200]
        clase = tag.get("class")
        notify(f"  <{tag.name} class={clase}>: {snippet}")

    # ── 5. Muestra fragmento del HTML donde aparece 'Vigente' ────────
    notify("📌 **=== CONTEXTO DONDE APARECE 'Vigente' ===**")
    idx = html.find("Vigente")
    if idx != -1:
        fragmento = html[max(0, idx-300):idx+300].replace("\n", " ")
        notify(f"  ...{fragmento}...")
    else:
        notify("  'Vigente' no encontrado en HTML")

    notify(f"📄 HTML total: {len(html):,} caracteres")


if __name__ == "__main__":
    notify("🚀 Iniciando diagnóstico v2...")
    diagnosticar_pagina()
    notify("✅ Diagnóstico v2 completo")
