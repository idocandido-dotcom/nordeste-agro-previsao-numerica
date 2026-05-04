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
# - captura mapas oficiais de precipitação acumulada;
# - procura automaticamente a área colorida do mapa na tela;
# - recorta a região MATOPIBA;
# - gera 24h, 48h, 72h;
# - gera GIF animado;
# - gera manifest.json para o WordPress.
#
# Não cria dados simulados.
# Não publica imagem branca ou tela de carregamento.
# ============================================================


VIME_URL = "https://vime.inmet.gov.br/CO"

MODELO_DESEJADO = "COSMO 7x7km"
MAPA_DESEJADO = "Precipitação Acumulada"

OUT_DIR = Path("public/clima/matopiba")
OUT_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORT_WIDTH = 1365
VIEWPORT_HEIGHT = 900

REPO_CDN_BASE = (
    "https://cdn.jsdelivr.net/gh/"
    "idocandido-dotcom/nordeste-agro-previsao-numerica@main/"
    "public/clima/matopiba"
)

# Coordenadas aproximadas dos horários no painel esquerdo do VIME.
# Se o layout do VIME mudar, o script ainda tenta detectar o mapa depois.
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
        print(f"Clique por texto realizado: {texto}")
        return True
    except Exception:
        return False


def tentar_selecionar_modelo_mapa(page):
    """
    Tenta selecionar modelo e produto.
    Se o VIME não expuser os selects como HTML comum, segue com padrão carregado.
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
                            time.sleep(4)
                            break
                        except Exception as erro:
                            print(f"Falha ao selecionar modelo {lab}: {erro}")

                for lab in labels:
                    lab_lower = lab.lower()

                    if "precipitação acumulada" in lab_lower or "precipitacao acumulada" in lab_lower:
                        try:
                            sel.select_option(label=lab)
                            print(f"Mapa selecionado: {lab}")
                            time.sleep(4)
                            break
                        except Exception as erro:
                            print(f"Falha ao selecionar mapa {lab}: {erro}")

            except Exception as erro:
                print(f"Erro lendo select {i}: {erro}")

    except Exception as erro:
        print("Não foi possível ler selects:", erro)


def clicar_hora_por_coordenada(page, item):
    label = item["label"]
    x = item["click_x"]
    y = item["click_y"]

    print(f"Clicando horário {label} por coordenada x={x}, y={y}")
    page.mouse.click(x, y)
    time.sleep(5)


def pixel_colorido(r, g, b):
    maxc = max(r, g, b)
    minc = min(r, g, b)

    # Ignora branco/cinza claro e texto preto pequeno.
    if r > 235 and g > 235 and b > 235:
        return False

    if r < 45 and g < 45 and b < 45:
        return False

    # Mapa tem cores fortes: azul, verde, amarelo, vermelho, rosa.
    return (maxc - minc) > 35


def detectar_bbox_mapa_colorido(imagem):
    """
    Detecta automaticamente a área colorida principal do mapa.
    Ignora a barra lateral esquerda usando x_min_busca.
    """
    img = imagem.convert("RGB")
    w, h = img.size

    x_min_busca = int(w * 0.22)
    x_max_busca = int(w * 0.98)
    y_min_busca = int(h * 0.06)
    y_max_busca = int(h * 0.88)

    xs = []
    ys = []

    step = 4

    for y in range(y_min_busca, y_max_busca, step):
      for x in range(x_min_busca, x_max_busca, step):
          r, g, b = img.getpixel((x, y))

          if pixel_colorido(r, g, b):
              xs.append(x)
              ys.append(y)

    if not xs or not ys:
        return None

    min_x = max(min(xs) - 20, 0)
    max_x = min(max(xs) + 20, w)
    min_y = max(min(ys) - 20, 0)
    max_y = min(max(ys) + 20, h)

    largura = max_x - min_x
    altura = max_y - min_y

    if largura < 250 or altura < 220:
        return None

    return (min_x, min_y, max_x, max_y)


def calcular_indice_mapa(img):
    """
    Mede se o recorte tem conteúdo colorido suficiente.
    """
    img = img.convert("RGB")
    w, h = img.size

    total = 0
    coloridos = 0
    quase_brancos = 0

    step = 6

    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = img.getpixel((x, y))
            total += 1

            if pixel_colorido(r, g, b):
                coloridos += 1

            if r > 235 and g > 235 and b > 235:
                quase_brancos += 1

    if total == 0:
        return {
            "color_ratio": 0,
            "white_ratio": 1,
        }

    return {
        "color_ratio": coloridos / total,
        "white_ratio": quase_brancos / total,
    }


def imagem_parece_mapa(img):
    indice = calcular_indice_mapa(img)

    print(
        "Índice do mapa:",
        "color_ratio=", round(indice["color_ratio"], 4),
        "white_ratio=", round(indice["white_ratio"], 4)
    )

    if indice["color_ratio"] >= 0.04 and indice["white_ratio"] <= 0.88:
        return True

    return False


def aguardar_e_detectar_mapa(page, contexto, timeout_segundos=180):
    """
    Aguarda o mapa colorido aparecer e retorna o bbox detectado.
    """
    print(f"Aguardando mapa colorido carregar: {contexto}")

    inicio = time.time()
    tentativa = 0

    while time.time() - inicio < timeout_segundos:
        tentativa += 1
        temp_path = OUT_DIR / f"_temp_full_{contexto}_{tentativa}.png"

        try:
            page.screenshot(path=str(temp_path), full_page=True)

            img = Image.open(temp_path).convert("RGB")
            bbox = detectar_bbox_mapa_colorido(img)

            if bbox:
                recorte = img.crop(bbox)
                print(f"BBox detectado em {contexto}: {bbox}")

                if imagem_parece_mapa(recorte):
                    temp_path.unlink(missing_ok=True)
                    print(f"Mapa colorido confirmado: {contexto}")
                    return bbox

            temp_path.unlink(missing_ok=True)

        except Exception as erro:
            print(f"Erro ao detectar mapa: {erro}")

        time.sleep(6)

    salvar_debug(page, f"_debug_timeout_{contexto}.png")

    raise RuntimeError(
        f"O mapa oficial do VIME não ficou disponível em {timeout_segundos}s "
        f"durante {contexto}. Nenhuma imagem será publicada."
    )


def recortar_matopiba_a_partir_do_mapa(mapa_img):
    """
    Recorte proporcional dentro do mapa oficial detectado.

    A imagem do VIME mostra área ampla. O recorte abaixo mantém o foco
    visual no MATOPIBA e retira grande parte do entorno.
    """
    w, h = mapa_img.size

    # Recorte proporcional. Ajustado para foco MA, TO, PI e BA.
    left = int(w * 0.12)
    top = int(h * 0.05)
    right = int(w * 0.98)
    bottom = int(h * 0.92)

    return mapa_img.crop((left, top, right, bottom))


def capturar_frame(page, item):
    slug = item["slug"]
    label = item["label"]

    print(f"Capturando frame {slug} ({label})...")

    clicar_hora_por_coordenada(page, item)

    bbox = aguardar_e_detectar_mapa(
        page,
        contexto=slug,
        timeout_segundos=180
    )

    fullshot = OUT_DIR / f"_full_{slug}.png"
    page.screenshot(path=str(fullshot), full_page=True)

    img = Image.open(fullshot).convert("RGB")

    mapa = img.crop(bbox)

    if not imagem_parece_mapa(mapa):
        salvar_debug(page, f"_debug_mapa_invalido_{slug}.png")
        raise RuntimeError(
            f"O frame {slug} não parece mapa válido. Imagem não será publicada."
        )

    matopiba = recortar_matopiba_a_partir_do_mapa(mapa)

    if not imagem_parece_mapa(matopiba):
        salvar_debug(page, f"_debug_matopiba_invalido_{slug}.png")
        raise RuntimeError(
            f"O recorte MATOPIBA de {slug} não parece mapa válido."
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
            }
        )

        print(f"Abrindo VIME/INMET: {VIME_URL}")

        page.goto(
            VIME_URL,
            wait_until="domcontentloaded",
            timeout=120000
        )

        time.sleep(18)

        salvar_debug(page, "_debug_pagina_inicial.png")

        tentar_clicar_texto(page, "CO", timeout=3000)
        time.sleep(5)

        tentar_selecionar_modelo_mapa(page)
        time.sleep(8)

        salvar_debug(page, "_debug_apos_configuracao.png")

        # Confirma que há mapa colorido antes de capturar frames.
        aguardar_e_detectar_mapa(
            page,
            contexto="inicial",
            timeout_segundos=180
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
