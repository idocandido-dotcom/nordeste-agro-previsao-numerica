import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ============================================================
# COLETOR DE COTAÇÕES — NORDESTE AGRO
# ============================================================
# Primeira versão:
# - cria/atualiza o JSON dinâmico usado pelo WordPress;
# - mantém a estrutura pronta para receber cotações reais;
# - atualiza a data de sincronização automaticamente;
# - mantém backup do último JSON válido.
#
# Importante:
# Esta versão ainda não coleta preços reais automaticamente.
# Ela prepara a estrutura dinâmica para a página deixar de depender
# dos dados fixos dentro do HTML.
# ============================================================


OUT_DIR = Path("public/cotacoes")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_JSON = OUT_DIR / "cotacoes_regionais.json"
BACKUP_JSON = OUT_DIR / "cotacoes_regionais_ultimo_valido.json"

FONTE = "CEPEA / CONAB / B3 / IBGE-MAPA"
TIPO = "cotacoes_regionais"
ATUALIZACAO = "diaria"


BASE_DADOS = []


def agora_brasilia():
    fuso_brasilia = timezone(timedelta(hours=-3))
    return datetime.now(fuso_brasilia)


def formatar_data_br(dt):
    return dt.strftime("%d/%m/%Y")


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


def obter_dados_base():
    existente = carregar_json_existente()

    if existente and isinstance(existente.get("dados"), list) and existente.get("dados"):
        return existente["dados"]

    return BASE_DADOS


def montar_payload():
    agora = agora_brasilia()
    dados = obter_dados_base()

    return {
        "ok": True,
        "fonte": FONTE,
        "tipo": TIPO,
        "atualizacao": ATUALIZACAO,
        "atualizado_em": agora.isoformat(),
        "ultima_sincronizacao": formatar_data_br(agora),
        "total_registros": len(dados),
        "dados": dados,
        "aviso": (
            "Cotações referenciais. Valores podem variar conforme praça, qualidade, volume, "
            "frete, forma de pagamento e disponibilidade das fontes."
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
        raise RuntimeError("Não existe JSON anterior válido para fallback.")

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
    try:
        payload = montar_payload()
        salvar_payload(payload)

        print("JSON de cotações gerado com sucesso.")
        print(f"Registros: {payload['total_registros']}")
        print(f"Última sincronização: {payload['ultima_sincronizacao']}")

    except Exception as erro:
        print(f"Erro ao gerar cotações: {erro}")
        aplicar_fallback(str(erro))


if __name__ == "__main__":
    main()
