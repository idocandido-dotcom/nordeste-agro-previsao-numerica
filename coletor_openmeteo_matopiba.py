import json
import math
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# COLETOR REGIONAL — NORDESTE + TOCANTINS + PARÁ
# MALHA UNIFORME COM 200 PONTOS
# Fonte meteorológica: Open-Meteo Forecast API
# ============================================================
# Este script:
# - carrega o GeoJSON da região;
# - gera uma grade uniforme sobre Nordeste + TO + PA;
# - filtra pontos dentro dos polígonos reais;
# - seleciona exatamente 200 pontos bem distribuídos;
# - consulta previsão de precipitação na Open-Meteo;
# - salva JSON para o WordPress.
#
# Não simula chuva.
# Não inventa valores.
# Os pontos são coordenadas técnicas de consulta.
# ============================================================


# ------------------------------------------------------------
# CONFIGURAÇÕES PRINCIPAIS
# ------------------------------------------------------------

OUT_DIR = Path("public/clima/regional")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_JSON = OUT_DIR / "openmeteo_regional.json"
BACKUP_JSON = OUT_DIR / "openmeteo_regional_ultimo_valido.json"

FONTE = "Open-Meteo Forecast API"
MODELO = "Best match / modelos meteorológicos combinados pela Open-Meteo"
AREA = "Nordeste + Tocantins + Pará"

API_URL = "https://api.open-meteo.com/v1/forecast"

# GeoJSON local no GitHub, se existir
GEOJSON_LOCAL_PATHS = [
    Path("public/mapas/matopibapa.geojson"),
    Path("public/clima/mapas/matopibapa.geojson"),
    Path("mapas/matopibapa.geojson"),
]

# GeoJSON do WordPress, caso não exista no GitHub
GEOJSON_URL = "https://nordesteagro.com/wp-content/uploads/nordeste-agro/mapas/matopibapa.geojson"

UFS_REGIONAIS = ["PA", "MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA", "TO"]

TOTAL_PONTOS_DESEJADO = 200

# Quanto maior este número, mais regular fica a seleção final
MULTIPLICADOR_CANDIDATOS = 6

TAMANHO_LOTE_OPENMETEO = 20
MAX_TENTATIVAS = 3
PAUSA_ENTRE_LOTES = 1
PAUSA_BASE_RETRY = 4
MINIMO_PONTOS_VALIDOS = 150


# ------------------------------------------------------------
# FUNÇÕES DE TEXTO E GEOJSON
# ------------------------------------------------------------

def normalizar_texto(valor):
    texto = str(valor or "").strip().upper()

    substituicoes = {
        "Á": "A",
        "À": "A",
        "Â": "A",
        "Ã": "A",
        "É": "E",
        "Ê": "E",
        "Í": "I",
        "Ó": "O",
        "Ô": "O",
        "Õ": "O",
        "Ú": "U",
        "Ç": "C",
    }

    for antigo, novo in substituicoes.items():
        texto = texto.replace(antigo, novo)

    return texto


def obter_uf_feature(feature):
    props = feature.get("properties", {}) or {}

    chaves = [
        "SIGLA_UF",
        "UF",
        "uf",
        "sigla_uf",
        "SG_UF",
        "NM_UF",
        "estado",
        "nome",
        "NOME",
        "name",
    ]

    nomes = {
        "PARA": "PA",
        "MARANHAO": "MA",
        "PIAUI": "PI",
        "CEARA": "CE",
        "RIO GRANDE DO NORTE": "RN",
        "PARAIBA": "PB",
        "PERNAMBUCO": "PE",
        "ALAGOAS": "AL",
        "SERGIPE": "SE",
        "BAHIA": "BA",
        "TOCANTINS": "TO",
    }

    for chave in chaves:
        if chave in props and props[chave] not in (None, ""):
            valor = normalizar_texto(props[chave])
            return nomes.get(valor, valor)

    return ""


def abrir_url_texto(url):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json,text/plain,*/*",
            "User-Agent": "NordesteAgro-Clima/1.0",
        },
        method="GET",
    )

    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read().decode("utf-8")


def carregar_geojson():
    for caminho in GEOJSON_LOCAL_PATHS:
        if caminho.exists():
            print(f"Carregando GeoJSON local: {caminho}")
            return json.loads(caminho.read_text(encoding="utf-8"))

    print(f"GeoJSON local não encontrado. Baixando do WordPress: {GEOJSON_URL}")
    texto = abrir_url_texto(GEOJSON_URL)
    return json.loads(texto)


def filtrar_features_regionais(geojson):
    features = []

    for feature in geojson.get("features", []):
        uf = obter_uf_feature(feature)

        if uf in UFS_REGIONAIS:
            features.append(feature)

    if not features:
        raise RuntimeError("Nenhum estado regional foi encontrado no GeoJSON.")

    return features


# ------------------------------------------------------------
# GEOMETRIA: PONTO DENTRO DE POLÍGONO
# ------------------------------------------------------------

def iterar_aneis(geometry):
    if not geometry:
        return

    tipo = geometry.get("type")
    coords = geometry.get("coordinates", [])

    if tipo == "Polygon":
        yield coords

    elif tipo == "MultiPolygon":
        for poligono in coords:
            yield poligono


def ponto_em_anel(lon, lat, anel):
    dentro = False
    n = len(anel)

    if n < 3:
        return False

    j = n - 1

    for i in range(n):
        xi, yi = anel[i][0], anel[i][1]
        xj, yj = anel[j][0], anel[j][1]

        cruza = ((yi > lat) != (yj > lat))

        if cruza:
            x_intersec = (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi

            if lon < x_intersec:
                dentro = not dentro

        j = i

    return dentro


def ponto_em_poligono(lon, lat, poligono):
    if not poligono:
        return False

    anel_externo = poligono[0]

    if not ponto_em_anel(lon, lat, anel_externo):
        return False

    # Remove buracos internos, se existirem
    for buraco in poligono[1:]:
        if ponto_em_anel(lon, lat, buraco):
            return False

    return True


def ponto_em_feature(lon, lat, feature):
    geometry = feature.get("geometry", {})

    for poligono in iterar_aneis(geometry):
        if ponto_em_poligono(lon, lat, poligono):
            return True

    return False


def encontrar_uf_do_ponto(lon, lat, features):
    for feature in features:
        if ponto_em_feature(lon, lat, feature):
            return obter_uf_feature(feature)

    return ""


def calcular_bounds(features):
    min_lon = float("inf")
    max_lon = float("-inf")
    min_lat = float("inf")
    max_lat = float("-inf")

    for feature in features:
        geometry = feature.get("geometry", {})

        for poligono in iterar_aneis(geometry):
            for anel in poligono:
                for coord in anel:
                    lon = float(coord[0])
                    lat = float(coord[1])

                    min_lon = min(min_lon, lon)
                    max_lon = max(max_lon, lon)
                    min_lat = min(min_lat, lat)
                    max_lat = max(max_lat, lat)

    if not math.isfinite(min_lon):
        raise RuntimeError("Não foi possível calcular os limites do GeoJSON.")

    return {
        "min_lon": min_lon,
        "max_lon": max_lon,
        "min_lat": min_lat,
        "max_lat": max_lat,
    }


# ------------------------------------------------------------
# MALHA UNIFORME
# ------------------------------------------------------------

def gerar_candidatos_grade(features, total_desejado):
    bounds = calcular_bounds(features)

    largura = bounds["max_lon"] - bounds["min_lon"]
    altura = bounds["max_lat"] - bounds["min_lat"]

    if largura <= 0 or altura <= 0:
        raise RuntimeError("Bounds inválidos para gerar grade.")

    # Começa com uma grade maior do que 200 para depois selecionar bem distribuído
    alvo_candidatos = total_desejado * MULTIPLICADOR_CANDIDATOS

    proporcao = largura / altura

    linhas = max(10, int(math.sqrt(alvo_candidatos / proporcao)))
    colunas = max(10, int(linhas * proporcao))

    candidatos = []

    tentativa = 0

    while len(candidatos) < alvo_candidatos and tentativa < 12:
        tentativa += 1
        candidatos = []

        passo_lon = largura / max(1, colunas - 1)
        passo_lat = altura / max(1, linhas - 1)

        for i in range(linhas):
            lat = bounds["min_lat"] + i * passo_lat

            for j in range(colunas):
                lon = bounds["min_lon"] + j * passo_lon

                uf = encontrar_uf_do_ponto(lon, lat, features)

                if uf in UFS_REGIONAIS:
                    candidatos.append(
                        {
                            "uf": uf,
                            "lat": round(lat, 6),
                            "lon": round(lon, 6),
                        }
                    )

        print(
            f"Tentativa grade {tentativa}: "
            f"{colunas} colunas x {linhas} linhas = {len(candidatos)} candidatos válidos"
        )

        colunas = int(colunas * 1.18) + 1
        linhas = int(linhas * 1.18) + 1

    if len(candidatos) < total_desejado:
        raise RuntimeError(
            f"Não foi possível gerar candidatos suficientes dentro da região. "
            f"Candidatos: {len(candidatos)}"
        )

    return candidatos


def distancia2(a, b):
    dx = a["lon"] - b["lon"]
    dy = a["lat"] - b["lat"]
    return dx * dx + dy * dy


def selecionar_pontos_uniformes(candidatos, total):
    # Ordena por latitude e longitude para reduzir aleatoriedade
    candidatos = sorted(candidatos, key=lambda p: (p["lat"], p["lon"]))

    # Primeiro ponto: mais ao noroeste da região
    primeiro = min(candidatos, key=lambda p: (p["lon"] - p["lat"]))
    selecionados = [primeiro]

    restantes = [
        p for p in candidatos
        if not (p["lat"] == primeiro["lat"] and p["lon"] == primeiro["lon"])
    ]

    # Farthest point sampling:
    # seleciona sempre o candidato mais distante dos já selecionados.
    while len(selecionados) < total and restantes:
        melhor_indice = 0
        melhor_distancia = -1

        for idx, ponto in enumerate(restantes):
            dmin = min(distancia2(ponto, s) for s in selecionados)

            if dmin > melhor_distancia:
                melhor_distancia = dmin
                melhor_indice = idx

        selecionados.append(restantes.pop(melhor_indice))

        if len(selecionados) % 25 == 0:
            print(f"Pontos selecionados: {len(selecionados)}/{total}")

    if len(selecionados) != total:
        raise RuntimeError(
            f"Seleção final não gerou {total} pontos. Gerou {len(selecionados)}."
        )

    selecionados = sorted(selecionados, key=lambda p: (p["uf"], p["lat"], p["lon"]))

    for idx, ponto in enumerate(selecionados, start=1):
        ponto["id"] = f"P{idx:03d}"
        ponto["nome"] = f"Ponto {idx:03d}"

    return selecionados


def gerar_pontos_grade_uniforme():
    geojson = carregar_geojson()
    features = filtrar_features_regionais(geojson)

    candidatos = gerar_candidatos_grade(features, TOTAL_PONTOS_DESEJADO)
    pontos = selecionar_pontos_uniformes(candidatos, TOTAL_PONTOS_DESEJADO)

    distribuicao = {}

    for p in pontos:
        distribuicao[p["uf"]] = distribuicao.get(p["uf"], 0) + 1

    print("Distribuição final por UF:")
    for uf in UFS_REGIONAIS:
        print(f"{uf}: {distribuicao.get(uf, 0)} pontos")

    return pontos, distribuicao


# ------------------------------------------------------------
# OPEN-METEO
# ------------------------------------------------------------

def montar_url_openmeteo(pontos_lote):
    latitudes = ",".join(str(p["lat"]) for p in pontos_lote)
    longitudes = ",".join(str(p["lon"]) for p in pontos_lote)

    params = {
        "latitude": latitudes,
        "longitude": longitudes,
        "hourly": "precipitation",
        "forecast_days": "4",
        "timezone": "America/Bahia",
        "precipitation_unit": "mm",
    }

    return API_URL + "?" + urllib.parse.urlencode(params)


def abrir_json_com_retry(url, descricao):
    ultimo_erro = None

    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            print(f"{descricao} - tentativa {tentativa}/{MAX_TENTATIVAS}")

            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "NordesteAgro-Clima/1.0",
                },
                method="GET",
            )

            with urllib.request.urlopen(req, timeout=90) as response:
                texto = response.read().decode("utf-8")
                return json.loads(texto)

        except urllib.error.HTTPError as erro:
            ultimo_erro = erro

            if erro.code in (429, 500, 502, 503, 504):
                espera = PAUSA_BASE_RETRY * tentativa
                print(f"Erro HTTP {erro.code}. Aguardando {espera}s...")
                time.sleep(espera)
                continue

            raise

        except Exception as erro:
            ultimo_erro = erro
            espera = PAUSA_BASE_RETRY * tentativa
            print(f"Erro na consulta: {erro}. Aguardando {espera}s...")
            time.sleep(espera)

    raise RuntimeError(f"Falha após {MAX_TENTATIVAS} tentativas em {descricao}: {ultimo_erro}")


def soma_intervalo(valores, inicio, fim):
    total = 0.0

    for v in valores[inicio:fim]:
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
                f"{ponto['nome']} retornou menos de 72 horas de precipitação."
            )

        resultados.append(
            {
                "id": ponto["id"],
                "uf": ponto["uf"],
                "nome": ponto["nome"],
                "lat": ponto["lat"],
                "lon": ponto["lon"],
                "precipitacao_mm": {
                    "24h": soma_intervalo(precipitacao, 0, 24),
                    "48h": soma_intervalo(precipitacao, 24, 48),
                    "72h": soma_intervalo(precipitacao, 48, 72),
                },
            }
        )

    return resultados


def consultar_lote(pontos_lote, numero_lote):
    url = montar_url_openmeteo(pontos_lote)

    dados = abrir_json_com_retry(
        url,
        f"Consultando lote {numero_lote} com {len(pontos_lote)} pontos",
    )

    return processar_resposta_lote(pontos_lote, dados)


def consultar_ponto_individual(ponto):
    url = montar_url_openmeteo([ponto])

    dados = abrir_json_com_retry(
        url,
        f"Consultando ponto individual {ponto['nome']} - {ponto['uf']}",
    )

    return processar_resposta_lote([ponto], dados)[0]


def consultar_openmeteo(pontos_grade):
    todos_resultados = []
    erros = []
    numero_lote = 0

    for i in range(0, len(pontos_grade), TAMANHO_LOTE_OPENMETEO):
        numero_lote += 1
        lote = pontos_grade[i:i + TAMANHO_LOTE_OPENMETEO]

        try:
            resultados = consultar_lote(lote, numero_lote)
            todos_resultados.extend(resultados)

        except Exception as erro_lote:
            print(f"Erro no lote {numero_lote}: {erro_lote}")
            print("Tentando recuperar ponto por ponto...")

            for ponto in lote:
                try:
                    resultado = consultar_ponto_individual(ponto)
                    todos_resultados.append(resultado)

                except Exception as erro_ponto:
                    print(f"Erro no ponto {ponto['nome']} - {ponto['uf']}: {erro_ponto}")

                    erros.append(
                        {
                            "id": ponto["id"],
                            "uf": ponto["uf"],
                            "nome": ponto["nome"],
                            "lat": ponto["lat"],
                            "lon": ponto["lon"],
                            "erro": str(erro_ponto),
                        }
                    )

        time.sleep(PAUSA_ENTRE_LOTES)

    return todos_resultados, erros


# ------------------------------------------------------------
# JSON FINAL
# ------------------------------------------------------------

def gerar_periodos(pontos):
    periodos = {
        "24h": [],
        "48h": [],
        "72h": [],
    }

    for p in pontos:
        for periodo in periodos.keys():
            periodos[periodo].append(
                {
                    "id": p["id"],
                    "uf": p["uf"],
                    "nome": p["nome"],
                    "lat": p["lat"],
                    "lon": p["lon"],
                    "mm": p["precipitacao_mm"][periodo],
                }
            )

    return periodos


def resumo_periodo(pontos):
    valores = [float(p["mm"]) for p in pontos]

    if not valores:
        return {
            "min": 0,
            "media": 0,
            "max": 0,
        }

    return {
        "min": round(min(valores), 1),
        "media": round(sum(valores) / len(valores), 1),
        "max": round(max(valores), 1),
    }


def carregar_backup_valido():
    if BACKUP_JSON.exists():
        print("Carregando último JSON válido como fallback...")
        return json.loads(BACKUP_JSON.read_text(encoding="utf-8"))

    if OUT_JSON.exists():
        print("Carregando JSON atual como fallback...")
        return json.loads(OUT_JSON.read_text(encoding="utf-8"))

    return None


def salvar_payload(payload):
    OUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    BACKUP_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Arquivo gerado: {OUT_JSON}")
    print(f"Backup atualizado: {BACKUP_JSON}")


def gerar_payload(pontos_consultados, erros, distribuicao):
    periodos = gerar_periodos(pontos_consultados)

    return {
        "ok": True,
        "fonte": FONTE,
        "modelo": MODELO,
        "area": AREA,
        "oficial_inmet": False,
        "simulado": False,
        "tipo": "previsao_meteorologica_por_grade_uniforme",
        "metodo": (
            "Malha uniforme com 200 pontos gerados dentro do GeoJSON regional "
            "Nordeste + Tocantins + Pará; consulta Open-Meteo Forecast API por coordenada; "
            "cálculo de acumulados 24h, 48h e 72h."
        ),
        "malha": {
            "tipo": "grade_uniforme",
            "total_pontos_planejados": TOTAL_PONTOS_DESEJADO,
            "total_pontos_validos": len(pontos_consultados),
            "distribuicao_por_uf": distribuicao,
        },
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "total_pontos": len(pontos_consultados),
        "total_erros": len(erros),
        "erros": erros[:50],
        "periodos": {
            "24h": {
                "label": "Previsão acumulada 24h",
                "resumo": resumo_periodo(periodos["24h"]),
                "pontos": periodos["24h"],
            },
            "48h": {
                "label": "Previsão acumulada 48h",
                "resumo": resumo_periodo(periodos["48h"]),
                "pontos": periodos["48h"],
            },
            "72h": {
                "label": "Previsão acumulada 72h",
                "resumo": resumo_periodo(periodos["72h"]),
                "pontos": periodos["72h"],
            },
        },
    }


def aplicar_fallback(motivo):
    backup = carregar_backup_valido()

    if not backup:
        raise RuntimeError(
            "Coleta falhou e não existe JSON anterior válido para fallback."
        )

    backup["ok"] = True
    backup["fallback_usado"] = True
    backup["fallback_motivo"] = motivo
    backup["fallback_em_utc"] = datetime.now(timezone.utc).isoformat()

    OUT_JSON.write_text(
        json.dumps(backup, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Fallback aplicado com sucesso.")
    print(f"Motivo: {motivo}")


def main():
    print("Iniciando coleta por malha uniforme: Nordeste + Tocantins + Pará...")

    try:
        pontos_grade, distribuicao = gerar_pontos_grade_uniforme()

        print(f"Total de pontos planejados: {len(pontos_grade)}")
        print("Consultando Open-Meteo...")

        pontos_consultados, erros = consultar_openmeteo(pontos_grade)

        if len(pontos_consultados) < MINIMO_PONTOS_VALIDOS:
            motivo = (
                f"Poucos pontos válidos retornados: {len(pontos_consultados)}. "
                f"Mínimo exigido: {MINIMO_PONTOS_VALIDOS}."
            )
            print(motivo)
            aplicar_fallback(motivo)
            return

        payload = gerar_payload(pontos_consultados, erros, distribuicao)
        salvar_payload(payload)

        print(f"Total de pontos válidos: {len(pontos_consultados)}")
        print(f"Total de erros: {len(erros)}")

        for periodo, dados_periodo in payload["periodos"].items():
            print(periodo, dados_periodo["resumo"])

    except Exception as erro:
        motivo = str(erro)
        print(f"Erro geral na coleta: {motivo}")
        aplicar_fallback(motivo)


if __name__ == "__main__":
    main()
