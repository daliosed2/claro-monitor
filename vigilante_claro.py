# -*- coding: utf-8 -*-
import os, re
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


def diagnosticar_v3():
    html = requests.get(URL, timeout=30, headers=HEADERS).text
    soup = BeautifulSoup(html, "html.parser")

    # ── 1. Ver los primeros 3 scripts que contienen fc_titulo ────────
    notify("🔍 **=== SCRIPTS CON fc_titulo (primeros 3) ===**")
    count = 0
    for i, s in enumerate(soup.find_all("script", string=True)):
        texto = s.string or ""
        if "fc_titulo" in texto:
            # mostrar los primeros 600 chars del script
            snippet = texto.strip()[:600].replace("\n", " ")
            notify(f"**[script {i}]:** `{snippet}`")
            count += 1
            if count >= 3:
                break

    # ── 2. Buscar el patrón exacto alrededor de fc_titulo ────────────
    notify("📌 **=== CONTEXTO EXACTO DE fc_titulo ===**")
    idx = html.find("fc_titulo")
    if idx != -1:
        fragmento = html[max(0, idx-200):idx+400].replace("\n", " ")
        notify(f"`{fragmento}`")

    # ── 3. Buscar cómo se declara el array/objeto ────────────────────
    notify("🗂️ **=== PATRONES DE ASIGNACIÓN ===**")
    patrones = [
        r"\w+\s*=\s*\[",          # variable = [
        r"\w+\.push\(",            # array.push(
        r"var\s+\w+\s*=\s*\{",    # var x = {
        r"let\s+\w+\s*=\s*\[",    # let x = [
        r"const\s+\w+\s*=\s*\[",  # const x = [
    ]
    for s in soup.find_all("script", string=True):
        texto = s.string or ""
        if "fc_titulo" not in texto:
            continue
        for pat in patrones:
            matches = re.findall(pat, texto[:2000])
            if matches:
                notify(f"  patrón `{pat}` → {matches[:5]}")
        break  # solo el primer script relevante


if __name__ == "__main__":
    notify("🚀 Diagnóstico v3...")
    diagnosticar_v3()
    notify("✅ v3 completo")
