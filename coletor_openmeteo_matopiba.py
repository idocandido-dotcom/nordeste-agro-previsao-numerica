import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# COLETOR MATOPIBA — OPEN-METEO
# ============================================================
# Este script:
# - consulta a Open-Meteo Forecast API;
# - usa pontos reais por coordenada no MATOPIBA;
# - calcula precipitação acumulada prevista para 24h, 48h e 72h;
# - salva JSON para o WordPress gerar o mapa e o slide.
#
# Não usa simulação.
# Não inventa valores.
# Não gera imagem fixa.
# ============================================================


OUT_DIR = Path("public/clima/matopiba")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_JSON = OUT_DIR / "openmeteo_matopiba.json"

FONTE = "Open-Meteo Forecast API"
MODELO = "Best match / modelos meteorológicos combinados pela Open-Meteo"
AREA = "MATOPIBA"

API_URL = "https://api.open-meteo.com/v1/forecast"

# Pontos distribuídos no MATOPIBA.
# Inclui cidades produtoras e pontos adicionais para melhorar interpolação.
PONTOS = [
    # MARANHÃO
    {"uf": "MA", "nome": "Balsas", "lat": -7.5325, "lon": -46.0356},
    {"uf": "MA", "nome": "Tasso Fragoso", "lat": -8.4724, "lon": -45.7545},
    {"uf": "MA", "nome": "Alto Parnaíba", "lat": -9.1089, "lon": -45.9300},
    {"uf": "MA", "nome": "Riachão", "lat": -7.3617, "lon": -46.6172},
    {"uf": "MA", "nome": "São Raimundo das Mangabeiras", "lat": -7.0219, "lon": -45.4806},
    {"uf": "MA", "nome": "Sambaíba", "lat": -7.1344, "lon": -45.3511},
    {"uf": "MA", "nome": "Carolina", "lat": -7.3353, "lon": -47.4692},
    {"uf": "MA", "nome": "Benedito Leite", "lat": -7.2100, "lon": -44.5572},
    {"uf": "MA", "nome": "Fortaleza dos Nogueiras", "lat": -6.9656, "lon": -46.1747},
    {"uf": "MA", "nome": "Loreto", "lat": -7.0811, "lon": -45.1458},

    # TOCANTINS
    {"uf": "TO", "nome": "Palmas", "lat": -10.1844, "lon": -48.3336},
    {"uf": "TO", "nome": "Porto Nacional", "lat": -10.7081, "lon": -48.4172},
    {"uf": "TO", "nome": "Gurupi", "lat": -11.7292, "lon": -49.0686},
    {"uf": "TO", "nome": "Pedro Afonso", "lat": -8.9686, "lon": -48.1778},
    {"uf": "TO", "nome": "Campos Lindos", "lat": -7.9894, "lon": -46.8642},
    {"uf": "TO", "nome": "Dianópolis", "lat": -11.6244, "lon": -46.8192},
    {"uf": "TO", "nome": "Formoso do Araguaia", "lat": -11.7975, "lon": -49.5319},
    {"uf": "TO", "nome": "Lagoa da Confusão", "lat": -10.7906, "lon": -49.6197},
    {"uf": "TO", "nome": "Natividade", "lat": -11.7075, "lon": -47.7225},
    {"uf": "TO", "nome": "Araguaína", "lat": -7.1911, "lon": -48.2072},

    # PIAUÍ
    {"uf": "PI", "nome": "Bom Jesus", "lat": -9.0740, "lon": -44.3590},
    {"uf": "PI", "nome": "Uruçuí", "lat": -7.2294, "lon": -44.5561},
    {"uf": "PI", "nome": "Baixa Grande do Ribeiro", "lat": -7.8497, "lon": -45.2192},
    {"uf": "PI", "nome": "Corrente", "lat": -10.4333, "lon": -45.1639},
    {"uf": "PI", "nome": "Gilbués", "lat": -9.8325, "lon": -45.3431},
    {"uf": "PI", "nome": "Santa Filomena", "lat": -9.1128, "lon": -45.9211},
    {"uf": "PI", "nome": "Currais", "lat": -9.0111, "lon": -44.4069},
    {"uf": "PI", "nome": "Monte Alegre do Piauí", "lat": -9.7533, "lon": -45.3031},
    {"uf": "PI", "nome": "Ribeiro Gonçalves", "lat": -7.5583, "lon": -45.2444},
    {"uf": "PI", "nome": "Sebastião Leal", "lat": -7.5686, "lon": -44.0608},

    # BAHIA
    {"uf": "BA", "nome": "Barreiras", "lat": -12.1528, "lon": -44.9900},
    {"uf": "BA", "nome": "Luís Eduardo Magalhães", "lat": -12.0956, "lon": -45.7867},
    {"uf": "BA", "nome": "São Desidério", "lat": -12.3639, "lon": -44.9731},
    {"uf": "BA", "nome": "Formosa do Rio Preto", "lat": -11.0483, "lon": -45.1931},
    {"uf": "BA", "nome": "Correntina", "lat": -13.3436, "lon": -44.6367},
    {"uf": "BA", "nome": "Riachão das Neves", "lat": -11.7461, "lon": -44.9147},
    {"uf": "BA", "nome": "Jaborandi", "lat": -13.6214, "lon": -44.4619},
    {"uf": "BA", "nome": "Cocos", "lat": -14.1817, "lon": -44.5356},
    {"uf": "BA", "nome": "Baianópolis", "lat": -12.3019, "lon": -44.5389},
    {"uf": "BA", "nome": "Wanderley", "lat": -12.1169, "lon": -43.8956},

    # PONTOS DE REFORÇO PARA INTERPOLAÇÃO REGIONAL
    {"uf": "MA", "nome": "Ponto MA Norte", "lat": -5.90, "lon": -45.50},
    {"uf": "MA", "nome": "Ponto MA Oeste", "lat": -6.80, "lon": -47.30},
    {"uf": "MA", "nome": "Ponto MA Leste", "lat": -6.90, "lon": -44.20},
    {"uf": "TO", "nome": "Ponto TO Norte", "lat": -8.30, "lon": -48.50},
    {"uf": "TO", "nome": "Ponto TO Centro", "lat": -10.30, "lon": -48.60},
    {"uf": "TO", "nome": "Ponto TO Sudeste", "lat": -12.50, "lon": -46.80},
    {"uf": "PI", "nome": "Ponto PI Oeste", "lat": -8.40, "lon": -45.60},
    {"uf": "PI", "nome": "Ponto PI Centro", "lat": -8.80, "lon": -44.40},
    {"uf": "PI", "nome": "Ponto PI Sul", "lat": -10.30, "lon": -44.80},
    {"uf": "BA", "nome": "Ponto BA Norte", "lat": -11.40, "lon": -45.30},
    {"uf": "BA", "nome": "Ponto BA Oeste", "lat": -12.70, "lon": -46.00},
    {"uf": "BA", "nome": "Ponto BA Sul", "lat": -14.10, "lon": -44.70},
]


def abrir_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "NordesteAgro-Clima/1.0"
        },
        method="GET"
    )

    with urllib.request.urlopen(req, timeout=120) as response:
        texto = response.read().decode("utf-8")
        return json.loads(texto)


def montar_url(pontos_lote):
    latitudes = ",".join(str(p["lat"]) for p in pontos_lote)
    longitudes = ",".join(str(p["lon"]) for p in pontos_lote)

    params = {
        "latitude": latitudes,
        "longitude": longitudes,
        "hourly": "precipitation",
        "forecast_days": "4",
        "timezone": "America/Bahia",
        "precipitation_unit": "mm"
    }

    return API_URL + "?" + urllib.parse.urlencode(params)


def soma_intervalo(valores, inicio, fim):
    recorte = valores[inicio:fim]
    total = 0.0

    for v in recorte:
        if v is None:
            continue
        total += float(v)

    return round(total, 1)


def processar_resposta_lote(pontos_lote, dados):
    if isinstance(dados, dict):
        dados_lista = [dados]
    elif isinstance(dados, list):
        dados_lista = dados
    else:
        raise RuntimeError("Resposta da Open-Meteo veio em formato inesperado.")

    if len(dados_lista) != len(pontos_lote):
        raise RuntimeError(
            f"Quantidade de respostas ({len(dados_lista)}) diferente dos pontos ({len(pontos_lote)})."
        )

    resultados = []

    for ponto, dado in zip(pontos_lote, dados_lista):
        hourly = dado.get("hourly", {})
        precipitacao = hourly.get("precipitation", [])

        if len(precipitacao) < 72:
            raise RuntimeError(
                f"Ponto {ponto['nome']} retornou menos de 72 horas de precipitação."
            )

        acumulado_24 = soma_intervalo(precipitacao, 0, 24)
        acumulado_48 = soma_intervalo(precipitacao, 24, 48)
        acumulado_72 = soma_intervalo(precipitacao, 48, 72)

        resultados.append({
            "uf": ponto["uf"],
            "nome": ponto["nome"],
            "lat": ponto["lat"],
            "lon": ponto["lon"],
            "precipitacao_mm": {
                "24h": acumulado_24,
                "48h": acumulado_48,
                "72h": acumulado_72
            }
        })

    return resultados


def consultar_openmeteo():
    todos_resultados = []

    tamanho_lote = 10

    for i in range(0, len(PONTOS), tamanho_lote):
        lote = PONTOS[i:i + tamanho_lote]
        url = montar_url(lote)

        print(f"Consultando lote {i // tamanho_lote + 1}: {len(lote)} pontos")
        dados = abrir_json(url)

        resultados = processar_resposta_lote(lote, dados)
        todos_resultados.extend(resultados)

    return todos_resultados


def gerar_periodos(pontos):
    periodos = {
        "24h": [],
        "48h": [],
        "72h": []
    }

    for p in pontos:
        for periodo in periodos.keys():
            periodos[periodo].append({
                "uf": p["uf"],
                "nome": p["nome"],
                "lat": p["lat"],
                "lon": p["lon"],
                "mm": p["precipitacao_mm"][periodo]
            })

    return periodos


def resumo_periodo(pontos):
    valores = [float(p["mm"]) for p in pontos]

    if not valores:
        return {
            "min": 0,
            "media": 0,
            "max": 0
        }

    return {
        "min": round(min(valores), 1),
        "media": round(sum(valores) / len(valores), 1),
        "max": round(max(valores), 1)
    }


def main():
    print("Iniciando coleta Open-Meteo MATOPIBA...")

    pontos = consultar_openmeteo()
    periodos = gerar_periodos(pontos)

    payload = {
        "ok": True,
        "fonte": FONTE,
        "modelo": MODELO,
        "area": AREA,
        "oficial_inmet": False,
        "simulado": False,
        "tipo": "previsao_meteorologica_por_coordenada",
        "metodo": "Consulta Open-Meteo Forecast API por pontos do MATOPIBA e cálculo de acumulados 24h, 48h e 72h",
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "total_pontos": len(pontos),
        "periodos": {
            "24h": {
                "label": "Previsão acumulada 24h",
                "resumo": resumo_periodo(periodos["24h"]),
                "pontos": periodos["24h"]
            },
            "48h": {
                "label": "Previsão acumulada 48h",
                "resumo": resumo_periodo(periodos["48h"]),
                "pontos": periodos["48h"]
            },
            "72h": {
                "label": "Previsão acumulada 72h",
                "resumo": resumo_periodo(periodos["72h"]),
                "pontos": periodos["72h"]
            }
        }
    }

    OUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Arquivo gerado: {OUT_JSON}")
    print(f"Total de pontos: {len(pontos)}")

    for periodo, dados in payload["periodos"].items():
        print(periodo, dados["resumo"])


if __name__ == "__main__":
    main()
