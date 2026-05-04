import csv
import io
import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ============================================================
# COLETOR REAL DE COTAÇÕES — NORDESTE AGRO
# Fonte principal: CONAB - Preços Agropecuários
# ============================================================
# Este coletor gera dois arquivos:
#
# 1) public/cotacoes/cotacoes_regionais.json
#    - arquivo leve para a página principal de cotações
#    - mantém somente a cotação mais recente por Estado + Cidade + Produto
#    - inclui historico_30d quando disponível
#
# 2) public/cotacoes/historico_cotacoes_36m.json
#    - arquivo para nova página de histórico
#    - agrupa os registros por Estado + Cidade + Produto
#    - mantém série histórica para consulta de até 36 meses
# ============================================================


OUT_DIR = Path("public/cotacoes")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_JSON_ATUAL = OUT_DIR / "cotacoes_regionais.json"
OUT_JSON_HISTORICO = OUT_DIR / "historico_cotacoes_36m.json"

BACKUP_JSON_ATUAL = OUT_DIR / "cotacoes_regionais_ultimo_valido.json"
BACKUP_JSON_HISTORICO = OUT_DIR / "historico_cotacoes_36m_ultimo_valido.json"

FONTE = "CONAB - Preços Agropecuários"
TIPO_ATUAL = "cotacoes_regionais"
TIPO_HISTORICO = "historico_cotacoes_36m"
ATUALIZACAO = "diaria"

URLS_CONAB = [
    "https://portaldeinformacoes.conab.gov.br/downloads/arquivos/PrecosSemanalMunicipio.txt",
    "https://portaldeinformacoes.conab.gov.br/downloads/arquivos/PrecosSemanalUF.txt",
    "https://portaldeinformacoes.conab.gov.br/downloads/arquivos/PrecosMensalMunicipio.txt",
]

UFS_ALVO = {"AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE", "TO", "PA"}

PRODUTOS_ALVO = {
    "SOJA": "Soja",
    "MILHO": "Milho",
    "ALGODAO": "Algodão",
    "ALGODÃO": "Algodão",
    "ARROZ": "Arroz",
    "FEIJAO": "Feijão",
    "FEIJÃO": "Feijão",
    "LEITE": "Leite",
    "BOI": "Carne bovina",
    "BOVINO": "Carne bovina",
    "CARNE BOVINA": "Carne bovina",
    "SORGO": "Sorgo",
    "ACUCAR": "Açúcar cristal",
    "AÇÚCAR": "Açúcar cristal",
}

MAX_TENTATIVAS_DOWNLOAD = 3
MINIMO_REGISTROS_VALIDOS = 10


def agora_brasilia():
    fuso_brasilia = timezone(timedelta(hours=-3))
    return datetime.now(fuso_brasilia)


def formatar_data_br(dt):
    return dt.strftime("%d/%m/%Y")


def normalizar(txt):
    txt = str(txt or "").strip().upper()
    trocas = {
        "Á": "A", "À": "A", "Â": "A", "Ã": "A",
        "É": "E", "Ê": "E",
        "Í": "I",
        "Ó": "O", "Ô": "O", "Õ": "O",
        "Ú": "U",
        "Ç": "C",
    }

    for a, b in trocas.items():
        txt = txt.replace(a, b)

    return txt


def baixar_texto(url):
    ultimo_erro = None

    for tentativa in range(1, MAX_TENTATIVAS_DOWNLOAD + 1):
        try:
            print(f"Baixando CONAB: {url} tentativa {tentativa}/{MAX_TENTATIVAS_DOWNLOAD}")

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "NordesteAgro-Cotacoes/1.0",
                    "Accept": "text/plain,text/csv,*/*",
                },
                method="GET",
            )

            with urllib.request.urlopen(req, timeout=120) as resp:
                bruto = resp.read()

            for encoding in ["utf-8-sig", "latin-1", "cp1252"]:
                try:
                    return bruto.decode(encoding)
                except UnicodeDecodeError:
                    pass

            return bruto.decode("utf-8", errors="replace")

        except Exception as erro:
            ultimo_erro = erro
            print(f"Erro no download: {erro}")

    raise RuntimeError(f"Não foi possível baixar {url}. Último erro: {ultimo_erro}")


def detectar_dialeto(texto):
    amostra = texto[:10000]

    try:
        return csv.Sniffer().sniff(amostra, delimiters=";\t,|")
    except Exception:
        class DialetoPadrao(csv.Dialect):
            delimiter = ";"
            quotechar = '"'
            escapechar = None
            doublequote = True
            skipinitialspace = False
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL

        return DialetoPadrao


def ler_tabela(texto):
    dialeto = detectar_dialeto(texto)
    leitor = csv.DictReader(io.StringIO(texto), dialect=dialeto)
    linhas = list(leitor)

    if not linhas:
        raise RuntimeError("Arquivo CONAB baixado, mas sem linhas tabulares.")

    print(f"Colunas detectadas: {leitor.fieldnames}")
    print(f"Linhas detectadas: {len(linhas)}")

    return linhas


def pegar_valor(row, possibilidades):
    normalizadas = {normalizar(k): k for k in row.keys()}

    for nome in possibilidades:
        nome_norm = normalizar(nome)

        if nome_norm in normalizadas:
            return row.get(normalizadas[nome_norm])

    for chave_norm, chave_original in normalizadas.items():
        for nome in possibilidades:
            nome_norm = normalizar(nome)

            if nome_norm in chave_norm or chave_norm in nome_norm:
                return row.get(chave_original)

    return ""


def extrair_uf(row):
    return str(pegar_valor(row, [
        "UF",
        "SG_UF",
        "SIGLA_UF",
        "ESTADO",
        "UNIDADE DA FEDERACAO",
        "UNIDADE DA FEDERAÇÃO",
    ]) or "").strip().upper()


def limpar_nome_cidade(cidade, uf):
    cidade = str(cidade or "").strip()

    if not cidade:
        return uf

    # Mantém o nome como vem da fonte, mas remove espaços duplicados.
    cidade = re.sub(r"\s+", " ", cidade)

    return cidade


def extrair_cidade(row, uf):
    cidade = str(pegar_valor(row, [
        "MUNICIPIO",
        "MUNICÍPIO",
        "CIDADE",
        "PRACA",
        "PRAÇA",
        "LOCALIDADE",
    ]) or "").strip()

    return limpar_nome_cidade(cidade, uf)


def extrair_produto(row):
    return str(pegar_valor(row, [
        "PRODUTO",
        "NOME PRODUTO",
        "NOME_PRODUTO",
        "PRODUTO_DESCRICAO",
        "PRODUTO DESCRICAO",
        "PRODUTO DESCRIÇÃO",
    ]) or "").strip()


def extrair_data(row):
    return str(pegar_valor(row, [
        "DATA",
        "DT_PRECO",
        "DATA PRECO",
        "DATA PREÇO",
        "DATA_COLETA",
        "DATA COLETA",
        "REFERENCIA",
        "REFERÊNCIA",
        "DATA_REFERENCIA",
        "SEMANA",
        "PERIODO",
        "PERÍODO",
    ]) or "").strip()


def extrair_unidade(row):
    return str(pegar_valor(row, [
        "UNIDADE",
        "UNIDADE MEDIDA",
        "UNIDADE_MEDIDA",
        "MEDIDA",
        "EMBALAGEM",
    ]) or "").strip()


def extrair_preco_bruto(row):
    return pegar_valor(row, [
        "PRECO",
        "PREÇO",
        "VALOR",
        "VL_PRECO",
        "PRECO_MEDIO",
        "PREÇO MÉDIO",
        "PRECO MEDIO",
        "VALOR_MEDIO",
        "VALOR MÉDIO",
        "MEDIA",
        "MÉDIA",
    ])


def converter_numero(valor):
    if valor is None:
        return None

    s = str(valor).strip()

    if not s:
        return None

    s = s.replace("R$", "").replace("r$", "").replace(" ", "")
    s = re.sub(r"[^0-9,\.\-]", "", s)

    if not s:
        return None

    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        return round(float(s), 4)
    except Exception:
        return None


def formatar_preco(valor, unidade):
    if valor is None:
        return ""

    unidade_norm = normalizar(unidade)

    if "LITRO" in unidade_norm:
        return "R$ " + f"{valor:.4f}".replace(".", ",")

    return "R$ " + f"{valor:.2f}".replace(".", ",")


def classificar_produto(nome_produto):
    nome_norm = normalizar(nome_produto)

    for chave, produto_padrao in PRODUTOS_ALVO.items():
        if normalizar(chave) in nome_norm:
            return produto_padrao

    return ""


def parse_data_iso(data_txt):
    """
    Tenta transformar datas da CONAB em uma data ISO para ordenação.
    Funciona com textos como:
    - 26-05-2025 - 30-05-2025
    - 30/05/2025
    - 2025-05-30
    - mai/2025
    """
    s = str(data_txt or "").strip()

    if not s:
        return ""

    candidatos = re.findall(r"\d{2}[-/]\d{2}[-/]\d{4}", s)

    if candidatos:
        alvo = candidatos[-1]

        for fmt in ["%d-%m-%Y", "%d/%m/%Y"]:
            try:
                return datetime.strptime(alvo, fmt).date().isoformat()
            except Exception:
                pass

    candidatos_iso = re.findall(r"\d{4}-\d{2}-\d{2}", s)

    if candidatos_iso:
        return candidatos_iso[-1]

    meses = {
        "JAN": 1, "JANEIRO": 1,
        "FEV": 2, "FEVEREIRO": 2,
        "MAR": 3, "MARCO": 3, "MARÇO": 3,
        "ABR": 4, "ABRIL": 4,
        "MAI": 5, "MAIO": 5,
        "JUN": 6, "JUNHO": 6,
        "JUL": 7, "JULHO": 7,
        "AGO": 8, "AGOSTO": 8,
        "SET": 9, "SETEMBRO": 9,
        "OUT": 10, "OUTUBRO": 10,
        "NOV": 11, "NOVEMBRO": 11,
        "DEZ": 12, "DEZEMBRO": 12,
    }

    m = re.search(r"([A-Za-zçÇ]{3,9})[/\-\s]+(\d{4})", s)

    if m:
        mes_txt = normalizar(m.group(1))
        ano = int(m.group(2))
        mes = meses.get(mes_txt)

        if mes:
            return datetime(ano, mes, 1).date().isoformat()

    return ""


def gerar_regiao_generica(uf, cidade):
    if cidade:
        return f"{cidade} / {uf}"

    return uf


def transformar_linhas(linhas, origem):
    registros = []

    for row in linhas:
        uf = extrair_uf(row)

        if uf not in UFS_ALVO:
            continue

        cidade = extrair_cidade(row, uf)
        produto_original = extrair_produto(row)
        produto = classificar_produto(produto_original)

        if not produto:
            continue

        unidade = extrair_unidade(row)
        data = extrair_data(row)
        data_iso = parse_data_iso(data)
        valor = converter_numero(extrair_preco_bruto(row))

        if valor is None:
            continue

        registro = {
            "estado": uf,
            "cidade": cidade or uf,
            "regiao": gerar_regiao_generica(uf, cidade),
            "produto": produto,
            "preco": formatar_preco(valor, unidade),
            "valor": valor,
            "unidade": unidade or "unidade informada pela fonte",
            "data": data or formatar_data_br(agora_brasilia()),
            "data_iso": data_iso,
            "fonte": "CONAB",
            "referencia": f"{FONTE} - {origem}",
            "obs": "Cotação real importada da base pública da CONAB; validar condições locais antes de negociar."
        }

        registros.append(registro)

    return registros


def deduplicar(registros):
    vistos = set()
    saida = []

    for r in registros:
        chave = (
            r.get("estado"),
            r.get("cidade"),
            r.get("produto"),
            r.get("data"),
            r.get("unidade"),
            r.get("valor"),
        )

        if chave in vistos:
            continue

        vistos.add(chave)
        saida.append(r)

    return saida


def coletar_conab():
    todos = []
    erros = []

    for url in URLS_CONAB:
        nome = url.split("/")[-1]

        try:
            texto = baixar_texto(url)
            linhas = ler_tabela(texto)
            registros = transformar_linhas(linhas, nome)

            print(f"{nome}: {len(registros)} registros filtrados")
            todos.extend(registros)

        except Exception as erro:
            print(f"Erro ao processar {nome}: {erro}")
            erros.append({"url": url, "erro": str(erro)})

    todos = deduplicar(todos)

    return todos, erros


def data_limite_meses(meses):
    hoje = agora_brasilia().date()
    dias = int(meses * 30.44)
    return hoje - timedelta(days=dias)


def filtrar_ultimos_36_meses(registros):
    limite = data_limite_meses(36)

    filtrados = []

    for r in registros:
        data_iso = r.get("data_iso")

        if not data_iso:
            filtrados.append(r)
            continue

        try:
            d = datetime.strptime(data_iso, "%Y-%m-%d").date()

            if d >= limite:
                filtrados.append(r)

        except Exception:
            filtrados.append(r)

    return filtrados


def ordenar_por_data(registros):
    def chave(r):
        data_iso = r.get("data_iso") or "0000-00-00"
        return data_iso

    return sorted(registros, key=chave)


def agrupar_historico(registros):
    grupos = {}

    for r in registros:
        chave = (
            r.get("estado"),
            r.get("cidade"),
            r.get("produto"),
            r.get("unidade"),
        )

        grupos.setdefault(chave, []).append(r)

    dados_historico = []

    for (estado, cidade, produto, unidade), itens in grupos.items():
        itens_ordenados = ordenar_por_data(itens)

        historico = []

        for item in itens_ordenados:
            historico.append({
                "data": item.get("data"),
                "data_iso": item.get("data_iso"),
                "valor": item.get("valor"),
                "preco": item.get("preco"),
                "fonte": item.get("fonte"),
                "referencia": item.get("referencia"),
            })

        if not historico:
            continue

        ultimo = itens_ordenados[-1]

        dados_historico.append({
            "estado": estado,
            "cidade": cidade,
            "regiao": ultimo.get("regiao"),
            "produto": produto,
            "unidade": unidade,
            "fonte": ultimo.get("fonte"),
            "referencia": ultimo.get("referencia"),
            "ultimo_preco": ultimo.get("preco"),
            "ultimo_valor": ultimo.get("valor"),
            "ultima_data": ultimo.get("data"),
            "ultima_data_iso": ultimo.get("data_iso"),
            "total_pontos_historicos": len(historico),
            "historico": historico,
        })

    dados_historico.sort(key=lambda x: (
        str(x.get("estado")),
        str(x.get("cidade")),
        str(x.get("produto")),
    ))

    return dados_historico


def obter_historico_30d(historico):
    limite = data_limite_meses(1)
    saida = []

    for h in historico:
        data_iso = h.get("data_iso")

        if not data_iso:
            continue

        try:
            d = datetime.strptime(data_iso, "%Y-%m-%d").date()

            if d >= limite:
                saida.append({
                    "data": h.get("data"),
                    "data_iso": h.get("data_iso"),
                    "valor": h.get("valor"),
                    "preco": h.get("preco"),
                })

        except Exception:
            continue

    if len(saida) >= 2:
        return saida

    return historico[-5:] if len(historico) >= 2 else historico


def gerar_cotacoes_atuais(dados_historico):
    atuais = []

    for grupo in dados_historico:
        historico = grupo.get("historico", [])

        if not historico:
            continue

        ultimo = historico[-1]

        atual = {
            "estado": grupo.get("estado"),
            "cidade": grupo.get("cidade"),
            "regiao": grupo.get("regiao"),
            "produto": grupo.get("produto"),
            "preco": ultimo.get("preco"),
            "valor": ultimo.get("valor"),
            "unidade": grupo.get("unidade"),
            "data": ultimo.get("data"),
            "data_iso": ultimo.get("data_iso"),
            "fonte": grupo.get("fonte"),
            "referencia": grupo.get("referencia"),
            "obs": "Cotação mais recente importada da base pública da CONAB; validar condições locais antes de negociar.",
            "historico_30d": obter_historico_30d(historico),
        }

        atuais.append(atual)

    atuais.sort(key=lambda x: (
        str(x.get("estado")),
        str(x.get("cidade")),
        str(x.get("produto")),
    ))

    return atuais


def carregar_backup(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    return None


def salvar_json(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def aplicar_fallback(motivo):
    print("Aplicando fallback...")
    print(f"Motivo: {motivo}")

    backup_atual = carregar_backup(BACKUP_JSON_ATUAL)
    backup_hist = carregar_backup(BACKUP_JSON_HISTORICO)

    if backup_atual:
        backup_atual["fallback_usado"] = True
        backup_atual["fallback_motivo"] = motivo
        backup_atual["fallback_em"] = agora_brasilia().isoformat()
        salvar_json(OUT_JSON_ATUAL, backup_atual)

    if backup_hist:
        backup_hist["fallback_usado"] = True
        backup_hist["fallback_motivo"] = motivo
        backup_hist["fallback_em"] = agora_brasilia().isoformat()
        salvar_json(OUT_JSON_HISTORICO, backup_hist)

    if not backup_atual and not backup_hist:
        raise RuntimeError("Coleta falhou e não existe backup válido.")


def montar_payload_atual(cotacoes_atuais, erros):
    agora = agora_brasilia()

    return {
        "ok": True,
        "fonte": FONTE,
        "tipo": TIPO_ATUAL,
        "atualizacao": ATUALIZACAO,
        "atualizado_em": agora.isoformat(),
        "ultima_sincronizacao": formatar_data_br(agora),
        "total_registros": len(cotacoes_atuais),
        "fontes_carregadas": ["CONAB"] if cotacoes_atuais else [],
        "total_erros": len(erros),
        "erros": erros[:20],
        "dados": cotacoes_atuais,
        "aviso": (
            "Cotações referenciais importadas de fonte pública. Valores podem variar conforme praça, qualidade, "
            "volume, frete, forma de pagamento e disponibilidade das fontes."
        )
    }


def montar_payload_historico(dados_historico, erros):
    agora = agora_brasilia()

    return {
        "ok": True,
        "fonte": FONTE,
        "tipo": TIPO_HISTORICO,
        "atualizacao": ATUALIZACAO,
        "periodo": "36 meses",
        "atualizado_em": agora.isoformat(),
        "ultima_sincronizacao": formatar_data_br(agora),
        "total_series": len(dados_historico),
        "fontes_carregadas": ["CONAB"] if dados_historico else [],
        "total_erros": len(erros),
        "erros": erros[:20],
        "dados": dados_historico,
        "aviso": (
            "Histórico referencial importado de fonte pública. Valores podem variar conforme praça, qualidade, "
            "volume, frete, forma de pagamento e disponibilidade das fontes."
        )
    }


def main():
    print("Iniciando coletor real de cotações CONAB...")

    try:
        registros, erros = coletar_conab()

        print(f"Total bruto filtrado: {len(registros)}")
        print(f"Total de erros: {len(erros)}")

        if len(registros) < MINIMO_REGISTROS_VALIDOS:
            raise RuntimeError(
                f"Poucos registros válidos retornados da CONAB: {len(registros)}."
            )

        registros_36m = filtrar_ultimos_36_meses(registros)

        print(f"Registros dentro de 36 meses: {len(registros_36m)}")

        dados_historico = agrupar_historico(registros_36m)
        cotacoes_atuais = gerar_cotacoes_atuais(dados_historico)

        print(f"Séries históricas geradas: {len(dados_historico)}")
        print(f"Cotações atuais geradas: {len(cotacoes_atuais)}")

        payload_atual = montar_payload_atual(cotacoes_atuais, erros)
        payload_historico = montar_payload_historico(dados_historico, erros)

        salvar_json(OUT_JSON_ATUAL, payload_atual)
        salvar_json(BACKUP_JSON_ATUAL, payload_atual)

        salvar_json(OUT_JSON_HISTORICO, payload_historico)
        salvar_json(BACKUP_JSON_HISTORICO, payload_historico)

        print(f"Arquivo principal gerado: {OUT_JSON_ATUAL}")
        print(f"Arquivo histórico gerado: {OUT_JSON_HISTORICO}")

    except Exception as erro:
        print(f"Erro ao gerar cotações: {erro}")
        aplicar_fallback(str(erro))


if __name__ == "__main__":
    main()
