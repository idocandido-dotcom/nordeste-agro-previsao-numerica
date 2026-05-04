import json
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright


# ============================================================
# COLETOR OFICIAL VIME / INMET — MATOPIBA
# ============================================================
# Este script:
# - abre o VIME/INMET;
# - usa a área CO;
# - captura os mapas oficiais de precipitação acumulada;
# - recorta a região MATOPIBA;
# - gera 24h, 48h, 72h;
# - gera GIF animado;
# - gera manifest.json para o WordPress.
#
# Não cria dados simulados.
# Usa apenas imagem oficial visual do VIME/INMET.
# ============================================================


VIME_URL = "https://vime.inmet.gov.br/CO"

MODELO_DESEJADO = "COSMO 7x7km"
MAPA_DESEJADO = "Precipitação Acumulada"

OUT_DIR = Path("public/clima/matopiba")
OUT_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORT_WIDTH = 1365
VIEWPORT_HEIGHT = 900

# Recorte bruto do mapa no print do VIME.
# Coordenadas: esquerda, topo, direita, baixo.
MAP_CROP = (370, 85, 990, 650)

# Recorte final MATOPIBA dentro do recorte do mapa.
# Mantém MA, TO, PI e BA e remove áreas fora do foco.
MATOPIBA_CROP = (95, 35, 610, 520)

REPO_CDN_BASE = (
    "https://cdn.jsdelivr.net/gh/"
    "idocandido-dotcom/nordeste-agro-previsao-numerica@main/"
    "public/clima/matopiba"
)

# Coordenadas dos botões de horas no layout do VIME.
# Baseado no print enviado:
# primeira linha: +024 +027 +030 +033 +036 +039
# segunda linha: +042 +045 +048 +051 +054 +057
# terceira linha: +060 +063 +066 +069 +072 +075
#
# x/y são coordenadas aproximadas na viewport 1365x900.
HORAS = [
    {
        "slug": "24h",
        "label": "+024",
        "click_x": 27,
        "click_y": 386,
    },
    {
        "slug": "48h",
        "label": "+048",
        "click_x": 104,
        "click_y": 420,
    },
    {
        "slug": "72h",
        "label": "+072",
        "click_x": 202,
        "click_y": 456,
    },
]


def salvar_debug(page, nome):
    debug_path = OUT_DIR / nome
    try:
        page.screenshot(path=str(debug_path), full_page=True)
        print(f"Debug salvo: {debug_path}")
    except Exception as erro:
        print(f"Não foi possível salvar debug {nome}: {erro}")


def tentar_clicar_texto(page, texto, timeout=2500):
    try:
        page.get_by_text(texto, exact=True).click(timeout=timeout)
        return True
    except Exception:
        return False


def tentar_selecionar_modelo_mapa(page):
    """
    O VIME é uma aplicação JS. Em alguns momentos os selects aparecem
    como elementos customizados e não retornam opções para o Playwright.
    Esta função tenta selecionar, mas se não conseguir, segue com o padrão
    já carregado pela página.
    """
    print("Tentando selecionar modelo e mapa no VIME...")

    try:
        selects = page.locator("select")
        qtd = selects.count()
        print(f"Selects encontrados na página: {qtd}")

        for i in range(qtd):
            try:
                sel = selects.nth(i)
                options = sel.locator("option")
                opt_count = options.count()
                labels = []

                for j in range(opt_count):
                    labels.append(options.nth(j).inner_text().strip())

                print(f"Select {i} opções:", labels[:30])

                for lab in labels:
                    lab_lower = lab.lower()

                    if "cosmo" in lab_lower and "7" in lab_lower:
                        try:
                            sel.select_option(label=lab)
                            print(f"Modelo selecionado: {lab}")
                            time.sleep(2)
                            break
                        except Exception as erro:
                            print(f"Falha ao selecionar modelo {lab}: {erro}")

                for lab in labels:
                    lab_lower = lab.lower()

                    if "precipitação acumulada" in lab_lower or "precipitacao acumulada" in lab_lower:
                        try:
                            sel.select_option(label=lab)
                            print(f"Mapa selecionado: {lab}")
                            time.sleep(2)
                            break
                        except Exception as erro:
                            print(f"Falha ao selecionar mapa {lab}: {erro}")

            except Exception as erro:
                print(f"Erro lendo select {i}: {erro}")

    except Exception as erro:
        print("Não foi possível ler selects:", erro)


def clicar_hora_por_coordenada(page, item):
    """
    Como o VIME não está expondo os botões de previsão como botões HTML
    no Playwright, usamos clique por coordenada.
    """
    label = item["label"]
    x = item["click_x"]
    y = item["click_y"]

    print(f"Clicando horário {label} por coordenada x={x}, y={y}")

    page.mouse.click(x, y)
    time.sleep(4)


def capturar_frame(page, item):
    """
    Captura uma imagem para 24h, 48h ou 72h.
    """
    slug = item["slug"]
    label = item["label"]

    print(f"Capturando frame {slug} ({label})...")

    clicar_hora_por_coordenada(page, item)

    fullshot = OUT_DIR / f"_full_{slug}.png"
    page.screenshot(path=str(fullshot), full_page=True)

    img = Image.open(fullshot)

    mapa = img.crop(MAP_CROP)
    matopiba = mapa.crop(MATOPIBA_CROP)

    out_png = OUT_DIR / f"matopiba_{slug}.png"
    matopiba.save(out_png)

    try:
        fullshot.unlink()
    except Exception:
        pass

    print(f"Frame salvo: {out_png}")

    return out_png


def gerar_gif(frames, gif_path):
    imagens = []

    for frame in frames:
        img = Image.open(frame).convert("P", palette=Image.ADAPTIVE)
        imagens.append(img)

    if not imagens:
        raise RuntimeError("Nenhum frame disponível para gerar GIF.")

    imagens[0].save(
        gif_path,
        save_all=True,
        append_images=imagens[1:],
        duration=1300,
        loop=0
    )

    print(f"GIF gerado: {gif_path}")


def gerar_manifest(arquivos):
    manifest = {
        "ok": True,
        "fonte": "INMET / VIME",
        "modelo": MODELO_DESEJADO,
        "produto": MAPA_DESEJADO,
        "area": "MATOPIBA",
        "oficial": True,
        "simulado": False,
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "frames": {
            "24h": {
                "label": "24h",
                "url": f"{REPO_CDN_BASE}/{arquivos['24h'].name}"
            },
            "48h": {
                "label": "48h",
                "url": f"{REPO_CDN_BASE}/{arquivos['48h'].name}"
            },
            "72h": {
                "label": "72h",
                "url": f"{REPO_CDN_BASE}/{arquivos['72h'].name}"
            },
        },
        "gif": {
            "label": "GIF animado",
            "url": f"{REPO_CDN_BASE}/{arquivos['gif'].name}"
        }
    }

    manifest_path = OUT_DIR / "manifest.json"

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Manifest gerado: {manifest_path}")

    return manifest_path


def main():
    arquivos = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox"
            ]
        )

        page = browser.new_page(
            viewport={
                "width": VIEWPORT_WIDTH,
                "height": VIEWPORT_HEIGHT
            }
        )

        print(f"Abrindo VIME/INMET: {VIME_URL}")

        page.goto(
            VIME_URL,
            wait_until="domcontentloaded",
            timeout=120000
        )

        # Aguarda o React/VIME montar.
        time.sleep(12)

        salvar_debug(page, "_debug_pagina_inicial.png")

        # Clica em CO, caso necessário.
        tentar_clicar_texto(page, "CO", timeout=3000)
        time.sleep(2)

        tentar_selecionar_modelo_mapa(page)
        time.sleep(3)

        salvar_debug(page, "_debug_apos_configuracao.png")

        for item in HORAS:
            slug = item["slug"]
            arquivos[slug] = capturar_frame(page, item)

        browser.close()

    gif_path = OUT_DIR / "matopiba_animado.gif"

    gerar_gif(
        [
            arquivos["24h"],
            arquivos["48h"],
            arquivos["72h"],
        ],
        gif_path
    )

    arquivos["gif"] = gif_path

    gerar_manifest(arquivos)

    print("Processo finalizado com sucesso.")
    print("Arquivos gerados:")

    for chave, caminho in arquivos.items():
        print(f"{chave}: {caminho}")


if __name__ == "__main__":
    main()
