# -*- coding: utf-8 -*-
import ast, json, os, re, time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

URL = "https://www.claro.com.ec/personas/legal-y-regulatorio/"
STATE_FILE = Path("claro_docs.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

load_dotenv()
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")


def es_mes_actual(fecha_dd_mm_yyyy: str) -> bool:
    try:
        f = datetime.strptime(fecha_dd_mm_yyyy, "%d-%m-%Y")
        hoy = datetime.now()
        return f.year == hoy.year and f.month == hoy.month
    except ValueError:
        return False


def es_valido(doc: dict) -> bool:
    vig = doc.get("vigencia", "").lower().strip()
    return vig.startswith("vigente") and es_mes_actual(doc["publicado"])


def obtener_documentos() -> list[dict]:
    html = requests.get(URL, timeout=20, headers=HEADERS).text
    soup = BeautifulSoup(html, "html.parser")

    scripts_inline = soup.find_all("script", string=True)
    notify(f"🔍 Scripts inline encontrados: {len(scripts_inline)}")

    # Buscar catalogoArr o variantes
    scripts = [s for s in scripts_inline if "catalogoArr" in (s.string or "")]

    if not scripts:
        # mostrar primeras líneas de cada script para debug
        for i, s in enumerate(scripts_inline[:5]):
            snippet = (s.string or "")[:150].replace("\n", " ")
            notify(f"  script[{i}]: {snippet}")
        raise RuntimeError("No se encontró catalogoArr en el HTML")

    patron = re.compile(r"catalogoArr\[\w+\]\s*=\s*({.*?});", re.S)
    docs = []
    for scr in scripts:
        for bloque in patron.findall(scr.string):
            limpio = re.sub(r",\s*}", "}", bloque)
            d_js = ast.literal_eval(limpio)
            docs.append({
                "id":        d_js.get("fi_documento"),
                "titulo":    d_js.get("fc_titulo"),
                "publicado": d_js.get("fd_fecha_publicacion"),
                "vigencia":  d_js.get("fc_vigencia_descripcion"),
                "url":       "https://www.claro.com.ec" + d_js.get("fc_url_documento", ""),
            })
    return docs


def notify(msg: str):
    ts = datetime.now().strftime("[%d/%m %H:%M] ")
    console_msg = re.sub(r"[^\x00-\x7F]", " ", msg)
    print(ts + console_msg)
    if DISCORD_WEBHOOK:
        try:
            requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=10)
        except requests.RequestException as e:
            print("Error Discord:", e)


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


def main():
    conocidos = {d["id"] for d in cargar_estado() if es_valido(d)}
    notify(f"Monitor iniciado. Docs válidos conocidos: {len(conocidos)}")

    try:
        docs = obtener_documentos()
        nuevos = [d for d in docs if d["id"] not in conocidos and es_valido(d)]

        for d in nuevos:
            notify(f"📄 Nuevo documento: {d['titulo']} ({d['publicado']})\n{d['url']}")
            conocidos.add(d["id"])

        if nuevos:
            guardar_estado(docs)
        else:
            notify("✅ Sin novedades en esta pasada")
    except Exception as e:
        notify(f"⚠️ Error general: {e}")


if __name__ == "__main__":
    main()
