import asyncio
import re
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

BASE_URL = "https://mais.sbt.com.br/"
OUTPUT = Path("mais-sbt.m3u")

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)

# Termos que ajudam a separar páginas de conteúdo de páginas de canais.
CHANNEL_HINTS = (
    "/channel/",
    "/canais/",
    "/canal/",
)

# Categorias conhecidas do ecossistema +SBT.
CATEGORY_RULES = [
    ("Novelas", ("novela", "novelas")),
    ("Infantil", ("kids", "infantil", "desenho", "bob zoom")),
    ("Notícias", ("news", "notícia", "noticias")),
    ("Entretenimento", ("entretenimento", "programas", "variedades")),
    ("Filmes e Séries", ("filme", "filmes", "série", "series")),
    ("Esportes", ("esporte", "sports")),
]

def clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value

def normalize_name(value: str) -> str:
    value = clean_text(value)
    value = re.sub(r"^\+SBT\s*[-|:]\s*", "", value, flags=re.I)
    return value[:120]

def category_for(name: str) -> str:
    low = name.lower()
    for category, terms in CATEGORY_RULES:
        if any(term in low for term in terms):
            return category
    return "Entretenimento"

def is_hls(url: str) -> bool:
    low = url.lower()
    return ".m3u8" in low and url.startswith(("http://", "https://"))

def same_host(url: str) -> bool:
    try:
        return urlparse(url).netloc.endswith("sbt.com.br") or \
               "s73cloud.com" in urlparse(url).netloc
    except Exception:
        return False

def stream_score(url: str) -> int:
    low = url.lower()
    score = 0
    if ".m3u8" in low:
        score += 100
    if "live" in low:
        score += 10
    if "master" in low:
        score += 8
    if "playlist" in low:
        score += 5
    if "manifest" in low:
        score += 4
    return score

def ffprobe_ok(url: str) -> bool:
    """
    Testa o manifesto HLS sem reproduzir o conteúdo.
    Não tenta remover DRM nem contornar proteção.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-rw_timeout", "8000000",
                "-user_agent", UA,
                "-i", url,
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False

async def get_page_info(page):
    title = clean_text(await page.title())

    # Tenta os elementos mais comuns de título.
    candidates = []
    for selector in ("h1", "h2", "[data-testid*='title']", "[class*='title']"):
        try:
            texts = await page.locator(selector).all_inner_texts()
            candidates.extend(texts)
        except Exception:
            pass

    name = ""
    for item in candidates:
        item = normalize_name(item)
        if 2 <= len(item) <= 100:
            name = item
            break

    if not name:
        name = normalize_name(title)

    if not name or name.lower() in {"+sbt", "sbt"}:
        name = "SBT"

    return name, category_for(name)

async def collect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        context = await browser.new_context(
            user_agent=UA,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1440, "height": 900},
        )

        page = await context.new_page()
        discovered = {}

        async def capture_response(response):
            url = response.url
            if is_hls(url):
                # Ignora manifestos claramente associados a anúncios.
                low = url.lower()
                if "/preroll/" in low or "adserver" in low:
                    return
                discovered.setdefault(url, {
                    "source": response.url,
                    "name": "",
                    "category": "Entretenimento",
                })

        page.on("response", capture_response)

        print("Abrindo +SBT...")
        try:
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            print(f"Aviso ao abrir página inicial: {exc}")

        await page.wait_for_timeout(8000)

        # Coleta links de canais presentes na página.
        hrefs = await page.locator("a").evaluate_all(
            """els => els.map(a => a.href).filter(Boolean)"""
        )

        channel_urls = []
        for href in hrefs:
            if any(h in href.lower() for h in CHANNEL_HINTS):
                if href.startswith("https://mais.sbt.com.br/"):
                    channel_urls.append(href.split("#")[0])

        # Também usa links que apareceram em elementos de vídeo/players.
        channel_urls = sorted(set(channel_urls))
        print(f"Páginas de canais descobertas: {len(channel_urls)}")

        # Caso a home já tenha carregado um canal ao vivo, mantém os manifests capturados.
        pages_to_visit = channel_urls[:80]

        for idx, url in enumerate(pages_to_visit, 1):
            print(f"[{idx}/{len(pages_to_visit)}] {url}")
            ch = await context.new_page()
            ch.on("response", capture_response)

            try:
                await ch.goto(url, wait_until="domcontentloaded", timeout=45000)
                await ch.wait_for_timeout(5000)

                name, category = await get_page_info(ch)

                # Associa os manifestos descobertos mais recentemente ao canal.
                for stream_url, item in discovered.items():
                    if not item["name"]:
                        item["name"] = name
                        item["category"] = category

            except Exception as exc:
                print(f"  erro: {exc}")
            finally:
                await ch.close()

        await browser.close()

    # Remove duplicados e ordena pelo nome.
    records = []
    for url, item in discovered.items():
        name = normalize_name(item.get("name") or "SBT")
        if not name:
            continue
        records.append({
            "name": name,
            "category": item.get("category") or category_for(name),
            "url": url,
        })

    # Se vários manifests foram capturados para o mesmo canal, fica com o primeiro.
    unique = {}
    for item in records:
        key = (item["name"].lower(), item["category"].lower())
        if key not in unique or stream_score(item["url"]) > stream_score(unique[key]["url"]):
            unique[key] = item

    return list(unique.values())

def write_playlist(items):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    lines = ["#EXTM3U"]

    for item in sorted(items, key=lambda x: (x["category"], x["name"])):
        name = item["name"].replace('"', "'")
        category = item["category"].replace('"', "'")
        url = item["url"]

        lines.append(
            f'#EXTINF:-1 tvg-id="{name}" tvg-name="{name}" '
            f'tvg-language="pt-BR" tvg-country="BR" '
            f'group-title="{category}",{name}'
        )
        lines.append(url)

    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

def main():
    items = asyncio.run(collect())

    print(f"Streams HLS encontrados: {len(items)}")

    valid = []
    for idx, item in enumerate(items, 1):
        print(f"Teste {idx}/{len(items)}: {item['name']}")
        if ffprobe_ok(item["url"]):
            print("  OK")
            valid.append(item)
        else:
            print("  FALHOU — removido")

    write_playlist(valid)
    print(f"Playlist gerada: {OUTPUT}")
    print(f"Canais ativos publicados: {len(valid)}")

if __name__ == "__main__":
    main()
