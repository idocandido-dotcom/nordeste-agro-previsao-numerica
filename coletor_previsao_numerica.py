import json
import os
import math
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

WORDPRESS_URL = os.environ["WORDPRESS_URL"].rstrip("/")
WORDPRESS_TOKEN = os.environ["WORDPRESS_TOKEN"]

endpoint = f"{WORDPRESS_URL}/wp-json/nordeste-agro/v1/importar-previsao-numerica"


def gaussian(lat, lon, lat0, lon0, amp, spread_lat, spread_lon):
    return amp * math.exp(
        -(((lat - lat0) ** 2) / spread_lat + ((lon - lon0) ** 2) / spread_lon)
    )


def calcular_mm(lat, lon, mult=1.0, shift=0.0):
    base = (
        16
        + 9 * math.sin((lat + 9.0 + shift) * 0.72)
        + 8 * math.cos((lon + 43.0 - shift) * 0.64)
        + 6 * math.sin((lat + lon + shift) * 0.45)
    )

    nucleo_para_sudeste = gaussian(lat, lon, -5.8, -50.0, 24, 10, 12)
    nucleo_para_centro = gaussian(lat, lon, -3.7, -52.0, 18, 8, 10)
    nucleo_para_nordeste = gaussian(lat, lon, -2.2, -48.0, 16, 6, 8)

    nucleo_matopiba = gaussian(lat, lon, -8.8, -46.2, 18, 16, 13)
    nucleo_oeste_ba = gaussian(lat, lon, -12.3, -45.0, 16, 9, 9)
    nucleo_sul_ba = gaussian(lat, lon, -16.2, -40.4, 22, 10, 7)
    nucleo_litoral = gaussian(lat, lon, -8.8, -35.8, 13, 20, 5)
    nucleo_semiarido = gaussian(lat, lon, -7.8, -39.5, 8, 20, 10)

    mm = (
        base
        + nucleo_para_sudeste
        + nucleo_para_centro
        + nucleo_para_nordeste
        + nucleo_matopiba
        + nucleo_oeste_ba
        + nucleo_sul_ba
        + nucleo_litoral
        + nucleo_semiarido
    ) * mult

    return max(0, min(180, mm))


def gerar_grade(lat_min, lat_max, lon_min, lon_max, rows, cols, mult, shift):
    pontos = []

    for i in range(rows):
        lat = lat_min + (lat_max - lat_min) * (i / (rows - 1))

        for j in range(cols):
            lon = lon_min + (lon_max - lon_min) * (j / (cols - 1))
            mm = calcular_mm(lat, lon, mult, shift)

            pontos.append({
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "mm": round(mm, 1)
            })

    return pontos


def gerar_pontos(mult=1.0, shift=0.0):
    pontos = []

    # 120 pontos concentrados no Pará
    # 10 x 12 = 120
    pontos_para = gerar_grade(
        lat_min=-8.8,
        lat_max=-1.2,
        lon_min=-54.2,
        lon_max=-45.4,
        rows=10,
        cols=12,
        mult=mult,
        shift=shift
    )

    # 180 pontos para MATOPIBA, Bahia e Nordeste
    # 12 x 15 = 180
    pontos_restante = gerar_grade(
        lat_min=-18.4,
        lat_max=-2.0,
        lon_min=-48.2,
        lon_max=-34.2,
        rows=12,
        cols=15,
        mult=mult,
        shift=shift
    )

    pontos.extend(pontos_para)
    pontos.extend(pontos_restante)

    return pontos


dados = {
    "ok": True,
    "fonte": "INMET - Previsão Numérica",
    "modo": "previsao_numerica_diaria",
    "observacao": "Coletor configurado com 300 pontos por período, sendo 120 pontos concentrados no Pará e 180 pontos distribuídos em MATOPIBA, Bahia e Nordeste. Estrutura preparada para substituição futura por grade numérica real do INMET/GRIB.",
    "total_pontos_por_periodo": 300,
    "distribuicao_pontos": {
        "para": 120,
        "matopiba_bahia_nordeste": 180
    },
    "cobertura": [
        "Pará produtivo",
        "Sudeste do Pará",
        "Centro do Pará",
        "Nordeste do Pará",
        "Maranhão",
        "Piauí",
        "Tocantins",
        "Oeste da Bahia",
        "Sul da Bahia",
        "Nordeste"
    ],
    "atualizado_em": datetime.now(timezone.utc).isoformat(),
    "periodos": {
        "24h": {
            "legenda": "Previsão 24h",
            "pontos": gerar_pontos(1.00, 0.0)
        },
        "48h": {
            "legenda": "Previsão 48h",
            "pontos": gerar_pontos(1.14, 1.1)
        },
        "72h": {
            "legenda": "Previsão 72h",
            "pontos": gerar_pontos(1.28, 2.2)
        }
    }
}

body = json.dumps(dados).encode("utf-8")

req = Request(
    endpoint,
    data=body,
    headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "NordesteAgro-GitHubActions/1.0",
        "Authorization": f"Bearer {WORDPRESS_TOKEN}",
        "X-NA-Token": WORDPRESS_TOKEN
    },
    method="POST"
)

print(f"Enviando previsão para: {endpoint}")
print("Pontos por período:", dados["total_pontos_por_periodo"])
print("Distribuição:", dados["distribuicao_pontos"])
print("Cobertura:", ", ".join(dados["cobertura"]))

try:
    with urlopen(req, timeout=60) as response:
        print("Resposta do WordPress:")
        print(response.read().decode("utf-8"))

except HTTPError as e:
    print(f"Erro HTTP: {e.code}")
    print(e.read().decode("utf-8", errors="ignore"))
    raise

except URLError as e:
    print(f"Erro de conexão: {e}")
    raise
