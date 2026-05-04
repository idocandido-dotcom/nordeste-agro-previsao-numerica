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

# Horas desejadas.
# O VIME pode mostrar +024 ou +24, por isso deixamos várias opções.
HORAS = [
    {"labels": ["+024", "+24", "024", "24"], "slug": "24h"},
    {"labels": ["+048", "+48", "048", "48"], "slug": "48h"},
    {"labels": ["+072", "+72", "072", "72"], "slug": "72h"},
]

# Pasta onde as imagens serão salvas no GitHub
OUT_DIR = Path("public/clima/matopiba")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Tamanho da tela virtual usada pelo navegador automatizado
VIEWPORT_WIDTH = 1365
VIEWPORT_HEIGHT = 900

# Recorte bruto do mapa dentro da tela do VIME.
# Esses valores foram baseados no layout que você mostrou no print.
# Se o VIME mudar o layout, podemos ajustar depois.
MAP_CROP = (370, 85, 990, 650)

# Recorte final para focar MATOPIBA, retirando áreas fora do foco.
# O objetivo é não usar Pará e focar Maranhão, Tocantins, Piauí e Bahia.
MATOPIBA_CROP = (95, 35, 610, 520)

# URL pública via jsDelivr para o HTML do WordPress carregar os arquivos
REPO_CDN_BASE = (
    "https://cdn.jsdelivr.net/gh/"
    "idocandido-dotcom/nordeste-agro-previsao-numerica@main/"
    "public/clima/matopiba"
)


def clicar_texto_seguro(page, texto, timeout=4000):
    try:
        page.get_by_text(texto, exact=True).click(timeout=timeout)
        return True
    except Exception:
        return False


def selecionar_modelo_e_mapa(page):
    """
    Tenta selecionar o modelo COSMO 7x7km e o mapa de Precipitação Acumulada
    nos selects do VIME.
    """
    selects = page.locator("select")
    qtd = selects.count()

    print(f"Selects encontrados na página: {qtd}")

    for i in range(qtd):
        sel = selects.nth(i)

        try:
            options = sel.locator("option")
            opt_count = options.count()
            labels = []

            for j in range(opt_count):
                labels.append(options.nth(j).inner_text().strip())

            print(f"Select {i} opções:", labels[:20])

            # Selecionar modelo
            if any(MODELO_DESEJADO.lower() in x.lower() for x in labels):
                try:
                    sel.select_option(label=MODELO_DESEJADO)
                    print(f"Modelo selecionado: {MODELO_DESEJADO}")
                    time.sleep(1.5)
                    continue
                except Exception as erro:
                    print("Não foi possível selecionar modelo por label exato:", erro)

                    for lab in labels:
                        if "cosmo" in lab.lower() and "7" in lab.lower():
                            try:
                                sel.select_option(label=lab)
                                print(f"Modelo selecionado por aproximação: {lab}")
                                time.sleep(1.5)
                                break
                            except Exception:
                                pass

            # Selecionar mapa
            if any("precipitação acumulada" in x.lower() or "precipitacao acumulada" in x.lower() for x in labels):
                escolhido = None

                for lab in labels:
                    lab_lower = lab.lower()
                    if "precipitação acumulada" in lab_lower or "precipitacao acumulada" in lab_lower:
                        escolhido = lab
                        break

                if escolhido:
                    try:
                        sel.select_option(label=escolhido)
                        print(f"Mapa selecionado: {escolhido}")
                        time.sleep(1.5)
                        continue
                    except Exception as erro:
                        print("Não foi possível selecionar mapa:", erro)

        except Exception as erro:
            print(f"Erro ao ler select {i}:", erro)


def clicar_hora(page, labels):
    """
    Tenta clicar no botão de previsão por diferentes formas:
    +024, +24, 024, 24.
    """
    print("Tentando clicar horário com labels:", labels)

    # Tentativa 1: texto exato
    for label in labels:
        try:
            page.get_by_text(label, exact=True).click(timeout=3000)
            return label
        except Exception:
            pass

    # Tentativa 2: botão contendo o texto
    for label in labels:
        try:
            page.locator("button").filter(has_text=label).first.click(timeout=3000)
            return label
        except Exception:
            pass

    # Tentativa 3: qualquer elemento com texto
    for label in labels:
        try:
            page.locator(f"text={label}").first.click(timeout=3000)
            return label
        except Exception:
            pass

    # Diagnóstico: lista textos de botões encontrados
    try:
        botoes = page.locator("button")
        total = botoes.count()
        textos = []

        for i in range(min(total, 80)):
            try:
                txt = botoes.nth(i).inner_text(timeout=1000).strip()
                if txt:
                    textos.append(txt)
            except Exception:
                pass

        print("Botões encontrados na página:", textos)
    except Exception as erro:
        print("Não foi possível listar botões:", erro)

    raise RuntimeError(f"Não foi possível clicar no horário. Tentativas: {labels}")


def capturar_frame(page, labels, nome_saida_png):
    """
    Clica no horário desejado, faz screenshot da página,
    recorta a área do mapa e salva a imagem final MATOPIBA.
    """
    hora_clicada = clicar_hora(page, labels)

    print(f"Horário selecionado no VIME: {hora_clicada}")

    time.sleep(4)

    fullshot = OUT_DIR / f"_full_{nome_saida_png}"
    page.screenshot(path=str(fullshot), full_page=True)

    img = Image.open(fullshot)

    # Recorte bruto do mapa
    mapa = img.crop(MAP_CROP)

    # Recorte final do MATOPIBA
    matopiba = mapa.crop(MATOPIBA_CROP)

    out_png = OUT_DIR / nome_saida_png
    matopiba.save(out_png)

    try:
        fullshot.unlink()
    except Exception:
        pass

    return out_png


def gerar_gif(frames, gif_path):
    imagens = []

    for p in frames:
        img = Image.open(p).convert("P", palette=Image.ADAPTIVE)
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

    return manifest_path


def main():
    arquivos = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            viewport={
                "width": VIEWPORT_WIDTH,
                "height": VIEWPORT_HEIGHT
            }
        )

        print("Abrindo VIME/INMET:", VIME_URL)

        page.goto(
            VIME_URL,
            wait_until="domcontentloaded",
            timeout=120000
        )

        time.sleep(10)

        # Clica em CO, caso a página precise reforçar a região.
        clicar_texto_seguro(page, "CO", timeout=3000)
        time.sleep(2)

        selecionar_modelo_e_mapa(page)
        time.sleep(3)

        for item in HORAS:
            slug = item["slug"]
            labels = item["labels"]
            nome = f"matopiba_{slug}.png"

            print(f"Capturando {slug}...")
            arquivos[slug] = capturar_frame(page, labels, nome)

        browser.close()

    gif_path = OUT_DIR / "matopiba_animado.gif"

    gerar_gif(
        [
            arquivos["24h"],
            arquivos["48h"],
            arquivos["72h"]
        ],
        gif_path
    )

    arquivos["gif"] = gif_path

    manifest_path = gerar_manifest(arquivos)

    print("Arquivos gerados com sucesso:")

    for k, v in arquivos.items():
        print(k, "->", v)

    print("Manifest ->", manifest_path)


if __name__ == "__main__":
    main()
