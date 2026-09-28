import json
import re
import subprocess
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
CATALOG_FILE = ROOT / "fontes.json"
OUTPUT = ROOT / "mais-sbt.m3u"
DEBUG = ROOT / "descoberto.json"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"

def load():
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))

def normalize(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()

def probe(url):
    # Primeiro tenta um HEAD/GET curto; depois ffprobe.
    try:
        r = requests.get(
            url,
            headers={"User-Agent": UA},
            timeout=12,
            stream=True,
            allow_redirects=True,
        )
        if r.status_code >= 400:
            return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, f"HTTP: {e}"

    try:
        p = subprocess.run(
            [
                "ffprobe",
                "-v","error",
                "-rw_timeout","10000000",
                "-user_agent",UA,
                "-i",url,
                "-show_entries","stream=codec_type",
                "-of","csv=p=0",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
        )
        if p.returncode == 0 and p.stdout.strip():
            return True, "ffprobe OK"
        return False, "ffprobe sem stream"
    except Exception as e:
        return False, f"ffprobe: {e}"

def choose(catalog, streams):
    result=[]
    used=set()

    for item in streams:
        name=item["name"]
        if name not in {x["name"] for x in catalog}:
            continue

        key=(name, item["url"])
        if key in used:
            continue
        used.add(key)

        ok, reason=probe(item["url"])
        row=dict(item)
        row["working"]=ok
        row["test"]=reason

        if ok:
            result.append(row)

    # Um stream por canal, preferindo a primeira URL aprovada.
    final={}
    for row in result:
        final.setdefault(row["name"], row)

    return result, list(final.values())

def main():
    data=load()
    catalog=data["catalogo"]
    streams=data["streams"]

    tested, approved=choose(catalog, streams)

    lines=["#EXTM3U"]

    for item in sorted(approved,key=lambda x:x["name"].lower()):
        cat=next(
            x["category"] for x in catalog if x["name"]==item["name"]
        )
        name=item["name"].replace('"',"'")
        cat=cat.replace('"',"'")

        lines.append(
            f'#EXTINF:-1 tvg-id="{name}" tvg-name="{name}" '
            f'tvg-language="pt-BR" tvg-country="BR" '
            f'group-title="{cat}",{name}'
        )
        lines.append(item["url"])

    OUTPUT.write_text("\n".join(lines)+"\n",encoding="utf-8")

    rejected=[x for x in tested if not x["working"]]

    debug={
        "site":"https://mais.sbt.com.br/",
        "catalogo":catalog,
        "total_catalogo":len(catalog),
        "total_streams_testados":len(tested),
        "total_aprovados":len(approved),
        "streams_aprovados":approved,
        "streams_rejeitados":rejected,
        "observacao":"A descoberta oficial por HTML não é confiável para este site; streams públicos configurados são testados antes da publicação."
    }

    DEBUG.write_text(
        json.dumps(debug,ensure_ascii=False,indent=2),
        encoding="utf-8"
    )

    print("===================================")
    print(" +SBT M3U")
    print("===================================")
    print(f"Catálogo: {len(catalog)}")
    print(f"Streams testados: {len(tested)}")
    print(f"Canais aprovados: {len(approved)}")
    print(f"Playlist: {OUTPUT}")
    print(f"Diagnóstico: {DEBUG}")

    if not approved:
        raise SystemExit("Nenhum stream foi aprovado.")

if __name__=="__main__":
    main()
