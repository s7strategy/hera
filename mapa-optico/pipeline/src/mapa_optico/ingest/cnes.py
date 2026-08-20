"""CNES: quantos oftalmologistas cada municipio tem, de verdade.

Este e o modulo de maior risco do projeto (Fase 0 do briefing). Tres caminhos,
tentados nesta ordem, e o pipeline registra qual foi usado:

  1. `pysus`  — baixa a base PF do DATASUS e descompacta o .DBC (DBF comprimido
     com algoritmo proprietario; `dbfread` puro NAO abre).
  2. CSV manual — o arquivo baixado a mao em
     https://cnes.datasus.gov.br/pages/profissionais/extracao.jsp
     (selecionar a UF e NAO selecionar municipio), colocado em data/manual/.
  3. Base dos Dados — dataset ja tratado, via BigQuery (exige credencial GCP).

Armadilhas tratadas aqui, todas citadas no briefing:
  - codigo de municipio de 6 digitos do CNES vira 7 (transform.normalize)
  - um medico com varios vinculos conta UMA vez por municipio
  - carga horaria ambulatorial vira "oftalmologista equivalente" (40h = 1,0)
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from ..logs import aviso, etapa, log
from ..settings import DATA_DIR
from ..transform.normalize import deduplicar_profissionais, para_codigo7
from .fontes import carregar

FONTE = "cnes"
MANUAL_DIR = DATA_DIR / "manual"
HORAS_EQUIVALENTE = 40.0

# Nomes de coluna que ja vimos em bases PF do CNES e nas extracoes CSV do portal.
# Resolvemos por candidato em vez de fixar um nome: o layout muda entre
# competencias e entre o .DBC e o CSV do portal.
_CANDIDATOS = {
    "municipio": ["codufmun", "co_municipio_gestor", "codmun", "municipio", "cd_municipio", "ibge"],
    "cbo": ["cbo", "cbo02", "codcbo", "co_cbo", "cbo_unico", "descricao_cbo"],
    "cpf": ["cpf_prof", "cpf", "co_cpf", "cns_prof", "cns", "co_profissional_sus"],
    "horas_amb": ["hora_amb", "horaamb", "qt_carga_hor_ambulatorial", "carga_horaria_ambulatorial"],
    "horas_hosp": ["horahosp", "hora_hosp", "qt_carga_hor_hospitalar"],
    "horas_outras": ["horaoutr", "hora_outr", "qt_carga_horaria_outros"],
    "nome": ["nomeprof", "nome", "no_profissional"],
}


class CnesIndisponivel(RuntimeError):
    """Nenhum dos caminhos do CNES funcionou. Parar e reportar — nao improvisar."""


def _resolver(colunas: Iterable[str], papel: str) -> str | None:
    normalizadas = {str(c).strip().lower(): str(c) for c in colunas}
    for cand in _CANDIDATOS[papel]:
        if cand in normalizadas:
            return normalizadas[cand]
    return None


def _preparar(df: pd.DataFrame, cbos: list[str], contador: Any) -> pd.DataFrame:
    """Filtra por CBO de oftalmologista e devolve vinculos normalizados."""
    col_mun = _resolver(df.columns, "municipio")
    col_cbo = _resolver(df.columns, "cbo")
    col_cpf = _resolver(df.columns, "cpf")
    if not (col_mun and col_cbo and col_cpf):
        raise CnesIndisponivel(
            "layout do CNES nao reconhecido. Colunas recebidas: "
            f"{list(df.columns)[:25]}. Ajuste _CANDIDATOS em ingest/cnes.py."
        )

    trabalho = df.copy()
    trabalho["_cbo"] = trabalho[col_cbo].astype(str).str.strip().str.replace(r"\D", "", regex=True)
    alvo = {str(c).strip() for c in cbos}
    antes = len(trabalho)
    trabalho = trabalho[trabalho["_cbo"].isin(alvo)]
    contador.descartar("CBO diferente de oftalmologista", antes - len(trabalho))

    trabalho["codigo_ibge"] = trabalho[col_mun].map(para_codigo7)
    sem_codigo = int(trabalho["codigo_ibge"].isna().sum())
    if sem_codigo:
        contador.descartar("codigo de municipio invalido", sem_codigo)
        trabalho = trabalho.dropna(subset=["codigo_ibge"])

    trabalho["id_profissional"] = trabalho[col_cpf].astype(str).str.strip()

    col_amb = _resolver(df.columns, "horas_amb")
    if col_amb:
        trabalho["horas_ambulatorial"] = pd.to_numeric(trabalho[col_amb], errors="coerce").fillna(0.0)
    else:
        aviso("CNES sem coluna de carga horaria ambulatorial; oftalmo equivalente ficara nulo")
        trabalho["horas_ambulatorial"] = pd.NA
    return trabalho[["codigo_ibge", "id_profissional", "horas_ambulatorial"]]


def agregar_por_municipio(vinculos: pd.DataFrame, competencia: str) -> pd.DataFrame:
    """De vinculos para uma linha por municipio: profissionais unicos + horas."""
    tem_horas = vinculos["horas_ambulatorial"].notna().any()
    dedup = deduplicar_profissionais(
        vinculos,
        coluna_horas="horas_ambulatorial" if tem_horas else None,
    )
    if dedup.empty:
        return pd.DataFrame(
            columns=[
                "codigo_ibge",
                "qtd_oftalmologistas",
                "horas_semanais_total",
                "oftalmo_equivalente",
                "competencia_cnes",
            ]
        )
    if tem_horas:
        agg = dedup.groupby("codigo_ibge").agg(
            qtd_oftalmologistas=("id_profissional", "nunique"),
            horas_semanais_total=("horas_ambulatorial", "sum"),
        )
    else:
        agg = dedup.groupby("codigo_ibge").agg(qtd_oftalmologistas=("id_profissional", "nunique"))
        agg["horas_semanais_total"] = pd.NA
    agg = agg.reset_index()
    agg["oftalmo_equivalente"] = (
        (agg["horas_semanais_total"] / HORAS_EQUIVALENTE).round(2) if tem_horas else pd.NA
    )
    agg["competencia_cnes"] = competencia
    return agg


def _via_pysus(uf: str, competencia: str | None, refresh: bool) -> tuple[pd.DataFrame, str, str]:
    try:
        from pysus.online_data import CNES  # type: ignore
    except ImportError as exc:  # pragma: no cover - depende do extra instalado
        raise CnesIndisponivel(
            "pysus nao instalado. Rode `uv sync --extra cnes` (ou `pip install pysus`)."
        ) from exc

    ano, mes = _competencia_partes(competencia)
    log("baixando CNES via pysus", uf=uf, ano=ano, mes=mes)
    try:
        arquivos = CNES.download(["PF"], [uf], [ano], [mes])  # type: ignore[attr-defined]
        df = arquivos.to_dataframe() if hasattr(arquivos, "to_dataframe") else pd.DataFrame(arquivos)
    except Exception as exc:
        raise CnesIndisponivel(f"pysus falhou para {uf} {ano}-{mes:02d}: {exc}") from exc
    if df is None or len(df) == 0:
        raise CnesIndisponivel(f"pysus devolveu base vazia para {uf} {ano}-{mes:02d}")
    return df, f"{ano}{mes:02d}", "pysus"


def _competencia_partes(competencia: str | None) -> tuple[int, int]:
    if competencia:
        return int(competencia[:4]), int(competencia[4:6])
    # Sem competencia explicita: usa o mes retrasado, que ja costuma estar publicado.
    hoje = pd.Timestamp.utcnow()
    alvo = (hoje - pd.DateOffset(months=2)).to_pydatetime()
    return alvo.year, alvo.month


def _via_csv_manual(uf: str, competencia: str | None) -> tuple[pd.DataFrame, str, str]:
    """Le qualquer CSV colocado em data/manual/ cujo nome contenha a UF."""
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    candidatos = sorted(
        p for p in MANUAL_DIR.glob("*.csv") if uf.lower() in p.name.lower() or "cnes" in p.name.lower()
    )
    if not candidatos:
        raise CnesIndisponivel(
            f"nenhum CSV manual em {MANUAL_DIR}. Baixe a extracao de profissionais da UF em "
            "https://cnes.datasus.gov.br/pages/profissionais/extracao.jsp e salve ali."
        )
    caminho = candidatos[-1]
    for sep in (";", ","):
        for enc in ("latin-1", "utf-8"):
            try:
                df = pd.read_csv(caminho, sep=sep, encoding=enc, dtype=str, low_memory=False)
            except Exception as exc:  # noqa: BLE001 - tentativa de combinacao
                log("combinacao de leitura falhou", arquivo=caminho.name, sep=sep, enc=enc, erro=str(exc))
                continue
            if df.shape[1] > 1:
                log("CNES lido de CSV manual", arquivo=caminho.name, linhas=len(df), colunas=df.shape[1])
                return df, competencia or "manual", f"csv_manual:{caminho.name}"
    raise CnesIndisponivel(f"nao consegui parsear {caminho} (separador/encoding).")


def oftalmologistas_por_municipio(
    uf: str,
    *,
    competencia: str | None = None,
    refresh: bool = False,
    caminho_preferido: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Devolve (DataFrame por municipio, metadados de proveniencia).

    Levanta CnesIndisponivel se todos os caminhos falharem — o chamador reporta
    e para. Nunca devolvemos zero oftalmologistas por falta de dado.
    """
    cfg = carregar()["cnes"]
    cbos = [*cfg["cbo_oftalmologista"], *(cfg.get("cbo_correlatos") or [])]
    competencia = competencia or cfg.get("competencia")

    caminhos = {
        "pysus": lambda: _via_pysus(uf, competencia, refresh),
        "csv": lambda: _via_csv_manual(uf, competencia),
    }
    ordem = [caminho_preferido] if caminho_preferido else ["pysus", "csv"]
    erros: list[str] = []

    with etapa(f"ingest.cnes.{uf}") as c:
        for nome in ordem:
            if nome not in caminhos:
                erros.append(f"{nome}: caminho desconhecido")
                continue
            try:
                bruto, comp, origem = caminhos[nome]()
            except CnesIndisponivel as exc:
                aviso("caminho do CNES indisponivel", caminho=nome, erro=str(exc))
                erros.append(f"{nome}: {exc}")
                continue
            c.entrada = len(bruto)
            vinculos = _preparar(bruto, cbos, c)
            agregado = agregar_por_municipio(vinculos, comp)
            c.saida = len(agregado)
            meta = {
                "origem": origem,
                "competencia": comp,
                "cbos": cbos,
                "vinculos": len(vinculos),
                "profissionais_unicos": int(agregado["qtd_oftalmologistas"].sum()) if not agregado.empty else 0,
                "municipios_com_oftalmo": len(agregado),
            }
            log("CNES agregado", **meta)
            return agregado, meta
    raise CnesIndisponivel(
        "CNES indisponivel por todos os caminhos testados:\n  - " + "\n  - ".join(erros)
    )
