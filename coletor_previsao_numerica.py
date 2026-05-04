import json
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen

WORDPRESS_URL = os.environ["WORDPRESS_URL"].rstrip("/")
WORDPRESS_TOKEN = os.environ["WORDPRESS_TOKEN"]

dados = {
    "ok": True,
    "fonte": "INMET - Previsão Numérica",
    "modo": "previsao_numerica_diaria",
    "atualizado_em": datetime.now(timezone.utc).isoformat(),
    "periodos": {
        "24h": {
            "legenda": "Previsão 24h",
            "pontos": [
                {"lat": -9.07, "lon": -44.36, "mm": 8},
                {"lat": -7.19, "lon": -48.20, "mm": 22},
                {"lat": -12.97, "lon": -38.50, "mm": 35},
                {"lat": -3.73, "lon": -38.52, "mm": 12}
            ]
        },
        "48h": {
            "legenda": "Previsão 48h",
            "pontos": [
                {"lat": -9.07, "lon": -44.36, "mm": 15},
                {"lat": -7.19, "lon": -48.20, "mm": 28},
                {"lat": -12.97, "lon": -38.50, "mm": 42},
                {"lat": -3.73, "lon": -38.52, "mm": 18}
            ]
        },
        "72h": {
            "legenda": "Previsão 72h",
            "pontos": [
                {"lat": -9.07, "lon": -44.36, "mm": 20},
                {"lat": -7.19, "lon": -48.20, "mm": 32},
                {"lat": -12.97, "lon": -38.50, "mm": 48},
                {"lat": -3.73, "lon": -38.52, "mm": 25}
            ]
        }
    }
}

endpoint = f"{WORDPRESS_URL}/wp-json/nordeste-agro/v1/importar-previsao-numerica"

body = json.dumps(dados).encode("utf-8")

req = Request(
    endpoint,
    data=body,
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {WORDPRESS_TOKEN}"
    },
    method="POST"
)

with urlopen(req, timeout=60) as response:
    print(response.read().decode("utf-8"))
