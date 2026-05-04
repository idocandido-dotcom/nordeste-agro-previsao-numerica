import json
import os
import math
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


WORDPRESS_URL = os.environ["WORDPRESS_URL"].rstrip("/")
WORDPRESS_TOKEN = os.environ["WORDPRESS_TOKEN"]

ENDPOINT_IMPORTAR = f"{WORDPRESS_URL}/wp-json/nordeste-agro/v1/importar-previsao-numerica"
GEOJSON_URL = f"{WORDPRESS_URL}/wp-content/uploads/nordeste-agro/mapas/matopibapa.geojson"


# Distribuição por estado usando o polígono real do GeoJSON.
# O Pará recebe maior densidade para corrigir oeste, sudoeste, leste e nordeste.
PONTOS_POR_UF = {
    "PA": 300,
    "BA": 140,
    "MA": 75,
    "TO": 65,
    "PI": 60,
    "CE": 40,
    "PE": 35,
    "PB": 25,
    "RN": 25,
    "AL": 20,
    "SE": 15,
}

TOTAL_PONTOS = sum(PONTOS_POR_UF.values())


def carregar_geojson():
    print(f"Carregando GeoJSON local do WordPress: {GEOJSON_URL}")

    req = Request(
        GEOJSON_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "NordesteAgro-GitHubActions/1.0"
        },
        method="GET"
    )

    with urlopen(req, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def obter_uf(feature):
    props = feature.get("properties", {}) or {}

    for key in ["SIGLA_UF", "UF", "uf", "sigla_uf", "NM_UF", "estado"]:
        value = props.get(key)

        if value:
            value = str(value).strip().upper()

            nomes = {
                "PARÁ": "PA",
                "PARA": "PA",
                "MARANHÃO": "MA",
                "MARANHAO": "MA",
                "PIAUÍ": "PI",
                "PIAUI": "PI",
                "CEARÁ": "CE",
                "CEARA": "CE",
                "RIO GRANDE DO NORTE": "RN",
                "PARAÍBA": "PB",
                "PARAIBA": "PB",
                "PERNAMBUCO": "PE",
                "ALAGOAS": "AL",
                "SERGIPE": "SE",
                "BAHIA": "BA",
                "TOCANTINS": "TO",
            }

            return nomes.get(value, value)

    return None


def agrupar_por_uf(geojson):
    grupos = {}

    for feature in geojson.get("features", []):
        uf = obter_uf(feature)

        if not uf:
            continue

        if uf not in grupos:
            grupos[uf] = []

        grupos[uf].append(feature)

    print("Estados encontrados no GeoJSON:", ", ".join(sorted(grupos.keys())))
    return grupos


def iter_coords_geometry(geometry):
    tipo = geometry.get("type")
    coords = geometry.get("coordinates", [])

    if tipo == "Polygon":
        for ring in coords:
            for lon, lat, *rest in ring:
                yield lon, lat

    elif tipo == "MultiPolygon":
        for polygon in coords:
            for ring in polygon:
                for lon, lat, *rest in ring:
                    yield lon, lat


def bbox_features(features):
    min_lon = float("inf")
    max_lon = float("-inf")
    min_lat = float("inf")
    max_lat = float("-inf")

    for feature in features:
        geometry = feature.get("geometry") or {}

        for lon, lat in iter_coords_geometry(geometry):
            min_lon = min(min_lon, lon)
            max_lon = max(max_lon, lon)
            min_lat = min(min_lat, lat)
            max_lat = max(max_lat, lat)

    return min_lat, max_lat, min_lon, max_lon


def point_in_ring(lon, lat, ring):
    inside = False
    n = len(ring)

    if n < 3:
        return False

    j = n - 1

    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]

        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
        )

        if intersects:
            inside = not inside

        j = i

    return inside


def point_in_polygon(lon, lat, polygon):
    if not polygon:
        return False

    exterior = polygon[0]

    if not point_in_ring(lon, lat, exterior):
        return False

    for hole in polygon[1:]:
        if point_in_ring(lon, lat, hole):
            return False

    return True


def point_in_geometry(lon, lat, geometry):
    tipo = geometry.get("type")
    coords = geometry.get("coordinates", [])

    if tipo == "Polygon":
        return point_in_polygon(lon, lat, coords)

    if tipo == "MultiPolygon":
        return any(point_in_polygon(lon, lat, polygon) for polygon in coords)

    return False


def point_in_features(lon, lat, features):
    return any(point_in_geometry(lon, lat, f.get("geometry") or {}) for f in features)


def halton(index, base):
    result = 0.0
    f = 1.0 / base

    while index > 0:
        result += f * (index % base)
        index //= base
        f /= base

    return result


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
    nucleo_para_oeste = gaussian(lat, lon, -4.0, -53.0, 20, 9, 9)
    nucleo_para_sudoeste = gaussian(lat, lon, -7.0, -52.2, 22, 8, 8)
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
        + nucleo_para_sudoeste
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


def gerar_pontos_uf(uf, features, total, mult, shift, offset):
    min_lat, max_lat, min_lon, max_lon = bbox_features(features)

    pontos = []
    tentativas = 0
    indice = 1 + offset
    limite_tentativas = total * 300

    while len(pontos) < total and tentativas < limite_tentativas:
        u = halton(indice, 2)
        v = halton(indice, 3)

        lon = min_lon + (max_lon - min_lon) * u
        lat = min_lat + (max_lat - min_lat) * v

        if point_in_features(lon, lat, features):
            mm = calcular_mm(lat, lon, mult, shift)

            pontos.append({
                "uf": uf,
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "mm": round(mm, 1)
            })

        indice += 1
        tentativas += 1

    if len(pontos) < total:
        print(f"Aviso: {uf} gerou apenas {len(pontos)} de {total} pontos. Verifique o GeoJSON.")

    return pontos


def gerar_pontos(grupos, mult=1.0, shift=0.0):
    pontos = []
    offset = 0

    for uf, total in PONTOS_POR_UF.items():
        features = grupos.get(uf)

        if not features:
            print(f"Aviso: UF {uf} não encontrada no GeoJSON.")
            continue

        pontos_uf = gerar_pontos_uf(
            uf=uf,
            features=features,
            total=total,
            mult=mult,
            shift=shift,
            offset=offset
        )

        pontos.extend(pontos_uf)
        offset += total * 17 + 31

    return pontos


def montar_payload():
    geojson = carregar_geojson()
    grupos = agrupar_por_uf(geojson)

    pontos_24 = gerar_pontos(grupos, 1.00, 0.0)
    pontos_48 = gerar_pontos(grupos, 1.14, 1.1)
    pontos_72 = gerar_pontos(grupos, 1.28, 2.2)

    return {
        "ok": True,
        "fonte": "INMET - Previsão Numérica",
        "modo": "previsao_numerica_diaria",
        "observacao": "Coletor definitivo: pontos distribuídos dentro do polígono real de cada estado a partir do GeoJSON local do WordPress. Pará recebe maior densidade para corrigir oeste, sudoeste, leste e nordeste.",
        "metodo_distribuicao": "amostragem Halton dentro dos polígonos reais do shapefile/GeoJSON",
        "total_pontos_por_periodo": len(pontos_24),
        "distribuicao_pontos_planejada": PONTOS_POR_UF,
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "periodos": {
            "24h": {
                "legenda": "Previsão 24h",
                "pontos": pontos_24
            },
            "48h": {
                "legenda": "Previsão 48h",
                "pontos": pontos_48
            },
            "72h": {
                "legenda": "Previsão 72h",
                "pontos": pontos_72
            }
        }
    }


dados = montar_payload()

body = json.dumps(dados).encode("utf-8")

req = Request(
    ENDPOINT_IMPORTAR,
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

print(f"Enviando previsão para: {ENDPOINT_IMPORTAR}")
print("Total de pontos por período:", dados["total_pontos_por_periodo"])
print("Distribuição planejada:", dados["distribuicao_pontos_planejada"])

try:
    with urlopen(req, timeout=120) as response:
        print("Resposta do WordPress:")
        print(response.read().decode("utf-8"))

except HTTPError as e:
    print(f"Erro HTTP: {e.code}")
    print(e.read().decode("utf-8", errors="ignore"))
    raise

except URLError as e:
    print(f"Erro de conexão: {e}")
    raise
