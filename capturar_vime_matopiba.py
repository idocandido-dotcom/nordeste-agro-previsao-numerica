import json
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
# COLETOR OFICIAL VIME / INMET — MATOPIBA
# ============================================================
# Este script:
# - abre o VIME/INMET;
# - usa o botão oficial "Download de Todas as Imagens";
# - baixa o ZIP oficial gerado pelo VIME;
# - extrai os frames +24, +48 e +72;
# - recorta o foco MATOPIBA;
# - gera PNGs finais;
# - gera manifest.json para o WordPress.
#
# Não cria valores numéricos.
# Não cria grade própria.
# Não gera simulação.
# Não publica imagem branca/carregando.
# Não gera GIF.
# O slide será feito pelo HTML do WordPress.
# ============================================================


REGIAO_VIME = "NE"
VIME_URL = f"https://vime.inmet.gov.br/{REGIAO_VIME}"

MODELO = "COSMO 7x7km"
PRODUTO = "Precipitação Acumulada 24h"
AREA = "MATOPIBA"

OUT_DIR = Path("public/clima/matopiba")
OUT_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORT_WIDTH = 1365
VIEWPORT_HEIGHT = 900

REPO_CDN_BASE = (
    "https://cdn.jsdelivr.net/gh/"
    "idocandido-dotcom/nordeste-agro-previsao-numerica@main/"
    "public/clima/matopiba"
)

FRAMES_DESEJADOS = {
    "24h": ["+24", "+024"],
    "48h": ["+48", "+048"],
    "72h": ["+72", "+072"],
}

# Recorte proporcional do arquivo oficial do VIME para focar MATOPIBA.
# Ajustado para o ZIP oficial baixado do VIME/INMET.
MATOPIBA_CROP_RATIO = {
    "left": 0.00,
    "top": 0.00,
    "right": 0.82,
    "bottom": 0.965,
}

DOWNLOAD_BUTTON_X = 95
DOWNLOAD_BUTTON_Y = 316


def limpar_saida_antiga():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    padroes = [
        "_vime_download*.zip",
        "_debug*.png",
        "_raw_*.png",
        "matopiba_24h.png",
        "matopiba_48h.png",
        "matopiba_72h.png",
        "manifest.json",
    ]

    for padrao in padroes:
        for arquivo in OUT_DIR.glob(padrao):
            try:
                arquivo.unlink()
            except Exception:
                pass


def salvar_debug(page, nome):
    caminho = OUT_DIR / nome

    try:
        page.screenshot(path=str(caminho), full_page=True)
        print(f"Debug salvo: {caminho}")
    except Exception as erro:
        print(f"Não foi possível salvar debug {nome}: {erro}")


def baixar_zip_vime(page):
    """
    Baixa o ZIP oficial do VIME usando o botão "Download de Todas as Imagens".

    Correção importante:
    No GitHub Actions, o clique normal pode falhar porque o <body> intercepta
    o ponteiro. Por isso usamos clique forçado e também clique via JavaScript
    diretamente no span.baixarZip.
    """
    print("Preparando download do ZIP oficial do VIME...")

    salvar_debug(page, "_debug_antes_download.png")

    zip_path = OUT_DIR / "_vime_download.zip"

    try:
        with page.expect_download(timeout=240000) as download_info:
            clicou = False

            # Tentativa 1: clique forçado no elemento real do botão.
            try:
                print("Tentando clique forçado em span.baixarZip...")
                page.locator("span.baixarZip").first.click(
                    timeout=15000,
                    force=True
                )
                clicou = True
                print("Clique forçado realizado em span.baixarZip.")
            except Exception as erro:
                print(f"Clique forçado em span.baixarZip falhou: {erro}")

            # Tentativa 2: clique via JavaScript no elemento.
            if not clicou:
                try:
                    print("Tentando clique via JavaScript em span.baixarZip...")
                    page.locator("span.baixarZip").first.evaluate(
                        "el => el.click()"
                    )
                    clicou = True
                    print("Clique via JavaScript realizado em span.baixarZip.")
                except Exception as erro:
                    print(f"Clique via JavaScript falhou: {erro}")

            # Tentativa 3: clique pelo texto.
            if not clicou:
                try:
                    print("Tentando clique por texto...")
                    page.get_by_text("Download de Todas as Imagens", exact=False).click(
                        timeout=15000,
                        force=True
                    )
                    clicou = True
                    print("Clique por texto realizado.")
                except Exception as erro:
                    print(f"Clique por texto falhou: {erro}")

            # Tentativa 4: clique por coordenada.
            if not clicou:
                print(
                    "Tentando clique por coordenada "
                    f"x={DOWNLOAD_BUTTON_X}, y={DOWNLOAD_BUTTON_Y}"
                )
                page.mouse.click(DOWNLOAD_BUTTON_X, DOWNLOAD_BUTTON_Y)
                clicou = True

            if not clicou:
                raise RuntimeError(
                    "Nenhuma estratégia conseguiu clicar no botão de download."
                )

        download = download_info.value
        download.save_as(str(zip_path))

    except PlaywrightTimeoutError:
        salvar_debug(page, "_debug_download_timeout.png")
        raise RuntimeError(
            "O VIME não iniciou o download do ZIP oficial dentro do tempo limite."
        )

    except Exception as erro:
        salvar_debug(page, "_debug_download_erro.png")
        raise RuntimeError(f"Erro ao baixar ZIP oficial do VIME: {erro}")

    if not zip_path.exists() or zip_path.stat().st_size < 10000:
        raise RuntimeError(
            "O arquivo ZIP do VIME não foi baixado corretamente ou veio vazio."
        )

    print(f"ZIP oficial baixado: {zip_path} ({zip_path.stat().st_size} bytes)")

    return zip_path


def listar_zip(zip_path):
    with zipfile.ZipFile(zip_path, "r") as z:
        nomes = z.namelist()

    print(f"Arquivos dentro do ZIP: {len(nomes)}")

    for nome in nomes[:15]:
        print(" -", nome)

    return nomes


def encontrar_imagem_do_frame(nomes, labels):
    candidatos = []

    for nome in nomes:
        nome_limpo = nome.strip()

        if not nome_limpo.lower().endswith(".png"):
            continue

        for label in labels:
            label_regex = re.escape(label)
            padrao = rf"_{label_regex}\.png$"

            if re.search(padrao, nome_limpo):
                candidatos.append(nome_limpo)

    if not candidatos:
        raise RuntimeError(
            f"Não encontrei imagem no ZIP para labels {labels}."
        )

    candidatos = sorted(candidatos)

    print(f"Frame {labels} encontrado:", candidatos[0])

    return candidatos[0]


def extrair_imagem(zip_path, nome_interno, destino):
    with zipfile.ZipFile(zip_path, "r") as z:
        with z.open(nome_interno) as origem:
            img = Image.open(origem).convert("RGB")
            img.save(destino)

    print(f"Imagem extraída: {destino}")

    return destino


def imagem_valida(img):
    img = img.convert("RGB")
    w, h = img.size

    total = 0
    coloridos = 0
    quase_brancos = 0

    step = 8

    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = img.getpixel((x, y))
            total += 1

            maxc = max(r, g, b)
            minc = min(r, g, b)

            if maxc - minc > 35:
                coloridos += 1

            if r > 235 and g > 235 and b > 235:
                quase_brancos += 1

    if total == 0:
        return False

    color_ratio = coloridos / total
    white_ratio = quase_brancos / total

    print(
        "Validação da imagem:",
        "color_ratio=", round(color_ratio, 4),
        "white_ratio=", round(white_ratio, 4)
    )

    return color_ratio >= 0.04 and white_ratio <= 0.90


def recortar_matopiba(img):
    img = img.convert("RGB")
    w, h = img.size

    left = int(w * MATOPIBA_CROP_RATIO["left"])
    top = int(h * MATOPIBA_CROP_RATIO["top"])
    right = int(w * MATOPIBA_CROP_RATIO["right"])
    bottom = int(h * MATOPIBA_CROP_RATIO["bottom"])

    crop = img.crop((left, top, right, bottom))

    return crop


def processar_frame(zip_path, nomes_zip, slug, labels):
    nome_interno = encontrar_imagem_do_frame(nomes_zip, labels)

    raw_path = OUT_DIR / f"_raw_{slug}.png"
    final_path = OUT_DIR / f"matopiba_{slug}.png"

    extrair_imagem(zip_path, nome_interno, raw_path)

    img_raw = Image.open(raw_path).convert("RGB")

    if not imagem_valida(img_raw):
        raise RuntimeError(
            f"A imagem oficial extraída para {slug} não parece válida."
        )

    img_matopiba = recortar_matopiba(img_raw)

    if not imagem_valida(img_matopiba):
        raise RuntimeError(
            f"O recorte MATOPIBA para {slug} não parece válido."
        )

    img_matopiba.save(final_path)

    print(f"Frame final salvo: {final_path}")

    return final_path


def gerar_manifest(arquivos):
    manifest = {
        "ok": True,
        "fonte": "INMET / VIME",
        "modelo": MODELO,
        "produto": PRODUTO,
        "area": AREA,
        "regiao_vime": REGIAO_VIME,
        "oficial": True,
        "simulado": False,
        "metodo": "Download oficial do ZIP do VIME/INMET e recorte visual MATOPIBA",
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
    limpar_saida_antiga()

    arquivos = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-web-security"
            ]
        )

        page = browser.new_page(
            viewport={
                "width": VIEWPORT_WIDTH,
                "height": VIEWPORT_HEIGHT
            },
            accept_downloads=True
        )

        print(f"Abrindo VIME/INMET: {VIME_URL}")

        page.goto(
            VIME_URL,
            wait_until="domcontentloaded",
            timeout=120000
        )

        # Aguarda o painel lateral montar.
        time.sleep(12)

        zip_path = baixar_zip_vime(page)

        browser.close()

    nomes_zip = listar_zip(zip_path)

    arquivos["24h"] = processar_frame(
        zip_path,
        nomes_zip,
        "24h",
        FRAMES_DESEJADOS["24h"]
    )

    arquivos["48h"] = processar_frame(
        zip_path,
        nomes_zip,
        "48h",
        FRAMES_DESEJADOS["48h"]
    )

    arquivos["72h"] = processar_frame(
        zip_path,
        nomes_zip,
        "72h",
        FRAMES_DESEJADOS["72h"]
    )

    gerar_manifest(arquivos)

    print("Processo finalizado com sucesso.")
    print("Arquivos gerados:")

    for chave, caminho in arquivos.items():
        print(f"{chave}: {caminho}")


if __name__ == "__main__":
    main()
