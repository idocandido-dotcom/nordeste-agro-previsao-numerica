import json
import os
import math
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

WORDPRESS_URL = os.environ["WORDPRESS_URL"].rstrip("/")
WORDPRESS_TOKEN = os.environ["WORDPRESS_TOKEN"]

ENDPOINT_IMPORTAR = f"{WORDPRESS_URL}/wp-json/nordeste-agro/v1/importar-previsao-numerica"

# API pública usada pelo portal Tempo/INMET para estações automáticas.
# Se o INMET alterar esse endpoint, o coletor falha e NÃO envia dado simulado.
INMET_API_BASE = "https://apitempo.inmet.gov.br"

# Estados do projeto Nordeste Agro / MATOPIBA + PA
UFS_ALVO = {
    "PA", "MA", "PI", "TO", "BA", "CE", "RN", "PB", "PE", "AL", "SE"
}

# Janela para chuva observada acumulada.
HORAS_ACUMULO = 24


def abrir_json(url, timeout=90):
    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "NordesteAgro-GitHubActions/1.0"
        },
        method="GET"
    )

    with urlopen(req, timeout=timeout) as response:
        texto = response.read().decode("utf-8")
        return json.loads(texto)


def normalizar_numero(valor):
    if valor is None:
        return None

    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()

    if texto in {"", "null", "None", "-", "NaN"}:
        return None

    texto = texto.replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return None


def primeiro_valor(dicionario, chaves):
    for chave in chaves:
        if chave in dicionario and dicionario[chave] not in (None, ""):
            return dicionario[chave]
    return None


def buscar_catalogo_estacoes():
    """
    Busca catálogo oficial das estações automáticas.
    Tentamos endpoints conhecidos do portal INMET.
    Se nenhum funcionar, o coletor para.
    """
    urls = [
        f"{INMET_API_BASE}/estacoes/T",
        f"{INMET_API_BASE}/estacoes",
    ]

    ultimo_erro = None

    for url in urls:
        try:
            dados = abrir_json(url)
            if isinstance(dados, list) and dados:
                return dados
        except Exception as erro:
            ultimo_erro = erro

    raise RuntimeError(f"Não foi possível carregar o catálogo de estações do INMET. Último erro: {ultimo_erro}")


def filtrar_estacoes_alvo(catalogo):
    estacoes = []

    for e in catalogo:
        uf = str(primeiro_valor(e, ["SG_ESTADO", "UF", "uf", "CD_UF", "sg_estado"]) or "").upper().strip()
        codigo = str(primeiro_valor(e, ["CD_ESTACAO", "codigo", "CODIGO", "id", "DC_NOME"]) or "").strip()
        nome = str(primeiro_valor(e, ["DC_NOME", "nome", "NOME", "estacao"]) or codigo).strip()

        lat = normalizar_numero(primeiro_valor(e, ["VL_LATITUDE", "latitude", "LATITUDE", "lat"]))
        lon = normalizar_numero(primeiro_valor(e, ["VL_LONGITUDE", "longitude", "LONGITUDE", "lon"]))

        if not uf or uf not in UFS_ALVO:
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
        raise RuntimeError("Nenhuma estação oficial do INMET encontrada para os estados-alvo.")

    return estacoes


def buscar_dados_estacao(codigo, data_inicio, data_fim):
    """
    Busca dados horários oficiais de uma estação automática no período.
    Tentamos padrões usados pelo serviço público do INMET.
    Se o endpoint mudar, a estação é ignorada; se todas falharem, o coletor para.
    """
    urls = [
        f"{INMET_API_BASE}/estacao/{data_inicio}/{data_fim}/{codigo}",
        f"{INMET_API_BASE}/estacao/dados/{data_inicio}/{data_fim}/{codigo}",
    ]

    ultimo_erro = None

    for url in urls:
        try:
            dados = abrir_json(url)
            if isinstance(dados, list):
                return dados
        except Exception as erro:
            ultimo_erro = erro

    raise RuntimeError(f"Falha ao buscar dados da estação {codigo}. Último erro: {ultimo_erro}")


def chuva_registro(registro):
    """
    Campos comuns de precipitação horária nos retornos do INMET.
    Normalmente aparece como CHUVA.
    """
    valor = primeiro_valor(
        registro,
        [
            "CHUVA",
            "chuva",
            "PRECIPITACAO",
            "PRECIPITAÇÃO",
            "precipitacao",
            "PRE_INS"
        ]
    )
    return normalizar_numero(valor)


def acumular_chuva_24h(estacao, data_inicio, data_fim):
    dados = buscar_dados_estacao(estacao["codigo"], data_inicio, data_fim)

    soma = 0.0
    leituras_validas = 0

    for r in dados:
        chuva = chuva_registro(r)

        if chuva is None:
            continue

        # Precipitação negativa não é válida.
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
        "periodo_horas": HORAS_ACUMULO
    }


def montar_payload():
    agora_utc = datetime.now(timezone.utc)
    data_fim = agora_utc.date()
    data_inicio = (agora_utc - timedelta(hours=HORAS_ACUMULO + 6)).date()

    data_inicio_str = data_inicio.isoformat()
    data_fim_str = data_fim.isoformat()

    catalogo = buscar_catalogo_estacoes()
    estacoes = filtrar_estacoes_alvo(catalogo)

    print(f"Estações oficiais INMET encontradas nos estados-alvo: {len(estacoes)}")
    print(f"Período consultado: {data_inicio_str} a {data_fim_str}")

    pontos = []
    erros = []

    for estacao in estacoes:
        try:
            ponto = acumular_chuva_24h(estacao, data_inicio_str, data_fim_str)
            if ponto is not None:
                pontos.append(ponto)
        except Exception as erro:
            erros.append({
                "codigo": estacao["codigo"],
                "uf": estacao["uf"],
                "erro": str(erro)
            })

    if not pontos:
        raise RuntimeError(
            "Nenhum ponto oficial de precipitação do INMET foi obtido. "
            "Por segurança, nenhum dado será enviado ao WordPress."
        )

    # Este payload mantém a mesma estrutura que o HTML já consome.
    # Os três períodos ficam iguais porque se trata de chuva observada acumulada.
    return {
        "ok": True,
        "fonte": "INMET - Estações Meteorológicas Automáticas",
        "modo": "observado_oficial_inmet",
        "tipo_dado": "precipitacao_observada_24h",
        "oficial": True,
        "simulado": False,
        "observacao": (
            "Dados oficiais observados das estações automáticas do INMET. "
            "Não contém simulação. Quando a API do INMET não retorna dado válido, "
            "o coletor não publica valor inventado."
        ),
        "periodo_observado": {
            "horas": HORAS_ACUMULO,
            "data_inicio_consulta": data_inicio_str,
            "data_fim_consulta": data_fim_str
        },
        "total_pontos_por_periodo": len(pontos),
        "erros_estacoes_ignoradas": erros[:30],
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
