# -*- coding: utf-8 -*-
import json, os, re
from datetime import datetime
from pathlib import Path

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
    html = requests.get(URL, timeout=20, headers=HEADERS).text
    soup = BeautifulSoup(html, "html.parser")

    # ── 1. Scripts externos ──────────────────────────────────────────
    notify("📦 **=== SCRIPTS EXTERNOS ===**")
    for tag in soup.find_all("script", src=True):
        src = tag.get("src", "")
        notify(f"  `{src}`")

    # ── 2. Scripts inline (primeros 10) ─────────────────────────────
    notify("📝 **=== SCRIPTS INLINE ===**")
    for i, s in enumerate(soup.find_all("script", string=True)[:10]):
        texto = (s.string or "").strip()[:300].replace("\n", " ")
        notify(f"  [{i}] {texto}")

    # ── 3. Posibles endpoints API en todo el HTML ────────────────────
    notify("🔗 **=== POSIBLES ENDPOINTS API ===**")
    apis = re.findall(
        r'(https?://[^\s"\'<>]+(?:json|api|legal|catalogo|documento)[^\s"\'<>]*)',
        html,
        re.IGNORECASE,
    )
    for a in sorted(set(apis)):
        notify(f"  {a}")

    # ── 4. Palabras clave en el HTML ─────────────────────────────────
    notify("🔎 **=== PALABRAS CLAVE EN HTML ===**")
    claves = ["catalogoArr", "fc_titulo", "fi_documento", "fetch(", "XMLHttpRequest", "axios"]
    for clave in claves:
        encontrado = "✅ SÍ" if clave in html else "❌ NO"
        notify(f"  {clave}: {encontrado}")

    # ── 5. Tamaño del HTML recibido ──────────────────────────────────
    notify(f"📄 **Tamaño HTML:** {len(html):,} caracteres")


if __name__ == "__main__":
    notify("🚀 Iniciando diagnóstico de Claro...")
    diagnosticar_pagina()
    notify("✅ Diagnóstico completo")
