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
# - captura mapas oficiais de precipitação acumulada;
# - espera o mapa carregar de verdade;
# - recorta a região MATOPIBA;
# - gera 24h, 48h, 72h;
# - gera GIF animado;
# - gera manifest.json para o WordPress.
#
# Não cria dados simulados.
# Não publica imagem se o mapa ainda estiver carregando.
# ============================================================


VIME_URL = "https://vime.inmet.gov.br/CO"

MODELO_DESEJADO = "COSMO 7x7km"
MAPA_DESEJADO = "Precipitação Acumulada"

OUT_DIR = Path("public/clima/matopiba")
OUT_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORT_WIDTH = 1365
VIEWPORT_HEIGHT = 900

# Recorte bruto do mapa no layout do VIME.
MAP_CROP = (370, 85, 990, 650)

# Recorte final para foco MATOPIBA.
MATOPIBA_CROP = (95, 35, 610, 520)

REPO_CDN_BASE = (
    "https://cdn.jsdelivr.net/gh/"
    "idocandido-dotcom/nordeste-agro-previsao-numerica@main/"
    "public/clima/matopiba"
)

# Coordenadas dos botões de horas no layout do VIME.
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


def tentar_clicar_texto(page, texto, timeout=3000):
    try:
        page.get_by_text(texto, exact=True).click(timeout=timeout)
        return True
    except Exception:
        return False


def tentar_selecionar_modelo_mapa(page):
    """
    Tenta selecionar modelo e produto.
    Se o VIME não expuser os selects como HTML normal,
    o script segue com o padrão já carregado pela página.
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
                            time.sleep(3)
                            break
                        except Exception as erro:
                            print(f"Falha ao selecionar modelo {lab}: {erro}")

                for lab in labels:
                    lab_lower = lab.lower()

                    if "precipitação acumulada" in lab_lower or "precipitacao acumulada" in lab_lower:
                        try:
                            sel.select_option(label=lab)
                            print(f"Mapa selecionado: {lab}")
                            time.sleep(3)
                            break
                        except Exception as erro:
                            print(f"Falha ao selecionar mapa {lab}: {erro}")

            except Exception as erro:
                print(f"Erro lendo select {i}: {erro}")

    except Exception as erro:
        print("Não foi possível ler selects:", erro)


def crop_mapa_from_screenshot(screenshot_path):
    img = Image.open(screenshot_path).convert("RGB")
    return img.crop(MAP_CROP)


def calcular_indice_corido(img):
    """
    Calcula se o recorte parece mapa carregado.
    O mapa oficial tem muitas cores fortes.
    A tela de carregamento é quase toda branca/cinza.
    """
    w, h = img.size
    total = 0
    coloridos = 0
    escuros = 0
    quase_brancos = 0

    step = 6

    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = img.getpixel((x, y))
            total += 1

            maxc = max(r, g, b)
            minc = min(r, g, b)

            if maxc - minc > 35:
                coloridos += 1

            if r < 80 and g < 80 and b < 80:
                escuros += 1

            if r > 235 and g > 235 and b > 235:
                quase_brancos += 1

    if total == 0:
        return {
            "color_ratio": 0,
            "dark_ratio": 0,
            "white_ratio": 1,
        }

    return {
        "color_ratio": coloridos / total,
        "dark_ratio": escuros / total,
        "white_ratio": quase_brancos / total,
    }


def mapa_esta_carregado(img):
    indice = calcular_indice_corido(img)

    print(
        "Índice do mapa:",
        "color_ratio=", round(indice["color_ratio"], 4),
        "dark_ratio=", round(indice["dark_ratio"], 4),
        "white_ratio=", round(indice["white_ratio"], 4)
    )

    # Mapa carregado deve ter área colorida significativa.
    # Spinner/tela branca tem color_ratio baixo e white_ratio alto.
    if indice["color_ratio"] >= 0.055 and indice["white_ratio"] <= 0.80:
        return True

    return False


def aguardar_mapa_carregado(page, contexto, timeout_segundos=120):
    """
    Aguarda até o mapa colorido aparecer.
    Se ficar no carregamento, falha.
    """
    print(f"Aguardando mapa carregar: {contexto}")

    inicio = time.time()
    tentativa = 0

    while time.time() - inicio < timeout_segundos:
        tentativa += 1

        temp_path = OUT_DIR / f"_temp_check_{contexto}_{tentativa}.png"

        try:
            page.screenshot(path=str(temp_path), full_page=True)
            mapa = crop_mapa_from_screenshot(temp_path)

            if mapa_esta_carregado(mapa):
                print(f"Mapa carregado confirmado em {contexto}.")
                temp_path.unlink(missing_ok=True)
                return True

            temp_path.unlink(missing_ok=True)

        except Exception as erro:
            print(f"Erro ao checar mapa carregado: {erro}")

        time.sleep(5)

    salvar_debug(page, f"_debug_timeout_{contexto}.png")

    raise RuntimeError(
        f"O mapa do VIME não carregou completamente em {timeout_segundos}s "
        f"durante {contexto}. Nenhuma imagem será publicada."
    )


def clicar_hora_por_coordenada(page, item):
    label = item["label"]
    x = item["click_x"]
    y = item["click_y"]

    print(f"Clicando horário {label} por coordenada x={x}, y={y}")
    page.mouse.click(x, y)
    time.sleep(3)


def capturar_frame(page, item):
    slug = item["slug"]
    label = item["label"]

    print(f"Capturando frame {slug} ({label})...")

    clicar_hora_por_coordenada(page, item)

    aguardar_mapa_carregado(
        page,
        contexto=slug,
        timeout_segundos=120
    )

    fullshot = OUT_DIR / f"_full_{slug}.png"
    page.screenshot(path=str(fullshot), full_page=True)

    img = Image.open(fullshot).convert("RGB")

    mapa = img.crop(MAP_CROP)
    matopiba = mapa.crop(MATOPIBA_CROP)

    # Segurança final: não salvar se o recorte final parecer tela em branco.
    if not mapa_esta_carregado(mapa):
        salvar_debug(page, f"_debug_mapa_nao_carregado_{slug}.png")
        raise RuntimeError(
            f"O frame {slug} ainda parece tela de carregamento. "
            f"Imagem não será publicada."
        )

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

        time.sleep(15)

        salvar_debug(page, "_debug_pagina_inicial.png")

        tentar_clicar_texto(page, "CO", timeout=3000)
        time.sleep(4)

        tentar_selecionar_modelo_mapa(page)
        time.sleep(6)

        salvar_debug(page, "_debug_apos_configuracao.png")

        # Antes de iniciar os frames, confirma que o mapa saiu da tela branca.
        aguardar_mapa_carregado(
            page,
            contexto="inicial",
            timeout_segundos=120
        )

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
