# -*- coding: utf-8 -*-
"""
Vigilante de documentos Claro
- Lee jsonDoc del HTML estático
- Notifica documentos Vigentes del mes actual por Discord
"""

import json, os, re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

URL = "https://www.claro.com.ec/personas/legal-y-regulatorio/"
STATE_FILE = Path("claro_docs.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

load_dotenv()
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")


# ── Helpers ──────────────────────────────────────────────────────────────────

def notify(msg: str):
    ts = datetime.now().strftime("[%d/%m %H:%M] ")
    print(ts + msg)
    if DISCORD_WEBHOOK:
        try:
            requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=10)
        except requests.RequestException as e:
            print("Error Discord:", e)


def es_mes_actual(fecha_dd_mm_yyyy: str) -> bool:
    """True si la fecha (dd-mm-aaaa) está en el mes y año actuales."""
    try:
        f = datetime.strptime(fecha_dd_mm_yyyy, "%d-%m-%Y")
        hoy = datetime.now()
        return f.year == hoy.year and f.month == hoy.month
    except ValueError:
        return False


def es_valido(doc: dict) -> bool:
    """Vigente + publicado en el mes actual."""
    vig = doc.get("fc_vigencia_descripcion", "").lower().strip()
    return vig.startswith("vigente") and es_mes_actual(doc.get("fd_fecha_publicacion", ""))


# ── Extracción ───────────────────────────────────────────────────────────────

def obtener_documentos() -> list[dict]:
    html = requests.get(URL, timeout=30, headers=HEADERS).text
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all("script", string=True):
        texto = script.string or ""
        if "jsonDoc" not in texto:
            continue

        match = re.search(r"var\s+jsonDoc\s*=\s*(\[.*?\]);", texto, re.S)
        if not match:
            continue

        raw = match.group(1)

        # Reparar encoding latin1 mal interpretado (Ã­ → í, etc.)
        raw = raw.encode("latin1", errors="replace").decode("utf-8", errors="replace")

        docs_raw = json.loads(raw)

        return [
            {
                "id":        d.get("fi_documento"),
                "titulo":    d.get("fc_titulo"),
                "publicado": d.get("fd_fecha_publicacion"),
                "vigencia":  d.get("fc_vigencia_descripcion"),
                "tema":      d.get("fc_tema_descripcion"),
                "url":       "https://www.claro.com.ec" + d.get("fc_url_documento", ""),
            }
            for d in docs_raw
        ]

    raise RuntimeError("No se encontró jsonDoc en el HTML")


# ── Estado ───────────────────────────────────────────────────────────────────

def cargar_estado() -> set:
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {d["id"] for d in data}
    return set()


def guardar_estado(docs: list[dict]):
    validos = [d for d in docs if es_valido(d)]
    STATE_FILE.write_text(
        json.dumps(validos, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    conocidos = cargar_estado()
    notify(f"🟢 Monitor iniciado. IDs conocidos: {len(conocidos)}")

    try:
        docs = obtener_documentos()
        notify(f"📄 Documentos totales encontrados: {len(docs)}")

        nuevos = [d for d in docs if d["id"] not in conocidos and es_valido(d)]

        if nuevos:
            for d in nuevos:
                notify(
                    f"🆕 **Nuevo documento**\n"
                    f"📌 {d['titulo']}\n"
                    f"🗂️ Tema: {d['tema']}\n"
                    f"📅 Publicado: {d['publicado']}\n"
                    f"🔗 {d['url']}"
                )
            guardar_estado(docs)
        else:
            notify("✅ Sin novedades en esta pasada")

    except Exception as e:
        notify(f"⚠️ Error: {e}")


if __name__ == "__main__":
    main()
