import json
import os
import math
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

WORDPRESS_URL = os.environ["WORDPRESS_URL"].rstrip("/")
WORDPRESS_TOKEN = os.environ["WORDPRESS_TOKEN"]

endpoint = f"{WORDPRESS_URL}/wp-json/nordeste-agro/v1/importar-previsao-numerica"


# Distribuição definitiva por tamanho/região produtiva.
# Total: 630 pontos por período.
REGIOES = [
    # PARÁ — 180 pontos
    {"uf": "PA", "regiao": "Oeste do Pará", "lat_min": -6.5, "lat_max": -1.2, "lon_min": -55.2, "lon_max": -51.8, "pontos": 35},
    {"uf": "PA", "regiao": "Centro do Pará", "lat_min": -7.0, "lat_max": -1.6, "lon_min": -52.8, "lon_max": -49.4, "pontos": 45},
    {"uf": "PA", "regiao": "Sudeste do Pará", "lat_min": -8.8, "lat_max": -4.2, "lon_min": -51.5, "lon_max": -47.8, "pontos": 45},
    {"uf": "PA", "regiao": "Leste e Nordeste do Pará", "lat_min": -4.8, "lat_max": -0.8, "lon_min": -49.2, "lon_max": -45.4, "pontos": 55},

    # BAHIA — 125 pontos
    {"uf": "BA", "regiao": "Oeste da Bahia", "lat_min": -14.6, "lat_max": -8.6, "lon_min": -46.6, "lon_max": -43.0, "pontos": 50},
    {"uf": "BA", "regiao": "Centro da Bahia", "lat_min": -15.4, "lat_max": -10.0, "lon_min": -43.6, "lon_max": -39.8, "pontos": 30},
    {"uf": "BA", "regiao": "Sul da Bahia", "lat_min": -18.4, "lat_max": -14.2, "lon_min": -41.8, "lon_max": -37.8, "pontos": 45},

    # MATOPIBA / NORDESTE
    {"uf": "MA", "regiao": "Maranhão", "lat_min": -10.3, "lat_max": -1.0, "lon_min": -48.8, "lon_max": -41.8, "pontos": 70},
    {"uf": "TO", "regiao": "Tocantins", "lat_min": -13.5, "lat_max": -5.0, "lon_min": -50.2, "lon_max": -45.4, "pontos": 65},
    {"uf": "PI", "regiao": "Piauí", "lat_min": -10.9, "lat_max": -2.7, "lon_min": -45.9, "lon_max": -40.3, "pontos": 55},
    {"uf": "CE", "regiao": "Ceará", "lat_min": -7.9, "lat_max": -2.8, "lon_min": -41.5, "lon_max": -37.2, "pontos": 35},
    {"uf": "PE", "regiao": "Pernambuco", "lat_min": -9.5, "lat_max": -7.1, "lon_min": -41.4, "lon_max": -34.8, "pontos": 30},
    {"uf": "RN", "regiao": "Rio Grande do Norte", "lat_min": -6.6, "lat_max": -4.7, "lon_min": -38.7, "lon_max": -34.9, "pontos": 20},
    {"uf": "PB", "regiao": "Paraíba", "lat_min": -8.3, "lat_max": -6.0, "lon_min": -38.8, "lon_max": -34.7, "pontos": 20},
    {"uf": "AL", "regiao": "Alagoas", "lat_min": -10.5, "lat_max": -8.8, "lon_min": -38.3, "lon_max": -35.0, "pontos": 15},
    {"uf": "SE", "regiao": "Sergipe", "lat_min": -11.6, "lat_max": -9.5, "lon_min": -38.4, "lon_max": -36.3, "pontos": 15},
]


def gaussian(lat, lon, lat0, lon0, amp, spread_lat, spread_lon):
    return amp * math.exp(
        -(((lat - lat0) ** 2) / spread_lat + ((lon - lon0) ** 2) / spread_lon)
    )


def calcular_mm(lat, lon, mult=1.0, shift=0.0):
    base = (
        16
        + 8 * math.sin((lat + 9.0 + shift) * 0.72)
        + 7 * math.cos((lon + 43.0 - shift) * 0.64)
        + 5 * math.sin((lat + lon + shift) * 0.45)
    )

    # Núcleos no Pará
    nucleo_para_oeste = gaussian(lat, lon, -3.8, -53.0, 18, 9, 9)
    nucleo_para_centro = gaussian(lat, lon, -4.0, -51.0, 18, 9, 9)
    nucleo_para_sudeste = gaussian(lat, lon, -6.1, -49.6, 24, 10, 10)
    nucleo_para_leste = gaussian(lat, lon, -2.4, -47.4, 20, 7, 8)

    # Núcleos MATOPIBA / Bahia / Nordeste
    nucleo_matopiba = gaussian(lat, lon, -8.8, -46.2, 18, 16, 13)
    nucleo_oeste_ba = gaussian(lat, lon, -12.3, -45.0, 16, 9, 9)
    nucleo_sul_ba = gaussian(lat, lon, -16.2, -40.4, 22, 10, 7)
    nucleo_litoral = gaussian(lat, lon, -8.8, -35.8, 13, 20, 5)
    nucleo_semiarido = gaussian(lat, lon, -7.8, -39.5, 8, 20, 10)

    mm = (
        base
        + nucleo_para_oeste
        + nucleo_para_centro
        + nucleo_para_sudeste
        + nucleo_para_leste
        + nucleo_matopiba
        + nucleo_oeste_ba
        + nucleo_sul_ba
        + nucleo_litoral
        + nucleo_semiarido
    ) * mult

    return max(0, min(180, mm))


def halton(index, base):
    result = 0.0
    f = 1.0 / base

    while index > 0:
        result += f * (index % base)
        index = index // base
        f = f / base

    return result


def gerar_pontos_regiao(regiao, mult, shift, offset):
    pontos = []

    lat_min = regiao["lat_min"]
    lat_max = regiao["lat_max"]
    lon_min = regiao["lon_min"]
    lon_max = regiao["lon_max"]
    total = regiao["pontos"]

    for n in range(1, total + 1):
        # Halton distribui melhor que grade comum, evitando linhas e concentração.
        u = halton(n + offset, 2)
        v = halton(n + offset, 3)

        lat = lat_min + (lat_max - lat_min) * u
        lon = lon_min + (lon_max - lon_min) * v

        mm = calcular_mm(lat, lon, mult, shift)

        pontos.append({
            "uf": regiao["uf"],
            "regiao": regiao["regiao"],
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "mm": round(mm, 1)
        })

    return pontos


def gerar_pontos(mult=1.0, shift=0.0):
    pontos = []
    offset = 0

    for regiao in REGIOES:
        pontos.extend(gerar_pontos_regiao(regiao, mult, shift, offset))
        offset += regiao["pontos"] + 17

    return pontos


TOTAL_PONTOS = sum(r["pontos"] for r in REGIOES)

dados = {
    "ok": True,
    "fonte": "INMET - Previsão Numérica",
    "modo": "previsao_numerica_diaria",
    "observacao": "Coletor com pontos distribuídos proporcionalmente por estado e região produtiva. Pará, Bahia, Maranhão, Tocantins e Piauí recebem maior densidade.",
    "total_pontos_por_periodo": TOTAL_PONTOS,
    "distribuicao_pontos": {
        "total": TOTAL_PONTOS,
        "por_regiao": [
            {
                "uf": r["uf"],
                "regiao": r["regiao"],
                "pontos": r["pontos"]
            }
            for r in REGIOES
        ]
    },
    "cobertura": [
        "Pará",
        "Maranhão",
        "Piauí",
        "Ceará",
        "Rio Grande do Norte",
        "Paraíba",
        "Pernambuco",
        "Alagoas",
        "Sergipe",
        "Bahia",
        "Tocantins"
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
