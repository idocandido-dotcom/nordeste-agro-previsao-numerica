import json
import os
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

WORDPRESS_URL = os.environ["WORDPRESS_URL"].rstrip("/")
WORDPRESS_TOKEN = os.environ["WORDPRESS_TOKEN"]

ENDPOINT_IMPORTAR = f"{WORDPRESS_URL}/wp-json/nordeste-agro/v1/importar-previsao-numerica"
INMET_API_BASE = "https://apitempo.inmet.gov.br"

UFS_ALVO = {"PA", "MA", "PI", "TO", "BA", "CE", "RN", "PB", "PE", "AL", "SE"}
HORAS_ACUMULO = 24


def abrir_url(url, timeout=90):
    req = Request(
        url,
        headers={
            "Accept": "application/json,text/plain,*/*",
            "User-Agent": "NordesteAgro-GitHubActions/1.0"
        },
        method="GET"
    )

    with urlopen(req, timeout=timeout) as response:
        status = response.status
        content_type = response.headers.get("Content-Type", "")
        texto = response.read().decode("utf-8", errors="ignore")
        return status, content_type, texto


def abrir_json(url, timeout=90):
    status, content_type, texto = abrir_url(url, timeout=timeout)

    if status < 200 or status >= 300:
        raise RuntimeError(f"HTTP {status} em {url}")

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        trecho = texto[:300].replace("\n", " ")
        raise RuntimeError(
            f"Resposta não veio em JSON. Content-Type={content_type}. "
            f"Trecho inicial: {trecho}"
        )


def primeiro_valor(dicionario, chaves):
    for chave in chaves:
        if chave in dicionario and dicionario[chave] not in (None, ""):
            return dicionario[chave]
    return None


def normalizar_numero(valor):
    if valor is None:
        return None

    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()

    if texto in {"", "-", "null", "None", "NaN"}:
        return None

    texto = texto.replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return None


def buscar_catalogo_estacoes():
    dados = abrir_json(f"{INMET_API_BASE}/estacoes/T")

    if not isinstance(dados, list) or not dados:
        raise RuntimeError("Catálogo de estações do INMET veio vazio ou inválido.")

    return dados


def filtrar_estacoes(catalogo):
    estacoes = []

    for e in catalogo:
        uf = str(primeiro_valor(e, ["SG_ESTADO", "UF", "uf"]) or "").upper().strip()
        codigo = str(primeiro_valor(e, ["CD_ESTACAO", "codigo", "CODIGO"]) or "").strip()
        nome = str(primeiro_valor(e, ["DC_NOME", "nome", "NOME"]) or codigo).strip()

        lat = normalizar_numero(primeiro_valor(e, ["VL_LATITUDE", "latitude", "LATITUDE", "lat"]))
        lon = normalizar_numero(primeiro_valor(e, ["VL_LONGITUDE", "longitude", "LONGITUDE", "lon"]))

        if uf not in UFS_ALVO:
            continue

        if not codigo or lat is None or lon is None:
            continue

        estacoes.append({
            "uf": uf,
            "codigo": codigo,
            "nome": nome,
            "lat": lat,
            "lon": lon
        })

    if not estacoes:
        raise RuntimeError("Nenhuma estação INMET válida encontrada para os estados-alvo.")

    return estacoes


def tentar_urls_dados_estacao(codigo, data_inicio, data_fim):
    urls = [
        f"{INMET_API_BASE}/estacao/{data_inicio}/{data_fim}/{codigo}",
        f"{INMET_API_BASE}/estacao/dados/{data_inicio}/{data_fim}/{codigo}",
        f"{INMET_API_BASE}/estacao/{codigo}/{data_inicio}/{data_fim}",
        f"{INMET_API_BASE}/dados/estacao/{data_inicio}/{data_fim}/{codigo}",
    ]

    erros = []

    for url in urls:
        try:
            dados = abrir_json(url)

            if isinstance(dados, list):
                return dados, url

            erros.append(f"{url} retornou JSON, mas não lista.")
        except Exception as erro:
            erros.append(f"{url} -> {erro}")

    raise RuntimeError("Nenhuma rota de dados horários retornou JSON válido. " + " | ".join(erros[:2]))


def chuva_registro(registro):
    possiveis_chaves = [
        "CHUVA",
        "chuva",
        "PRECIPITACAO",
        "PRECIPITAÇÃO",
        "precipitacao",
        "PRECIPITACAO_TOTAL",
        "precipitacao_total"
    ]

    for chave in possiveis_chaves:
        if chave in registro:
            return normalizar_numero(registro[chave])

    # Busca flexível por chave contendo CHUVA ou PREC
    for chave, valor in registro.items():
        chave_upper = str(chave).upper()
        if "CHUVA" in chave_upper or "PREC" in chave_upper:
            return normalizar_numero(valor)

    return None


def acumular_chuva_estacao(estacao, data_inicio, data_fim):
    dados, url_usada = tentar_urls_dados_estacao(estacao["codigo"], data_inicio, data_fim)

    soma = 0.0
    leituras_validas = 0

    for r in dados:
        if not isinstance(r, dict):
            continue

        chuva = chuva_registro(r)

        if chuva is None:
            continue

        if chuva < 0:
            continue

        soma += chuva
        leituras_validas += 1

    if leituras_validas == 0:
        return None

    return {
        "uf": estacao["uf"],
        "codigo_estacao": estacao["codigo"],
        "estacao": estacao["nome"],
        "lat": estacao["lat"],
        "lon": estacao["lon"],
        "mm": round(soma, 1),
        "leituras_validas": leituras_validas,
        "url_dados": url_usada,
        "periodo_horas": HORAS_ACUMULO
    }


def montar_payload():
    agora = datetime.now(timezone.utc)

    # Consulta uma janela um pouco maior para compensar atraso de disponibilização.
    data_fim = agora.date()
    data_inicio = (agora - timedelta(hours=HORAS_ACUMULO + 12)).date()

    data_inicio_str = data_inicio.isoformat()
    data_fim_str = data_fim.isoformat()

    catalogo = buscar_catalogo_estacoes()
    estacoes = filtrar_estacoes(catalogo)

    print(f"Estações oficiais INMET encontradas nos estados-alvo: {len(estacoes)}")
    print(f"Período consultado: {data_inicio_str} até {data_fim_str}")

    pontos = []
    erros = []

    for estacao in estacoes:
        try:
            ponto = acumular_chuva_estacao(estacao, data_inicio_str, data_fim_str)

            if ponto:
                pontos.append(ponto)

        except Exception as erro:
            erros.append({
                "uf": estacao["uf"],
                "codigo": estacao["codigo"],
                "nome": estacao["nome"],
                "erro": str(erro)[:500]
            })

    print(f"Pontos oficiais válidos encontrados: {len(pontos)}")
    print(f"Estações com erro/sem dado: {len(erros)}")

    if not pontos:
        print("Amostra de erros:")
        print(json.dumps(erros[:5], ensure_ascii=False, indent=2))

        raise RuntimeError(
            "Nenhum ponto oficial de precipitação do INMET foi obtido. "
            "Por segurança, nenhum dado será enviado ao WordPress."
        )

    return {
        "ok": True,
        "fonte": "INMET - Estações Meteorológicas Automáticas",
        "modo": "observado_oficial_inmet",
        "tipo_dado": "precipitacao_observada_24h",
        "oficial": True,
        "simulado": False,
        "observacao": (
            "Dados oficiais observados das estações automáticas do INMET. "
            "Não contém simulação. Se o INMET não retornar dado válido, "
            "o coletor não publica valor inventado."
        ),
        "periodo_observado": {
            "horas": HORAS_ACUMULO,
            "data_inicio_consulta": data_inicio_str,
            "data_fim_consulta": data_fim_str
        },
        "total_pontos_por_periodo": len(pontos),
        "erros_estacoes_ignoradas": erros[:50],
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "periodos": {
            "24h": {
                "legenda": "Chuva observada oficial - últimas 24h",
                "pontos": pontos
            },
            "48h": {
                "legenda": "Chuva observada oficial - últimas 24h",
                "pontos": pontos
            },
            "72h": {
                "legenda": "Chuva observada oficial - últimas 24h",
                "pontos": pontos
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

print(f"Enviando dados oficiais INMET para: {ENDPOINT_IMPORTAR}")
print("Fonte:", dados["fonte"])
print("Modo:", dados["modo"])
print("Pontos oficiais válidos:", dados["total_pontos_por_periodo"])

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
