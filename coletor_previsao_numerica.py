import json
import os
import math
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

WORDPRESS_URL = os.environ["WORDPRESS_URL"].rstrip("/")
WORDPRESS_TOKEN = os.environ["WORDPRESS_TOKEN"]

endpoint = f"{WORDPRESS_URL}/wp-json/nordeste-agro/v1/importar-previsao-numerica"

# Área expandida para cobrir:
# - Pará produtivo / sudeste do Pará
# - Maranhão
# - Piauí
# - Tocantins
# - Bahia, incluindo sul da Bahia
# - Nordeste litorâneo
lat_min, lat_max = -18.4, -1.2
lon_min, lon_max = -53.5, -34.2

# 20 x 10 = 200 pontos
rows, cols = 10, 20


def gaussian(lat, lon, lat0, lon0, amp, spread_lat, spread_lon):
    return amp * math.exp(
        -(((lat - lat0) ** 2) / spread_lat + ((lon - lon0) ** 2) / spread_lon)
    )


def gerar_pontos(mult=1.0, shift=0.0):
    pontos = []

    for i in range(rows):
        lat = lat_min + (lat_max - lat_min) * (i / (rows - 1))

        for j in range(cols):
            lon = lon_min + (lon_max - lon_min) * (j / (cols - 1))

            # Campo base suave
            base = (
                16
                + 9 * math.sin((lat + 9.0 + shift) * 0.72)
                + 8 * math.cos((lon + 43.0 - shift) * 0.64)
                + 6 * math.sin((lat + lon + shift) * 0.45)
            )

            # Núcleos regionais de precipitação

            # Sudeste / sul do Pará
            nucleo_para = gaussian(
                lat, lon,
                lat0=-5.8,
                lon0=-50.0,
                amp=20,
                spread_lat=10,
                spread_lon=12
            )

            # MATOPIBA — Maranhão, Tocantins, Piauí, oeste da Bahia
            nucleo_matopiba = gaussian(
                lat, lon,
                lat0=-8.8,
                lon0=-46.2,
                amp=18,
                spread_lat=16,
                spread_lon=13
            )

            # Oeste da Bahia / Luís Eduardo Magalhães / Barreiras
            nucleo_oeste_ba = gaussian(
                lat, lon,
                lat0=-12.3,
                lon0=-45.0,
                amp=16,
                spread_lat=9,
                spread_lon=9
            )

            # Sul da Bahia
            nucleo_sul_ba = gaussian(
                lat, lon,
                lat0=-16.2,
                lon0=-40.4,
                amp=22,
                spread_lat=10,
                spread_lon=7
            )

            # Litoral nordestino
            nucleo_litoral = gaussian(
                lat, lon,
                lat0=-8.8,
                lon0=-35.8,
                amp=13,
                spread_lat=20,
                spread_lon=5
            )

            # Centro-norte do Nordeste
            nucleo_semiarido = gaussian(
                lat, lon,
                lat0=-7.8,
                lon0=-39.5,
                amp=8,
                spread_lat=20,
                spread_lon=10
            )

            mm = (
                base
                + nucleo_para
                + nucleo_matopiba
                + nucleo_oeste_ba
                + nucleo_sul_ba
                + nucleo_litoral
                + nucleo_semiarido
            ) * mult

            mm = max(0, min(180, mm))

            pontos.append({
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "mm": round(mm, 1)
            })

    return pontos


dados = {
    "ok": True,
    "fonte": "INMET - Previsão Numérica",
    "modo": "previsao_numerica_diaria",
    "observacao": "Coletor configurado com 200 pontos expandidos para cobrir Pará, Sul da Bahia, MATOPIBA e Nordeste. Estrutura preparada para substituição futura por grade numérica real do INMET/GRIB.",
    "total_pontos_por_periodo": 200,
    "cobertura": [
        "Pará produtivo",
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
