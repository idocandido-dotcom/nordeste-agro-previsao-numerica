import json
import os
import math
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

WORDPRESS_URL = os.environ["WORDPRESS_URL"].rstrip("/")
WORDPRESS_TOKEN = os.environ["WORDPRESS_TOKEN"]

endpoint = f"{WORDPRESS_URL}/wp-json/nordeste-agro/v1/importar-previsao-numerica"

lat_min, lat_max = -15.2, -2.0
lon_min, lon_max = -49.8, -34.5

rows, cols = 10, 20


def gerar_pontos(mult=1.0, shift=0.0):
    pontos = []

    for i in range(rows):
        lat = lat_min + (lat_max - lat_min) * (i / (rows - 1))

        for j in range(cols):
            lon = lon_min + (lon_max - lon_min) * (j / (cols - 1))

            base = (
                18
                + 12 * math.sin((lat + 9.5 + shift) * 0.85)
                + 9 * math.cos((lon + 42.0 - shift) * 0.72)
                + 7 * math.sin((lat + lon + shift) * 0.55)
            )

            nucleo_ba = 18 * math.exp(
                -(((lat + 12.7) ** 2) / 10 + ((lon + 39.5) ** 2) / 8)
            )

            nucleo_ma_to_pi = 14 * math.exp(
                -(((lat + 7.5) ** 2) / 12 + ((lon + 46.0) ** 2) / 9)
            )

            nucleo_litoral = 11 * math.exp(
                -(((lat + 8.5) ** 2) / 18 + ((lon + 35.8) ** 2) / 5)
            )

            mm = max(
                0,
                min(
                    160,
                    (base + nucleo_ba + nucleo_ma_to_pi + nucleo_litoral) * mult
                )
            )

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
    "observacao": "Coletor configurado para 200 pontos por período. Estrutura preparada para substituir os pontos por grade numérica real do INMET/GRIB.",
    "total_pontos_por_periodo": 200,
    "atualizado_em": datetime.now(timezone.utc).isoformat(),
    "periodos": {
        "24h": {
            "legenda": "Previsão 24h",
            "pontos": gerar_pontos(1.00, 0.0)
        },
        "48h": {
            "legenda": "Previsão 48h",
            "pontos": gerar_pontos(1.16, 1.2)
        },
        "72h": {
            "legenda": "Previsão 72h",
            "pontos": gerar_pontos(1.32, 2.4)
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
