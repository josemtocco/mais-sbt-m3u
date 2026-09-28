import asyncio
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

BASE = "https://mais.sbt.com.br/"
OUTPUT = Path("mais-sbt.m3u")
DEBUG = Path("descoberto.json")

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)

# Canais atualmente identificados no serviço. Eles servem como referência
# de nome/categoria; os links reais continuam sendo descobertos no site.
KNOWN = {
    "sbt": ("SBT", "SBT"),
    "sbt rio": ("SBT Rio", "Regional"),
    "sbt news": ("SBT News", "Notícias"),
    "sbt novelas": ("+SBT Novelas", "Novelas"),
    "novelas": ("+SBT Novelas", "Novelas"),
    "show do milhão": ("Canal Show do Milhão", "Entretenimento"),
    "sbt kids": ("SBT Kids", "Infantil"),
}

def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def channel_name(text):
    t = clean(text)
    low = t.lower()

    for key, value in KNOWN.items():
        if key in low:
            return value

    t = re.sub(r"^\+?sbt\s*[-|:]\s*", "", t, flags=re.I)
    t = clean(t)
    return t[:100] if t else "SBT"

def category(name):
    low = name.lower()
    if "news" in low or "notícia" in low:
        return "Notícias"
    if "novela" in low:
        return "Novelas"
    if "kids" in low or "infantil" in low:
        return "Infantil"
    if "rio" in low or "regional" in low:
        return "Regional"
    if "milhão" in low:
        return "Entretenimento"
    return "SBT"

def valid_stream(url):
    if not url or not url.startswith(("http://", "https://")):
        return False
    low = url.lower()
    if ".m3u8" in low:
        return True
    # Alguns players usam URLs de CDN que terminam sem extensão.
    if "s73cloud.com" in low and any(x in low for x in ("live", "stream", "playlist", "manifest", "channel")):
        return True
    return False

def score(url):
    low = url.lower()
    s = 0
    for term, points in (
        (".m3u8", 100),
        ("master", 20),
        ("playlist", 15),
        ("manifest", 10),
        ("live", 8),
        ("s73cloud.com", 5),
    ):
        if term in low:
            s += points
    return s

def ffprobe(url):
    try:
        p = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-rw_timeout", "10000000",
                "-user_agent", UA,
                "-i", url,
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
        )
        return p.returncode == 0 and bool(p.stdout.strip())
    except Exception:
        return False

def extract_channel_urls(text):
    if not text:
        return set()
    result = set()
    patterns = [
        r'https?://mais\.sbt\.com\.br/channel/[A-Za-z0-9_-]+',
        r'["\'](/channel/[A-Za-z0-9_-]+)["\']',
    ]
    for pat in patterns:
        for m in re.findall(pat, text, flags=re.I):
            result.add(m if m.startswith("http") else urljoin(BASE, m))
    return result

async def text_from_page(page):
    try:
        return await page.content()
    except Exception:
        return ""

async def discover():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        context = await browser.new_context(
            user_agent=UA,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1440, "height": 1000},
        )

        discovered = {}
        channel_pages = set()
        errors = []

        async def capture(url, page_url, hint="network"):
            if not valid_stream(url):
                return

            key = url.split("?")[0]
            if key not in discovered:
                discovered[key] = {
                    "url": url,
                    "page": page_url,
                    "hint": hint,
                    "name": "",
                    "category": "",
                }

        async def inspect_page(page, url):
            # Extrai canais do HTML, scripts e JSON.
            html = await text_from_page(page)
            channel_pages.update(extract_channel_urls(html))

            try:
                links = await page.locator("a").evaluate_all(
                    "els => els.map(a => a.href).filter(Boolean)"
                )
                for href in links:
                    if "/channel/" in href.lower():
                        channel_pages.add(href.split("#")[0])
            except Exception:
                pass

            # Tenta iniciar o player.
            selectors = [
                "video",
                "button",
                "[role=button]",
                "[class*=play]",
                "[aria-label*=play i]",
                "[aria-label*=assistir i]",
                "[aria-label*=ao vivo i]",
            ]

            for selector in selectors:
                try:
                    loc = page.locator(selector)
                    count = min(await loc.count(), 8)
                    for i in range(count):
                        try:
                            await loc.nth(i).click(timeout=1200, force=True)
                            await page.wait_for_timeout(1200)
                        except Exception:
                            pass
                except Exception:
                    pass

            await page.wait_for_timeout(4500)

            # Também lê performance entries.
            try:
                resources = await page.evaluate(
                    "() => performance.getEntriesByType('resource').map(x => x.name)"
                )
                for resource in resources:
                    await capture(resource, url, "performance")
            except Exception:
                pass

            # Procura m3u8/CDN no HTML bruto.
            for match in re.findall(r'https?://[^"\'<>\s]+', html):
                if valid_stream(match):
                    await capture(match, url, "html")

            # Nome da página.
            title = clean(await page.title())
            h1 = ""
            try:
                h1 = clean(await page.locator("h1").first.inner_text(timeout=1000))
            except Exception:
                pass

            name = channel_name(h1 or title)

            for item in discovered.values():
                if item["page"] == url and not item["name"]:
                    item["name"] = name
                    item["category"] = category(name)

        page = await context.new_page()

        # Monitoramento de toda a rede da home.
        page.on(
            "response",
            lambda response: capture(
                response.url, page.url, "response"
            )
        )

        try:
            await page.goto(BASE, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            errors.append(f"home: {exc}")

        await page.wait_for_timeout(7000)
        await inspect_page(page, BASE)

        # Reinspeciona canais à medida que novos links forem encontrados.
        for _round in range(3):
            pending = sorted(channel_pages)
            print(f"Rodada {_round + 1}: {len(pending)} páginas de canais")
            before = len(channel_pages)

            for url in pending[:100]:
                ch = await context.new_page()
                ch.on(
                    "response",
                    lambda response, u=url: capture(
                        response.url, u, "response"
                    )
                )
                try:
                    await ch.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=50000,
                    )
                    await ch.wait_for_timeout(3500)
                    await inspect_page(ch, url)
                except Exception as exc:
                    errors.append(f"{url}: {exc}")
                finally:
                    await ch.close()

            if len(channel_pages) == before:
                break

        await browser.close()

    # Associa nomes conhecidos também quando o título da página for genérico.
    for item in discovered.values():
        if not item["name"]:
            item["name"] = "SBT"
            item["category"] = "SBT"

    # Uma URL por canal/categoria, priorizando manifesto mais explícito.
    chosen = {}
    for item in discovered.values():
        key = (item["name"].lower(), item["category"].lower())
        if key not in chosen or score(item["url"]) > score(chosen[key]["url"]):
            chosen[key] = item

    return channel_pages, list(chosen.values()), errors

def main():
    pages, streams, errors = asyncio.run(discover())

    print(f"Páginas descobertas: {len(pages)}")
    print(f"Streams descobertos: {len(streams)}")

    approved = []
    for i, item in enumerate(streams, 1):
        print(f"Teste {i}/{len(streams)}: {item['name']} -> {item['url']}")
        ok = ffprobe(item["url"])
        item["tested"] = True
        item["working"] = ok
        if ok:
            approved.append(item)
            print("  OK")
        else:
            print("  FALHOU")

    lines = ["#EXTM3U"]
    for item in sorted(approved, key=lambda x: (x["category"], x["name"])):
        name = item["name"].replace('"', "'")
        cat = item["category"].replace('"', "'")
        lines.append(
            f'#EXTINF:-1 tvg-id="{name}" tvg-name="{name}" '
            f'tvg-language="pt-BR" tvg-country="BR" '
            f'group-title="{cat}",{name}'
        )
        lines.append(item["url"])

    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    debug = {
        "site": BASE,
        "paginas_canais": sorted(pages),
        "streams_encontrados": streams,
        "streams_aprovados": approved,
        "total_paginas": len(pages),
        "total_streams": len(streams),
        "total_aprovados": len(approved),
        "erros": errors,
    }

    DEBUG.write_text(
        json.dumps(debug, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Playlist: {OUTPUT}")
    print(f"Canais ativos: {len(approved)}")

    if len(approved) == 0:
        print("ATENÇÃO: nenhum stream foi aprovado.")
        print("Consulte descoberto.json para identificar em qual etapa a descoberta falhou.")

if __name__ == "__main__":
    main()
