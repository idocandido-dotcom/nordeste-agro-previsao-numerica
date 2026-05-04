#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Nordeste Agro - Coletor de Cotações Oficiais

Este coletor gera os arquivos:

1) public/cotacoes/cotacoes_oficiais_nordeste_agro.json
2) public/cotacoes/cotacoes_regionais.json

O segundo arquivo mantém compatibilidade com o HTML atual da página Cotações.

REGRA PRINCIPAL:
- Não simular preço.
- Não preencher praça sem fonte.
- Não calcular preço local inventado.
- Só publicar item quando houver valor, data e fonte identificada.
- Se uma fonte falhar, registrar aviso no JSON.

FONTES:
1. CEPEA/ESALQ, por raspagem de tabelas públicas de indicadores.
2. CONAB, por importação de arquivos oficiais exportados/baixados e salvos em dados_conab/.
   Aceita CSV, XLSX, XLS e HTML com tabelas.

Por que CONAB entra via arquivo?
- A consulta pública da CONAB pode usar aplicações web dinâmicas e mudar endpoints.
- Para evitar dado errado, o coletor aceita somente exportações/tabelas oficiais que estejam
  no repositório ou em URLs diretas configuradas por variável de ambiente.

VARIÁVEIS DE AMBIENTE OPCIONAIS:
- CONAB_ARQUIVOS_URLS: lista de URLs diretas para CSV/XLS/XLSX/HTML, separadas por vírgula.
- SAIDA_COTACOES: caminho do JSON principal, se quiser alterar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import json
import os
import re
import sys
import unicodedata

import pandas as pd
import requests


FUSO_BR = timezone(timedelta(hours=-3))

ARQUIVO_SAIDA = Path(
    os.getenv(
        "SAIDA_COTACOES",
        "public/cotacoes/cotacoes_oficiais_nordeste_agro.json",
    )
)

ARQUIVO_COMPATIVEL_HTML = Path("public/cotacoes/cotacoes_regionais.json")

PASTA_CONAB = Path("dados_conab")

HEADERS = {
    "User-Agent": (
        "NordesteAgroBot/1.0 "
        "(coletor de dados públicos oficiais; https://nordesteagro.com)"
    )
}

UFS_NORDESTE_MATOPIBAPA = {
    "PA", "MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA", "TO"
}

COMMODITIES = {
    "soja": {
        "rotulo": "Soja",
        "termos": ["soja"],
        "unidade_padrao": "Saca 60 kg",
    },
    "milho": {
        "rotulo": "Milho",
        "termos": ["milho"],
        "unidade_padrao": "Saca 60 kg",
    },
    "algodao": {
        "rotulo": "Algodão",
        "termos": ["algodao", "algodão"],
        "unidade_padrao": "@",
    },
    "arroz": {
        "rotulo": "Arroz",
        "termos": ["arroz"],
        "unidade_padrao": "Saca",
    },
    "feijao": {
        "rotulo": "Feijão",
        "termos": ["feijao", "feijão"],
        "unidade_padrao": "Saca",
    },
    "leite": {
        "rotulo": "Leite",
        "termos": ["leite"],
        "unidade_padrao": "Litro",
    },
    "carne_bovina": {
        "rotulo": "Carne bovina",
        "termos": ["boi", "bovino", "bovina", "carne"],
        "unidade_padrao": "@",
    },
    "sorgo": {
        "rotulo": "Sorgo",
        "termos": ["sorgo"],
        "unidade_padrao": "Saca 60 kg",
    },
}


@dataclass(frozen=True)
class FonteCepea:
    commodity_chave: str
    produto: str
    url: str
    estado: str
    cidade: str
    unidade: str
    tipo_preco: str
    observacao: str


FONTES_CEPEA: List[FonteCepea] = [
    FonteCepea(
        commodity_chave="soja",
        produto="Soja",
        url="https://www.cepea.org.br/br/indicador/soja.aspx",
        estado="PR",
        cidade="Paranaguá",
        unidade="Saca 60 kg",
        tipo_preco="Indicador referencial",
        observacao="Indicador CEPEA/ESALQ de referência; não representa preço municipal do Nordeste.",
    ),
    FonteCepea(
        commodity_chave="milho",
        produto="Milho",
        url="https://www.cepea.org.br/br/indicador/milho.aspx",
        estado="SP",
        cidade="Campinas",
        unidade="Saca 60 kg",
        tipo_preco="Indicador referencial",
        observacao="Indicador CEPEA/ESALQ de referência; não representa preço municipal do Nordeste.",
    ),
    FonteCepea(
        commodity_chave="algodao",
        produto="Algodão",
        url="https://www.cepea.org.br/br/indicador/algodao.aspx",
        estado="SP",
        cidade="Indicador CEPEA/ESALQ",
        unidade="Centavos R$/libra-peso",
        tipo_preco="Indicador referencial",
        observacao="Indicador do algodão em pluma CEPEA/ESALQ.",
    ),
    FonteCepea(
        commodity_chave="arroz",
        produto="Arroz",
        url="https://www.cepea.org.br/br/indicador/arroz.aspx",
        estado="RS",
        cidade="Indicador CEPEA/IRGA-RS",
        unidade="Saca",
        tipo_preco="Indicador referencial",
        observacao="Indicador CEPEA/IRGA-RS.",
    ),
    FonteCepea(
        commodity_chave="feijao",
        produto="Feijão",
        url="https://www.cepea.org.br/br/indicador/feijao.aspx",
        estado="BR",
        cidade="Praças CEPEA",
        unidade="Saca",
        tipo_preco="Indicador referencial",
        observacao="Indicador CEPEA/CNA; pode aparecer agregado conforme disponibilidade da fonte.",
    ),
    FonteCepea(
        commodity_chave="leite",
        produto="Leite",
        url="https://www.cepea.org.br/br/indicador/leite.aspx",
        estado="BR",
        cidade="Média Brasil CEPEA",
        unidade="Litro",
        tipo_preco="Indicador referencial",
        observacao="Indicador CEPEA do leite; pode ter atualização mensal conforme metodologia da fonte.",
    ),
    FonteCepea(
        commodity_chave="carne_bovina",
        produto="Carne bovina",
        url="https://www.cepea.org.br/br/indicador/boi-gordo.aspx",
        estado="SP",
        cidade="Boi Gordo - Estado de São Paulo",
        unidade="@",
        tipo_preco="Indicador referencial",
        observacao="Indicador do boi gordo CEPEA/ESALQ.",
    ),
]


def agora_br() -> datetime:
    return datetime.now(FUSO_BR)


def agora_br_texto() -> str:
    return agora_br().strftime("%d/%m/%Y %H:%M")


def normalizar_txt(valor: Any) -> str:
    texto = str(valor or "").strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")
    texto = re.sub(r"\s+", " ", texto)
    return texto.lower().strip()


def apenas_texto(valor: Any) -> str:
    return str(valor or "").replace("\xa0", " ").strip()


def parse_numero_br(valor: Any) -> Optional[float]:
    if valor is None:
        return None

    texto = apenas_texto(valor)

    if not texto or texto.lower() in {"nan", "-", "—", "null", "none"}:
        return None

    texto = texto.replace("R$", "").replace("US$", "").replace("%", "").strip()
    texto = re.sub(r"[^0-9,.\-]", "", texto)

    if not texto:
        return None

    # Padrão brasileiro 1.234,56
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return None


def parse_data(valor: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Retorna (data_br, data_iso).
    Aceita datas como 04/05/2026, 2026-05-04, 05/2026.
    """
    texto = apenas_texto(valor)

    if not texto:
        return None, None

    # dd/mm/yyyy
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", texto)
    if m:
        dia, mes, ano = map(int, m.groups())
        try:
            d = datetime(ano, mes, dia, tzinfo=FUSO_BR).date()
            return d.strftime("%d/%m/%Y"), d.isoformat()
        except ValueError:
            pass

    # yyyy-mm-dd
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", texto)
    if m:
        ano, mes, dia = map(int, m.groups())
        try:
            d = datetime(ano, mes, dia, tzinfo=FUSO_BR).date()
            return d.strftime("%d/%m/%Y"), d.isoformat()
        except ValueError:
            pass

    # mm/yyyy ou mês/ano
    m = re.search(r"(\d{1,2})[/-](\d{4})", texto)
    if m:
        mes, ano = map(int, m.groups())
        try:
            d = datetime(ano, mes, 1, tzinfo=FUSO_BR).date()
            return d.strftime("%m/%Y"), d.isoformat()
        except ValueError:
            pass

    return texto, None


def commodity_por_produto(produto: Any) -> Optional[str]:
    p = normalizar_txt(produto)

    if not p:
        return None

    for chave, cfg in COMMODITIES.items():
        if any(normalizar_txt(t) in p for t in cfg["termos"]):
            return chave

    return None


def extrair_produto_unidade(texto_produto: Any) -> Tuple[str, str]:
    """
    Exemplo CONAB: SOJA (60KG), MILHO (60KG), BOI GORDO (15KG)
    """
    bruto = apenas_texto(texto_produto)
    unidade = ""

    m = re.search(r"\(([^)]+)\)", bruto)
    if m:
        unidade = m.group(1).strip()
        produto = re.sub(r"\([^)]+\)", "", bruto).strip()
    else:
        produto = bruto

    produto = re.sub(r"\s+", " ", produto).strip()

    return produto.title(), unidade


def unidade_amigavel(unidade: str, commodity_chave: Optional[str]) -> str:
    u = normalizar_txt(unidade)

    if "60" in u and ("kg" in u or "quilo" in u):
        return "Saca 60 kg"

    if "saca" in u or u == "sc":
        return "Saca"

    if "litro" in u or u == "l":
        return "Litro"

    if "arroba" in u or "@" in u or "15kg" in u or "15 kg" in u:
        return "@"

    if "kg" in u:
        return "Kg"

    if "ton" in u:
        return "Tonelada"

    if commodity_chave and commodity_chave in COMMODITIES:
        return COMMODITIES[commodity_chave]["unidade_padrao"]

    return unidade or "Unidade"


def formatar_moeda(valor: Optional[float], unidade: str = "") -> str:
    if valor is None:
        return "--"

    if normalizar_txt(unidade) == "litro":
        return "R$ " + f"{valor:.4f}".replace(".", ",")

    return "R$ " + f"{valor:.2f}".replace(".", ",")


def download(url: str) -> bytes:
    resp = requests.get(url, headers=HEADERS, timeout=50)
    resp.raise_for_status()
    return resp.content


def ler_tabelas_de_bytes(conteudo: bytes, origem: str) -> List[pd.DataFrame]:
    nome = origem.lower()

    if nome.endswith(".csv"):
        texto = conteudo.decode("utf-8-sig", errors="replace")

        for sep in [";", ",", "\t"]:
            try:
                df = pd.read_csv(StringIO(texto), sep=sep)
                if df.shape[1] > 1:
                    return [df]
            except Exception:
                continue

        return []

    if nome.endswith(".xlsx") or nome.endswith(".xls"):
        try:
            planilhas = pd.read_excel(BytesIO(conteudo), sheet_name=None)
            return [df for df in planilhas.values() if not df.empty]
        except Exception:
            return []

    try:
        html = conteudo.decode("utf-8", errors="replace")
        return pd.read_html(StringIO(html))
    except Exception:
        return []


def ler_tabelas_arquivo(path: Path) -> List[pd.DataFrame]:
    return ler_tabelas_de_bytes(path.read_bytes(), str(path))


def limpar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join(str(x) for x in col if str(x).lower() != "nan").strip()
            for col in df.columns
        ]
    else:
        df.columns = [str(c).strip() for c in df.columns]

    df = df.dropna(how="all")
    return df


def encontrar_coluna(df: pd.DataFrame, termos: Iterable[str]) -> Optional[str]:
    termos_n = [normalizar_txt(t) for t in termos]

    for col in df.columns:
        c = normalizar_txt(col)
        if any(t in c for t in termos_n):
            return col

    return None


def normalizar_item(
    *,
    produto: str,
    commodity_chave: Optional[str],
    estado: str,
    cidade: str,
    valor: Optional[float],
    unidade: str,
    data: str,
    data_iso: Optional[str],
    fonte: str,
    url_fonte: str,
    tipo_preco: str,
    nivel_comercializacao: str = "",
    observacao: str = "",
    historico_30d: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    if valor is None:
        return None

    commodity_chave = commodity_chave or commodity_por_produto(produto)

    if not commodity_chave:
        return None

    estado = apenas_texto(estado).upper() or "BR"
    cidade = apenas_texto(cidade) or "Média/Indicador"

    unidade = unidade_amigavel(unidade, commodity_chave)

    item = {
        "produto": COMMODITIES.get(commodity_chave, {}).get("rotulo", produto),
        "commodity_chave": commodity_chave,
        "estado": estado,
        "cidade": cidade,
        "valor": round(float(valor), 4),
        "preco": formatar_moeda(float(valor), unidade),
        "unidade": unidade,
        "data": data or "",
        "data_iso": data_iso,
        "fonte": fonte,
        "url_fonte": url_fonte,
        "tipo_preco": tipo_preco,
        "nivel_comercializacao": nivel_comercializacao,
        "status": "oficial",
        "observacao": observacao,
    }

    if historico_30d:
        item["historico_30d"] = historico_30d

    return item


def coletar_cepea() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    itens: List[Dict[str, Any]] = []
    avisos: List[Dict[str, Any]] = []

    for fonte in FONTES_CEPEA:
        try:
            conteudo = download(fonte.url)
            tabelas = ler_tabelas_de_bytes(conteudo, fonte.url)

            if not tabelas:
                raise RuntimeError("Nenhuma tabela encontrada na página do indicador.")

            serie = extrair_serie_cepea(tabelas)

            if not serie:
                raise RuntimeError("Tabela encontrada, mas sem série válida de preço/data.")

            atual = serie[-1]

            item = normalizar_item(
                produto=fonte.produto,
                commodity_chave=fonte.commodity_chave,
                estado=fonte.estado,
                cidade=fonte.cidade,
                valor=atual["valor"],
                unidade=fonte.unidade,
                data=atual["data"],
                data_iso=atual.get("data_iso"),
                fonte="CEPEA/ESALQ",
                url_fonte=fonte.url,
                tipo_preco=fonte.tipo_preco,
                nivel_comercializacao="Indicador",
                observacao=fonte.observacao,
                historico_30d=serie[-30:],
            )

            if item:
                itens.append(item)
                print(f"CEPEA OK: {fonte.produto} - {item['preco']}")
            else:
                raise RuntimeError("Registro normalizado ficou inválido.")

        except Exception as exc:
            aviso = {
                "fonte": "CEPEA/ESALQ",
                "produto": fonte.produto,
                "commodity_chave": fonte.commodity_chave,
                "url_fonte": fonte.url,
                "status": "erro",
                "mensagem": str(exc),
            }
            avisos.append(aviso)
            print(f"CEPEA ERRO: {fonte.produto} - {exc}", file=sys.stderr)

    return itens, avisos


def extrair_serie_cepea(tabelas: List[pd.DataFrame]) -> List[Dict[str, Any]]:
    """
    Procura uma tabela com coluna de data e preço.
    Retorna ordem crescente por data, adequada para gráfico.
    """
    for df_raw in tabelas:
        df = limpar_colunas(df_raw)

        if df.empty:
            continue

        col_data = encontrar_coluna(df, ["data", "dt", "dia"])

        if not col_data and len(df.columns) >= 2:
            col_data = df.columns[0]

        if not col_data:
            continue

        candidatos = []

        for col in df.columns:
            if col == col_data:
                continue

            nome = normalizar_txt(col)

            if any(t in nome for t in ["var", "%", "us$", "dolar", "dólar"]):
                continue

            n_validos = df[col].apply(parse_numero_br).notna().sum()

            if n_validos > 0:
                candidatos.append((col, n_validos))

        if not candidatos:
            continue

        candidatos.sort(key=lambda x: x[1], reverse=True)
        col_preco = candidatos[0][0]

        serie = []

        for _, row in df.iterrows():
            data_br, data_iso = parse_data(row.get(col_data))
            valor = parse_numero_br(row.get(col_preco))

            if not data_br or valor is None:
                continue

            serie.append({
                "data": data_br,
                "data_iso": data_iso,
                "valor": round(float(valor), 4),
            })

        unicos = {}

        for p in serie:
            chave = p.get("data_iso") or p["data"]
            unicos[chave] = p

        serie = list(unicos.values())
        serie.sort(key=lambda x: x.get("data_iso") or x.get("data") or "")

        if serie:
            return serie[-30:]

    return []


def iter_fontes_conab() -> List[Tuple[str, bytes]]:
    fontes: List[Tuple[str, bytes]] = []

    if PASTA_CONAB.exists():
        for path in sorted(PASTA_CONAB.glob("*")):
            if path.is_file() and path.suffix.lower() in {".csv", ".xlsx", ".xls", ".html", ".htm"}:
                fontes.append((str(path), path.read_bytes()))

    urls = [
        u.strip()
        for u in os.getenv("CONAB_ARQUIVOS_URLS", "").split(",")
        if u.strip()
    ]

    for url in urls:
        try:
            fontes.append((url, download(url)))
        except Exception as exc:
            print(f"CONAB URL ERRO: {url} - {exc}", file=sys.stderr)

    return fontes


def coletar_conab_importado() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    itens: List[Dict[str, Any]] = []
    avisos: List[Dict[str, Any]] = []

    fontes = iter_fontes_conab()

    if not fontes:
        avisos.append({
            "fonte": "CONAB",
            "status": "sem_arquivo",
            "mensagem": (
                "Nenhum arquivo oficial da CONAB foi encontrado em dados_conab/ "
                "e nenhuma URL direta foi informada em CONAB_ARQUIVOS_URLS."
            ),
        })
        return itens, avisos

    for origem, conteudo in fontes:
        try:
            tabelas = ler_tabelas_de_bytes(conteudo, origem)

            if not tabelas:
                raise RuntimeError("Nenhuma tabela reconhecida no arquivo/fonte.")

            total_origem = 0

            for tabela in tabelas:
                for item in normalizar_tabela_conab(tabela, origem):
                    itens.append(item)
                    total_origem += 1

            if total_origem == 0:
                raise RuntimeError("Tabela lida, mas nenhum item compatível com as commodities do projeto.")

            print(f"CONAB OK: {origem} - {total_origem} registros")

        except Exception as exc:
            avisos.append({
                "fonte": "CONAB",
                "origem": origem,
                "status": "erro",
                "mensagem": str(exc),
            })
            print(f"CONAB ERRO: {origem} - {exc}", file=sys.stderr)

    return itens, avisos


def normalizar_tabela_conab(df_raw: pd.DataFrame, origem: str) -> List[Dict[str, Any]]:
    df = limpar_colunas(df_raw)

    if df.empty:
        return []

    col_produto = encontrar_coluna(df, ["produto", "produto/unidade", "produto unidade"])
    col_nivel = encontrar_coluna(df, ["nivel", "nível", "comercializacao", "comercialização"])
    col_uf = encontrar_coluna(df, ["uf", "u.f", "estado"])
    col_cidade = encontrar_coluna(df, ["municipio", "município", "cidade", "praca", "praça", "localidade"])
    col_data = encontrar_coluna(df, ["data", "mes/ano", "mês/ano", "semana", "periodo", "período"])
    col_preco = encontrar_coluna(df, ["preco medio", "preço médio", "preco", "preço", "valor"])

    if not col_produto or not col_preco:
        return []

    registros: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        produto_bruto = row.get(col_produto)
        produto, unidade_extraida = extrair_produto_unidade(produto_bruto)
        commodity = commodity_por_produto(produto)

        if not commodity:
            continue

        valor = parse_numero_br(row.get(col_preco))

        if valor is None:
            continue

        estado = apenas_texto(row.get(col_uf)) if col_uf else "BR"
        estado = estado.upper()

        # Mantém apenas Nordeste + Tocantins + Pará.
        # Para publicar Brasil inteiro, comente este bloco.
        if estado and estado != "BR" and estado not in UFS_NORDESTE_MATOPIBAPA:
            continue

        cidade = apenas_texto(row.get(col_cidade)) if col_cidade else ""

        if not cidade:
            cidade = "Média estadual" if estado and estado != "BR" else "Média Brasil"

        data_br = ""
        data_iso = None

        if col_data:
            data_br, data_iso = parse_data(row.get(col_data))

        if not data_br:
            data_br = agora_br().strftime("%d/%m/%Y")

        nivel = apenas_texto(row.get(col_nivel)) if col_nivel else "Preço de mercado"

        item = normalizar_item(
            produto=produto,
            commodity_chave=commodity,
            estado=estado or "BR",
            cidade=cidade,
            valor=valor,
            unidade=unidade_extraida,
            data=data_br,
            data_iso=data_iso,
            fonte="CONAB",
            url_fonte=origem,
            tipo_preco="Preço oficial de mercado",
            nivel_comercializacao=nivel,
            observacao="Registro importado de arquivo/tabela oficial da CONAB.",
        )

        if item:
            registros.append(item)

    return deduplicar_itens(registros)


def deduplicar_itens(itens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}

    for item in itens:
        chave = "|".join([
            item.get("fonte", ""),
            item.get("commodity_chave", ""),
            item.get("estado", ""),
            normalizar_txt(item.get("cidade", "")),
            item.get("data", ""),
            str(item.get("valor", "")),
        ])

        out[chave] = item

    return list(out.values())


def gerar_payload(itens: List[Dict[str, Any]], avisos: List[Dict[str, Any]]) -> Dict[str, Any]:
    itens = deduplicar_itens(itens)

    itens.sort(key=lambda x: (
        x.get("commodity_chave", ""),
        x.get("estado", ""),
        x.get("cidade", ""),
        x.get("fonte", ""),
    ))

    payload = {
        "ok": bool(itens),
        "projeto": "Nordeste Agro",
        "tipo": "cotacoes_oficiais",
        "fonte_principal": "CONAB",
        "fontes_complementares": ["CEPEA/ESALQ", "B3"],
        "ultima_sincronizacao": agora_br_texto(),
        "gerado_em": agora_br().isoformat(timespec="seconds"),
        "frequencia_atualizacao": "diaria_em_dias_uteis",
        "modo": "github_actions_json_publico",
        "regra_dados": (
            "Somente valores coletados/importados de fontes oficiais são publicados. "
            "O sistema não simula preços e não cria cotação para praça sem dado oficial."
        ),
        "dados": itens,
        "avisos": avisos + gerar_avisos_commodities_sem_dado(itens),
        "fontes": [
            {
                "nome": "CONAB",
                "uso": "Preços agropecuários oficiais por produto, UF e localidade quando importados de arquivo/export oficial.",
                "status": "ativo_por_importacao_ou_url_direta",
            },
            {
                "nome": "CEPEA/ESALQ",
                "uso": "Indicadores referenciais oficiais de mercado por produto.",
                "status": "ativo",
            },
            {
                "nome": "B3",
                "uso": "Mercado futuro e referência complementar quando integrada futuramente.",
                "status": "preparado_para_integracao_futura",
            },
        ],
    }

    return payload


def gerar_avisos_commodities_sem_dado(itens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    com_dado = {i.get("commodity_chave") for i in itens}
    avisos = []

    for chave, cfg in COMMODITIES.items():
        if chave not in com_dado:
            avisos.append({
                "produto": cfg["rotulo"],
                "commodity_chave": chave,
                "status": "sem_dado_oficial_publicado",
                "mensagem": (
                    "Nenhum valor oficial foi coletado/importado para esta commodity nesta execução. "
                    "A página deve mostrar indisponibilidade, não valor simulado."
                ),
            })

    return avisos


def salvar_json(payload: Dict[str, Any]) -> None:
    ARQUIVO_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO_COMPATIVEL_HTML.parent.mkdir(parents=True, exist_ok=True)

    texto_json = json.dumps(payload, ensure_ascii=False, indent=2)

    ARQUIVO_SAIDA.write_text(texto_json, encoding="utf-8")
    ARQUIVO_COMPATIVEL_HTML.write_text(texto_json, encoding="utf-8")

    print(f"Arquivo principal gerado: {ARQUIVO_SAIDA}")
    print(f"Arquivo compatível com HTML gerado: {ARQUIVO_COMPATIVEL_HTML}")


def main() -> int:
    todos_itens: List[Dict[str, Any]] = []
    todos_avisos: List[Dict[str, Any]] = []

    itens_conab, avisos_conab = coletar_conab_importado()
    todos_itens.extend(itens_conab)
    todos_avisos.extend(avisos_conab)

    itens_cepea, avisos_cepea = coletar_cepea()
    todos_itens.extend(itens_cepea)
    todos_avisos.extend(avisos_cepea)

    payload = gerar_payload(todos_itens, todos_avisos)
    salvar_json(payload)

    print(f"Total de registros oficiais publicados: {len(payload['dados'])}")
    print(f"Total de avisos: {len(payload['avisos'])}")

    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
