import json
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

INMET_API_BASE = "https://apitempo.inmet.gov.br"
UFS_ALVO = {"PA", "MA", "PI", "TO", "BA", "CE", "RN", "PB", "PE", "AL", "SE"}


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
        return json.loads(response.read().decode("utf-8"))


def normalizar_numero(valor):
    if valor is None:
        return None
    texto = str(valor).strip().replace(",", ".")
    if texto in {"", "-", "null", "None", "NaN"}:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def primeiro_valor(dicionario, chaves):
    for chave in chaves:
        if chave in dicionario and dicionario[chave] not in (None, ""):
            return dicionario[chave]
    return None


catalogo = abrir_json(f"{INMET_API_BASE}/estacoes/T")

estacoes = []
for e in catalogo:
    uf = str(primeiro_valor(e, ["SG_ESTADO", "UF", "uf"]) or "").upper().strip()
    codigo = str(primeiro_valor(e, ["CD_ESTACAO", "codigo", "CODIGO"]) or "").strip()
    nome = str(primeiro_valor(e, ["DC_NOME", "nome", "NOME"]) or codigo).strip()

    if uf in UFS_ALVO and codigo:
        estacoes.append({"uf": uf, "codigo": codigo, "nome": nome})

print("Estações encontradas:", len(estacoes))
print("Primeiras estações:", estacoes[:10])

agora = datetime.now(timezone.utc)
data_fim = agora.date().isoformat()
data_inicio = (agora - timedelta(days=3)).date().isoformat()

print("Período de teste:", data_inicio, "até", data_fim)

for estacao in estacoes[:10]:
    codigo = estacao["codigo"]
    url = f"{INMET_API_BASE}/estacao/{data_inicio}/{data_fim}/{codigo}"

    print("\nConsultando:", estacao)

    try:
        dados = abrir_json(url)
        print("Quantidade de registros:", len(dados) if isinstance(dados, list) else "não lista")

        if isinstance(dados, list) and dados:
            print("Campos do primeiro registro:")
            print(list(dados[0].keys()))
            print("Primeiro registro completo:")
            print(json.dumps(dados[0], ensure_ascii=False, indent=2)[:2000])

            possiveis = []
            for r in dados[:10]:
                for chave, valor in r.items():
                    if "CHUVA" in chave.upper() or "PREC" in chave.upper():
                        possiveis.append((chave, valor))

            print("Campos possíveis de chuva encontrados:")
            print(possiveis[:20])

            break

    except Exception as erro:
        print("Erro nessa estação:", erro)
