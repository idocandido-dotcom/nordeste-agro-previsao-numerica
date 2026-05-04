import csv
import io
import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ============================================================
# COLETOR REAL DE COTAÇÕES — NORDESTE AGRO
# Fonte principal: CONAB - Preços Agropecuários
# ============================================================
# Este coletor:
# - baixa arquivo oficial de preços agropecuários da CONAB;
# - tenta ler automaticamente separador e colunas;
# - filtra Nordeste + Tocantins + Pará;
# - seleciona produtos agrícolas de interesse do Nordeste Agro;
# - gera JSON para o WordPress;
# - mantém backup do último JSON válido.
# ============================================================


OUT_DIR = Path("public/cotacoes")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_JSON = OUT_DIR / "cotacoes_regionais.json"
BACKUP_JSON = OUT_DIR / "cotacoes_regionais_ultimo_valido.json"

FONTE = "CONAB - Preços Agropecuários"
TIPO = "cotacoes_regionais"
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

    return linhas, leitor.fieldnames or []


def pegar_valor(row, possibilidades):
    normalizadas = {normalizar(k): k for k in row.keys()}

    for nome in possibilidades:
        nome_norm = normalizar(nome)
        if nome_norm in normalizadas:
            return row.get(normalizadas[nome_norm])

    # busca parcial
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


def extrair_cidade(row):
    return str(pegar_valor(row, [
        "MUNICIPIO",
        "MUNICÍPIO",
        "CIDADE",
        "PRACA",
        "PRAÇA",
        "LOCALIDADE",
    ]) or "").strip()


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
    ]) or "").strip()


def extrair_unidade(row):
    return str(pegar_valor(row, [
        "UNIDADE",
        "UNIDADE MEDIDA",
        "UNIDADE_MEDIDA",
        "MEDIDA",
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

    # Mantém apenas número, vírgula, ponto e sinal
    s = re.sub(r"[^0-9,\.\-]", "", s)

    if not s:
        return None

    # Caso brasileiro: 1.234,56
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

        cidade = extrair_cidade(row)
        produto_original = extrair_produto(row)
        produto = classificar_produto(produto_original)

        if not produto:
            continue

        unidade = extrair_unidade(row)
        data = extrair_data(row)
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


def carregar_json_existente():
    if OUT_JSON.exists():
        try:
            return json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def carregar_backup():
    if BACKUP_JSON.exists():
        return json.loads(BACKUP_JSON.read_text(encoding="utf-8"))

    if OUT_JSON.exists():
        return json.loads(OUT_JSON.read_text(encoding="utf-8"))

    return None


def coletar_conab():
    todos = []
    erros = []

    for url in URLS_CONAB:
        nome = url.split("/")[-1]

        try:
            texto = baixar_texto(url)
            linhas, _ = ler_tabela(texto)
            registros = transformar_linhas(linhas, nome)

            print(f"{nome}: {len(registros)} registros filtrados")
            todos.extend(registros)

        except Exception as erro:
            print(f"Erro ao processar {nome}: {erro}")
            erros.append({"url": url, "erro": str(erro)})

    todos = deduplicar(todos)

    return todos, erros


def montar_payload(registros, erros):
    agora = agora_brasilia()

    fontes = sorted(set(r.get("fonte", "") for r in registros if r.get("fonte")))

    return {
        "ok": True,
        "fonte": FONTE,
        "tipo": TIPO,
        "atualizacao": ATUALIZACAO,
        "atualizado_em": agora.isoformat(),
        "ultima_sincronizacao": formatar_data_br(agora),
        "total_registros": len(registros),
        "fontes_carregadas": fontes,
        "total_erros": len(erros),
        "erros": erros[:20],
        "dados": registros,
        "aviso": (
            "Cotações referenciais importadas de fonte pública. Valores podem variar conforme praça, qualidade, "
            "volume, frete, forma de pagamento e disponibilidade das fontes."
        )
    }


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
    print(f"Backup gerado: {BACKUP_JSON}")


def aplicar_fallback(motivo):
    backup = carregar_backup()

    if not backup:
        raise RuntimeError("Coleta falhou e não existe JSON anterior válido para fallback.")

    backup["ok"] = True
    backup["fallback_usado"] = True
    backup["fallback_motivo"] = motivo
    backup["fallback_em"] = agora_brasilia().isoformat()

    OUT_JSON.write_text(
        json.dumps(backup, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("Fallback aplicado com sucesso.")
    print(f"Motivo: {motivo}")


def main():
    print("Iniciando coletor real de cotações CONAB...")

    try:
        registros, erros = coletar_conab()

        print(f"Total de registros reais filtrados: {len(registros)}")
        print(f"Total de erros: {len(erros)}")

        if len(registros) < MINIMO_REGISTROS_VALIDOS:
            existente = carregar_json_existente()

            if existente and isinstance(existente.get("dados"), list) and existente.get("dados"):
                print("Poucos registros reais retornados. Mantendo dados existentes e atualizando data.")
                registros = existente["dados"]
            else:
                raise RuntimeError(
                    f"Poucos registros válidos retornados da CONAB: {len(registros)}."
                )

        payload = montar_payload(registros, erros)
        salvar_payload(payload)

        print("JSON real de cotações gerado com sucesso.")
        print(f"Registros: {payload['total_registros']}")
        print(f"Última sincronização: {payload['ultima_sincronizacao']}")

    except Exception as erro:
        print(f"Erro ao gerar cotações reais: {erro}")
        aplicar_fallback(str(erro))


if __name__ == "__main__":
    main()
