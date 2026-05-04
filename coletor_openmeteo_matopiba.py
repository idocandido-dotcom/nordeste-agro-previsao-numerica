import json
import time
import shutil
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# COLETOR NORDESTE + TOCANTINS + PARÁ — OPEN-METEO
# ============================================================
# Este script:
# - consulta a Open-Meteo Forecast API;
# - usa pontos reais por coordenada;
# - calcula precipitação acumulada prevista para 24h, 48h e 72h;
# - salva JSON para o WordPress gerar o mapa e o slide.
#
# Versão otimizada:
# - menos tentativas;
# - menos tempo de espera;
# - fallback para último JSON válido;
# - não inventa dados;
# - não simula valores;
# - se a API falhar muito, mantém o mapa anterior funcionando.
# ============================================================


OUT_DIR = Path("public/clima/matopiba")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_JSON = OUT_DIR / "openmeteo_matopiba.json"
BACKUP_JSON = OUT_DIR / "openmeteo_matopiba_ultimo_valido.json"

FONTE = "Open-Meteo Forecast API"
MODELO = "Best match / modelos meteorológicos combinados pela Open-Meteo"
AREA = "Nordeste + Tocantins + Pará"

API_URL = "https://api.open-meteo.com/v1/forecast"

# Ajustes de velocidade e segurança
TAMANHO_LOTE = 8
MAX_TENTATIVAS = 3
PAUSA_ENTRE_LOTES = 1
PAUSA_BASE_RETRY = 4
MINIMO_PONTOS_VALIDOS = 35


PONTOS = [
    # PARÁ
    {"uf": "PA", "nome": "Altamira", "lat": -3.2033, "lon": -52.2064},
    {"uf": "PA", "nome": "Santarém", "lat": -2.4431, "lon": -54.7083},
    {"uf": "PA", "nome": "Marabá", "lat": -5.3686, "lon": -49.1178},
    {"uf": "PA", "nome": "Paragominas", "lat": -2.9958, "lon": -47.3522},
    {"uf": "PA", "nome": "Redenção", "lat": -8.0253, "lon": -50.0317},
    {"uf": "PA", "nome": "Conceição do Araguaia", "lat": -8.2578, "lon": -49.2647},
    {"uf": "PA", "nome": "Castanhal", "lat": -1.2939, "lon": -47.9264},
    {"uf": "PA", "nome": "Tailândia", "lat": -2.9458, "lon": -48.9489},
    {"uf": "PA", "nome": "Uruará", "lat": -3.7158, "lon": -53.7397},
    {"uf": "PA", "nome": "Novo Progresso", "lat": -7.1431, "lon": -55.3786},

    # MARANHÃO
    {"uf": "MA", "nome": "Balsas", "lat": -7.5325, "lon": -46.0356},
    {"uf": "MA", "nome": "Tasso Fragoso", "lat": -8.4724, "lon": -45.7545},
    {"uf": "MA", "nome": "Alto Parnaíba", "lat": -9.1089, "lon": -45.9300},
    {"uf": "MA", "nome": "Riachão", "lat": -7.3617, "lon": -46.6172},
    {"uf": "MA", "nome": "São Raimundo das Mangabeiras", "lat": -7.0219, "lon": -45.4806},
    {"uf": "MA", "nome": "Imperatriz", "lat": -5.5264, "lon": -47.4917},
    {"uf": "MA", "nome": "Carolina", "lat": -7.3353, "lon": -47.4692},
    {"uf": "MA", "nome": "Chapadinha", "lat": -3.7417, "lon": -43.3603},
    {"uf": "MA", "nome": "Caxias", "lat": -4.8589, "lon": -43.3561},
    {"uf": "MA", "nome": "São Luís", "lat": -2.5307, "lon": -44.3068},

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
    {"uf": "PI", "nome": "Teresina", "lat": -5.0892, "lon": -42.8019},
    {"uf": "PI", "nome": "Floriano", "lat": -6.7718, "lon": -43.0241},
    {"uf": "PI", "nome": "Picos", "lat": -7.0778, "lon": -41.4672},
    {"uf": "PI", "nome": "Santa Filomena", "lat": -9.1128, "lon": -45.9211},
    {"uf": "PI", "nome": "Ribeiro Gonçalves", "lat": -7.5583, "lon": -45.2444},

    # CEARÁ
    {"uf": "CE", "nome": "Fortaleza", "lat": -3.7319, "lon": -38.5267},
    {"uf": "CE", "nome": "Sobral", "lat": -3.6861, "lon": -40.3497},
    {"uf": "CE", "nome": "Quixadá", "lat": -4.9708, "lon": -39.0153},
    {"uf": "CE", "nome": "Iguatu", "lat": -6.3594, "lon": -39.2986},
    {"uf": "CE", "nome": "Crateús", "lat": -5.1783, "lon": -40.6775},
    {"uf": "CE", "nome": "Juazeiro do Norte", "lat": -7.2128, "lon": -39.3153},
    {"uf": "CE", "nome": "Limoeiro do Norte", "lat": -5.1456, "lon": -38.0981},
    {"uf": "CE", "nome": "Tianguá", "lat": -3.7322, "lon": -40.9917},

    # RIO GRANDE DO NORTE
    {"uf": "RN", "nome": "Natal", "lat": -5.7945, "lon": -35.2110},
    {"uf": "RN", "nome": "Mossoró", "lat": -5.1875, "lon": -37.3442},
    {"uf": "RN", "nome": "Caicó", "lat": -6.4591, "lon": -37.0978},
    {"uf": "RN", "nome": "Pau dos Ferros", "lat": -6.1103, "lon": -38.2067},
    {"uf": "RN", "nome": "Assu", "lat": -5.5767, "lon": -36.9086},
    {"uf": "RN", "nome": "Apodi", "lat": -5.6647, "lon": -37.7989},

    # PARAÍBA
    {"uf": "PB", "nome": "João Pessoa", "lat": -7.1195, "lon": -34.8450},
    {"uf": "PB", "nome": "Campina Grande", "lat": -7.2306, "lon": -35.8811},
    {"uf": "PB", "nome": "Patos", "lat": -7.0244, "lon": -37.2800},
    {"uf": "PB", "nome": "Sousa", "lat": -6.7592, "lon": -38.2281},
    {"uf": "PB", "nome": "Cajazeiras", "lat": -6.8903, "lon": -38.5553},
    {"uf": "PB", "nome": "Monteiro", "lat": -7.8894, "lon": -37.1200},

    # PERNAMBUCO
    {"uf": "PE", "nome": "Recife", "lat": -8.0476, "lon": -34.8770},
    {"uf": "PE", "nome": "Petrolina", "lat": -9.3891, "lon": -40.5027},
    {"uf": "PE", "nome": "Caruaru", "lat": -8.2846, "lon": -35.9702},
    {"uf": "PE", "nome": "Garanhuns", "lat": -8.8903, "lon": -36.4928},
    {"uf": "PE", "nome": "Serra Talhada", "lat": -7.9919, "lon": -38.2988},
    {"uf": "PE", "nome": "Araripina", "lat": -7.5767, "lon": -40.4983},
    {"uf": "PE", "nome": "Salgueiro", "lat": -8.0742, "lon": -39.1192},

    # ALAGOAS
    {"uf": "AL", "nome": "Maceió", "lat": -9.6498, "lon": -35.7089},
    {"uf": "AL", "nome": "Arapiraca", "lat": -9.7525, "lon": -36.6611},
    {"uf": "AL", "nome": "Penedo", "lat": -10.2900, "lon": -36.5864},
    {"uf": "AL", "nome": "Palmeira dos Índios", "lat": -9.4056, "lon": -36.6328},
    {"uf": "AL", "nome": "Santana do Ipanema", "lat": -9.3783, "lon": -37.2453},

    # SERGIPE
    {"uf": "SE", "nome": "Aracaju", "lat": -10.9472, "lon": -37.0731},
    {"uf": "SE", "nome": "Itabaiana", "lat": -10.6850, "lon": -37.4253},
    {"uf": "SE", "nome": "Nossa Senhora da Glória", "lat": -10.2158, "lon": -37.4211},
    {"uf": "SE", "nome": "Lagarto", "lat": -10.9172, "lon": -37.6500},
    {"uf": "SE", "nome": "Estância", "lat": -11.2683, "lon": -37.4383},

    # BAHIA
    {"uf": "BA", "nome": "Salvador", "lat": -12.9777, "lon": -38.5016},
    {"uf": "BA", "nome": "Feira de Santana", "lat": -12.2664, "lon": -38.9663},
    {"uf": "BA", "nome": "Barreiras", "lat": -12.1528, "lon": -44.9900},
    {"uf": "BA", "nome": "Luís Eduardo Magalhães", "lat": -12.0956, "lon": -45.7867},
    {"uf": "BA", "nome": "São Desidério", "lat": -12.3639, "lon": -44.9731},
    {"uf": "BA", "nome": "Formosa do Rio Preto", "lat": -11.0483, "lon": -45.1931},
    {"uf": "BA", "nome": "Correntina", "lat": -13.3436, "lon": -44.6367},
    {"uf": "BA", "nome": "Vitória da Conquista", "lat": -14.8619, "lon": -40.8442},
    {"uf": "BA", "nome": "Ilhéus", "lat": -14.7930, "lon": -39.0460},
    {"uf": "BA", "nome": "Juazeiro", "lat": -9.4167, "lon": -40.5033},
]


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


def abrir_json_com_retry(url, descricao):
    ultimo_erro = None

    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            print(f"{descricao} - tentativa {tentativa}/{MAX_TENTATIVAS}")

            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "NordesteAgro-Clima/1.0"
                },
                method="GET"
            )

            with urllib.request.urlopen(req, timeout=90) as response:
                texto = response.read().decode("utf-8")
                return json.loads(texto)

        except urllib.error.HTTPError as erro:
            ultimo_erro = erro

            if erro.code in (429, 500, 502, 503, 504):
                espera = PAUSA_BASE_RETRY * tentativa
                print(f"Erro HTTP {erro.code}. Aguardando {espera}s e tentando novamente...")
                time.sleep(espera)
                continue

            raise

        except Exception as erro:
            ultimo_erro = erro
            espera = PAUSA_BASE_RETRY * tentativa
            print(f"Erro na consulta: {erro}. Aguardando {espera}s e tentando novamente...")
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
                f"Ponto {ponto['nome']} retornou menos de 72 horas de precipitação."
            )

        resultados.append({
            "uf": ponto["uf"],
            "nome": ponto["nome"],
            "lat": ponto["lat"],
            "lon": ponto["lon"],
            "precipitacao_mm": {
                "24h": soma_intervalo(precipitacao, 0, 24),
                "48h": soma_intervalo(precipitacao, 24, 48),
                "72h": soma_intervalo(precipitacao, 48, 72)
            }
        })

    return resultados


def consultar_lote(pontos_lote, numero_lote):
    url = montar_url(pontos_lote)
    dados = abrir_json_com_retry(url, f"Consultando lote {numero_lote} com {len(pontos_lote)} pontos")
    return processar_resposta_lote(pontos_lote, dados)


def consultar_ponto_individual(ponto):
    url = montar_url([ponto])
    dados = abrir_json_com_retry(url, f"Consultando ponto individual {ponto['nome']} - {ponto['uf']}")
    return processar_resposta_lote([ponto], dados)[0]


def consultar_openmeteo():
    todos_resultados = []
    erros = []

    numero_lote = 0

    for i in range(0, len(PONTOS), TAMANHO_LOTE):
        numero_lote += 1
        lote = PONTOS[i:i + TAMANHO_LOTE]

        try:
            resultados = consultar_lote(lote, numero_lote)
            todos_resultados.extend(resultados)

        except Exception as erro_lote:
            print(f"Erro no lote {numero_lote}: {erro_lote}")
            print("Tentando recuperar lote ponto por ponto...")

            for ponto in lote:
                try:
                    resultado = consultar_ponto_individual(ponto)
                    todos_resultados.append(resultado)
                except Exception as erro_ponto:
                    print(f"Erro no ponto {ponto['nome']} - {ponto['uf']}: {erro_ponto}")
                    erros.append({
                        "uf": ponto["uf"],
                        "nome": ponto["nome"],
                        "lat": ponto["lat"],
                        "lon": ponto["lon"],
                        "erro": str(erro_ponto)
                    })

        time.sleep(PAUSA_ENTRE_LOTES)

    return todos_resultados, erros


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
        encoding="utf-8"
    )

    BACKUP_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Arquivo gerado: {OUT_JSON}")
    print(f"Backup atualizado: {BACKUP_JSON}")


def gerar_payload(pontos, erros):
    periodos = gerar_periodos(pontos)

    return {
        "ok": True,
        "fonte": FONTE,
        "modelo": MODELO,
        "area": AREA,
        "oficial_inmet": False,
        "simulado": False,
        "tipo": "previsao_meteorologica_por_coordenada",
        "metodo": "Consulta Open-Meteo Forecast API por pontos do Nordeste, Tocantins e Pará; cálculo de acumulados 24h, 48h e 72h",
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "total_pontos": len(pontos),
        "total_erros": len(erros),
        "erros": erros[:30],
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
        encoding="utf-8"
    )

    print("Fallback aplicado com sucesso.")
    print(f"Motivo: {motivo}")


def main():
    print("Iniciando coleta Open-Meteo: Nordeste + Tocantins + Pará...")

    try:
        pontos, erros = consultar_openmeteo()

        if len(pontos) < MINIMO_PONTOS_VALIDOS:
            motivo = (
                f"Poucos pontos válidos retornados: {len(pontos)}. "
                f"Mínimo exigido: {MINIMO_PONTOS_VALIDOS}."
            )
            print(motivo)
            aplicar_fallback(motivo)
            return

        payload = gerar_payload(pontos, erros)
        salvar_payload(payload)

        print(f"Total de pontos válidos: {len(pontos)}")
        print(f"Total de erros: {len(erros)}")

        for periodo, dados_periodo in payload["periodos"].items():
            print(periodo, dados_periodo["resumo"])

    except Exception as erro:
        motivo = str(erro)
        print(f"Erro geral na coleta: {motivo}")
        aplicar_fallback(motivo)


if __name__ == "__main__":
    main()
