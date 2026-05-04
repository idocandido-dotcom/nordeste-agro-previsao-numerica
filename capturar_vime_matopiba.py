import json
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright


# =========================
# CONFIGURAÇÕES PRINCIPAIS
# =========================

VIME_URL = "https://vime.inmet.gov.br/CO"
MODELO_DESEJADO = "COSMO 7x7km"
MAPA_DESEJADO = "Precipitação Acumulada"

# Horas desejadas
HORAS = [
    {"label": "+024", "slug": "24h"},
    {"label": "+048", "slug": "48h"},
    {"label": "+072", "slug": "72h"},
]

# Saída
OUT_DIR = Path("public/clima/matopiba")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Tamanho da viewport para o Playwright
VIEWPORT_WIDTH = 1365
VIEWPORT_HEIGHT = 900

# Recorte bruto do mapa dentro da página inteira
# Ajustado para o layout do VIME mostrado no seu print.
# Se um dia o layout do VIME mudar, ajuste estes valores.
MAP_CROP = (370, 85, 990, 650)

# Recorte final para focar apenas MATOPIBA (sem Pará)
# (x1, y1, x2, y2) dentro do recorte do mapa
MATOPIBA_CROP = (95, 35, 610, 520)

REPO_CDN_BASE = "https://cdn.jsdelivr.net/gh/idocandido-dotcom/nordeste-agro-previsao-numerica@main/public/clima/matopiba"


def clicar_texto_seguro(page, texto, timeout=5000):
    try:
        page.get_by_text(texto, exact=True).click(timeout=timeout)
        return True
    except Exception:
        return False


def selecionar_modelo_e_mapa(page):
    selects = page.locator("select")
    qtd = selects.count()

    for i in range(qtd):
        sel = selects.nth(i)
        try:
            options = sel.locator("option")
            opt_count = options.count()
            labels = []

            for j in range(opt_count):
                labels.append(options.nth(j).inner_text().strip())

            # Modelo
            if any(MODELO_DESEJADO.lower() in x.lower() for x in labels):
                try:
                    sel.select_option(label=MODELO_DESEJADO)
                    time.sleep(1)
                    continue
                except Exception:
                    pass

            # Mapa
            if any("precipitação acumulada" in x.lower() for x in labels):
                try:
                    # tenta o texto exato, se não der, tenta por aproximação
                    try:
                        sel.select_option(label=MAPA_DESEJADO)
                    except Exception:
                        for lab in labels:
                            if "precipitação acumulada" in lab.lower():
                                sel.select_option(label=lab)
                                break
                    time.sleep(1)
                    continue
                except Exception:
                    pass
        except Exception:
            pass


def capturar_frame(page, hora_label, nome_saida_png):
    # clica no botão da hora
    if not clicar_texto_seguro(page, hora_label, timeout=4000):
        raise RuntimeError(f"Não foi possível clicar no horário {hora_label} no VIME.")

    time.sleep(4)

    fullshot = OUT_DIR / f"_full_{hora_label.replace('+', '')}.png"
    page.screenshot(path=str(fullshot), full_page=True)

    img = Image.open(fullshot)

    # recorte bruto do mapa
    mapa = img.crop(MAP_CROP)

    # recorte do MATOPIBA
    matopiba = mapa.crop(MATOPIBA_CROP)

    # salva png final
    out_png = OUT_DIR / nome_saida_png
    matopiba.save(out_png)

    # remove full temporário
    try:
        fullshot.unlink()
    except Exception:
        pass

    return out_png


def gerar_gif(frames, gif_path):
    imagens = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in frames]
    if not imagens:
        raise RuntimeError("Nenhum frame disponível para gerar GIF.")

    imagens[0].save(
        gif_path,
        save_all=True,
        append_images=imagens[1:],
        duration=1300,
        loop=0
    )


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
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    arquivos = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT})

        page.goto(VIME_URL, wait_until="domcontentloaded", timeout=120000)
        time.sleep(8)

        # garante a aba CO, caso necessário
        clicar_texto_seguro(page, "CO", timeout=3000)
        time.sleep(1)

        selecionar_modelo_e_mapa(page)
        time.sleep(2)

        # captura 24h, 48h, 72h
        for item in HORAS:
            slug = item["slug"]
            label = item["label"]
            nome = f"matopiba_{slug}.png"
            print(f"Capturando {label} ...")
            arquivos[slug] = capturar_frame(page, label, nome)

        browser.close()

    # gera GIF
    gif_path = OUT_DIR / "matopiba_animado.gif"
    gerar_gif(
        [arquivos["24h"], arquivos["48h"], arquivos["72h"]],
        gif_path
    )
    arquivos["gif"] = gif_path

    # gera manifest
    gerar_manifest(arquivos)

    print("Arquivos gerados com sucesso:")
    for k, v in arquivos.items():
        print(k, "->", v)


if __name__ == "__main__":
    main()
