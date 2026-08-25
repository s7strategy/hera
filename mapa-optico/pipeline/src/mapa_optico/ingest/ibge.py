"""IBGE: municipios, populacao por faixa etaria, renda e malha territorial.

APIs publicas, sem chave. Tudo cacheado em disco.

Decisao importante sobre a populacao 40+: em vez de fixar os codigos das faixas
etarias da classificacao c287 (que mudam entre tabelas e censos), pedimos TODAS
as faixas e somamos as que comecam em 40 anos ou mais, lendo o rotulo. Assim uma
renumeracao no SIDRA nao devolve silenciosamente um numero errado.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from ..cache import get_or_set
from ..geo import UF_CODIGO, area_km2, centroide
from ..http import FonteIndisponivel, get_json
from ..logs import aviso, etapa, log
from ..transform.normalize import para_codigo7, uf_do_codigo
from .fontes import carregar

FONTE = "ibge"

_VALOR_AUSENTE = {"-", "..", "...", "X", "..X", None, ""}


def _filtro_n6(ufs: list[str] | None) -> str:
    """Filtro territorial do SIDRA: municipios de uma UF ou do Brasil inteiro."""
    if not ufs:
        return "n6/all"
    codigos = [str(UF_CODIGO[uf.upper()]) for uf in ufs if uf.upper() in UF_CODIGO]
    if not codigos:
        return "n6/all"
    return "n6/in n3 " + ",".join(codigos)


def _mapa_colunas(cabecalho: dict[str, str]) -> dict[str, str]:
    """Do cabecalho do SIDRA ({'D1C': 'Municipio (Codigo)'}) para {papel: chave}."""
    mapa: dict[str, str] = {}
    for chave, rotulo in cabecalho.items():
        r = rotulo.lower()
        e_codigo = "cód" in r or "(cod" in r
        if "munic" in r and e_codigo:
            mapa["codigo"] = chave
        elif "munic" in r:
            mapa.setdefault("nome", chave)
        elif r == "valor":
            mapa["valor"] = chave
        elif "idade" in r and not e_codigo:
            mapa["idade"] = chave
    return mapa


def _num(valor: Any) -> float | None:
    if valor in _VALOR_AUSENTE:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    # SIDRA as vezes devolve "1.234,56" (pt-BR) e as vezes "1234.56" (ponto decimal).
    # So tratamos o ponto como separador de milhar quando ha virgula na string.
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except (TypeError, ValueError):
        return None


def idade_inicial(rotulo: str) -> int | None:
    """Extrai o inicio da faixa etaria a partir do rotulo do SIDRA.

    'Menos de 1 ano' -> 0 | '40 a 44 anos' -> 40 | '100 anos ou mais' -> 100
    'Total' -> None (nao e faixa)
    """
    r = rotulo.strip().lower()
    if r.startswith("total") or "não" in r or "nao" in r:
        return None
    if "menos de" in r:
        return 0
    m = re.search(r"(\d+)", r)
    return int(m.group(1)) if m else None


def municipios(ufs: list[str] | None = None, *, refresh: bool = False) -> pd.DataFrame:
    """Dimensao municipio pela API de localidades: codigo, nome, UF, micro e mesorregiao."""
    cfg = carregar()["ibge"]
    url = cfg["localidades_url"]
    chave = "municipios-" + (",".join(sorted(ufs)) if ufs else "BR")

    def _buscar() -> Any:
        return get_json(FONTE, url)

    with etapa("ingest.ibge.municipios") as c:
        bruto = get_or_set(FONTE, chave, _buscar, refresh=refresh)
        c.entrada = len(bruto)
        linhas = []
        for m in bruto:
            codigo = para_codigo7(m.get("id"))
            if not codigo:
                c.descartar("codigo invalido")
                continue
            micro = (m.get("microrregiao") or {})
            meso = (micro.get("mesorregiao") or {})
            # A UF sai dos dois primeiros digitos do codigo, que e definicao da
            # tabela de territorios. O payload do IBGE as vezes vem sem o bloco
            # microrregiao/mesorregiao aninhado, e confiar nele fazia sumir 171
            # dos 295 municipios de SC — silenciosamente, no filtro de UF.
            uf = uf_do_codigo(codigo) or ((meso.get("UF") or {}).get("sigla")) or _uf_por_regiao_imediata(m)
            if ufs and (uf or "").upper() not in {u.upper() for u in ufs}:
                c.descartar("fora das UFs pedidas")
                continue
            linhas.append(
                {
                    "codigo_ibge": codigo,
                    "nome": m.get("nome"),
                    "uf": uf,
                    "microrregiao": micro.get("nome"),
                    "mesorregiao": meso.get("nome"),
                }
            )
        df = pd.DataFrame(linhas)
        c.saida = len(df)
    return df


def _uf_por_regiao_imediata(m: dict[str, Any]) -> str | None:
    imediata = m.get("regiao-imediata") or {}
    intermediaria = imediata.get("regiao-intermediaria") or {}
    return ((intermediaria.get("UF") or {}).get("sigla"))


def populacao_por_idade(ufs: list[str] | None = None, *, refresh: bool = False) -> pd.DataFrame:
    """Populacao total e populacao 40+ por municipio (Censo, via SIDRA).

    A populacao 40+ e o proxy de presbiopia — o publico que efetivamente compra
    oculos de leitura. Sem ela o modelo perde o fator de mercado enderecavel.
    """
    cfg = carregar()["ibge"]["populacao"]
    url = cfg["sidra_url"].format(
        tabela=cfg["tabela"], variavel=cfg["variavel"], periodo=cfg["periodo"], n6=_filtro_n6(ufs)
    )
    chave = f"populacao-{cfg['tabela']}-{cfg['periodo']}-" + (",".join(sorted(ufs)) if ufs else "BR")
    idade_min = int(cfg.get("idade_minima", 40))

    with etapa("ingest.ibge.populacao") as c:
        bruto = get_or_set(FONTE, chave, lambda: get_json(FONTE, url), refresh=refresh)
        if not bruto or len(bruto) < 2:
            raise FonteIndisponivel(FONTE, "SIDRA devolveu resposta vazia para populacao")
        colunas = _mapa_colunas(bruto[0])
        faltando = {"codigo", "valor", "idade"} - set(colunas)
        if faltando:
            raise FonteIndisponivel(FONTE, f"cabecalho SIDRA inesperado, faltam {faltando}: {bruto[0]}")
        c.entrada = len(bruto) - 1

        acumulado: dict[str, dict[str, float | None]] = {}
        for linha in bruto[1:]:
            codigo = para_codigo7(linha.get(colunas["codigo"]))
            if not codigo:
                c.descartar("codigo invalido")
                continue
            rotulo = str(linha.get(colunas["idade"], ""))
            valor = _num(linha.get(colunas["valor"]))
            reg = acumulado.setdefault(codigo, {"populacao_total": None, "populacao_40mais": None})
            inicio = idade_inicial(rotulo)
            if rotulo.strip().lower().startswith("total"):
                reg["populacao_total"] = valor
            elif inicio is not None and valor is not None and inicio >= idade_min:
                reg["populacao_40mais"] = (reg["populacao_40mais"] or 0) + valor

        df = pd.DataFrame(
            [{"codigo_ibge": k, **v} for k, v in acumulado.items()]
        )
        if not df.empty:
            df["populacao_total"] = df["populacao_total"].astype("Float64").astype("Int64")
            df["populacao_40mais"] = df["populacao_40mais"].astype("Float64").astype("Int64")
        c.saida = len(df)
        # SIDRA respondendo 200 com um corpo que nao vira numero nenhum e o
        # modo de falha mais perigoso: sem esta guarda o pipeline segue feliz e
        # o ranking inteiro sai nulo sem ninguem ser avisado. Uma vez ja saiu.
        uteis = int(df["populacao_total"].notna().sum()) if not df.empty else 0
        if uteis == 0:
            raise FonteIndisponivel(
                FONTE,
                f"SIDRA respondeu {len(bruto) - 1} linhas para populacao e nenhuma virou numero. "
                f"Cabecalho: {bruto[0]}. Primeira linha: {bruto[1] if len(bruto) > 1 else '—'}",
            )
        sem_40 = int(df["populacao_40mais"].isna().sum()) if not df.empty else 0
        if sem_40:
            aviso("municipios sem populacao 40+", quantidade=sem_40)
    return df


def renda(ufs: list[str] | None = None, *, refresh: bool = False) -> pd.DataFrame:
    """Renda domiciliar per capita por municipio. Falha aqui NAO derruba o pipeline.

    Tenta as candidatas do fontes.yaml em ordem. Uma tabela fixa aqui ja quebrou
    a execucao inteira: a 7113 e da PNAD continua e nao existe em nivel de
    municipio, o que so aparece como HTTP 400 no meio da ingestao.
    """
    cfg = carregar()["ibge"]["renda"]
    candidatas = cfg.get("candidatas") or [
        {"tabela": cfg.get("tabela"), "variavel": cfg.get("variavel"), "periodo": cfg.get("periodo")}
    ]
    erros: list[str] = []
    for candidata in candidatas:
        try:
            df = _renda_de(candidata, cfg, ufs, refresh=refresh)
        except FonteIndisponivel as exc:
            erros.append(f"t/{candidata.get('tabela')}: {exc}")
            aviso("candidata de renda falhou", tabela=str(candidata.get("tabela")), erro=str(exc)[:160])
            continue
        log(
            "renda obtida",
            tabela=str(candidata.get("tabela")),
            rotulo=str(candidata.get("rotulo", "")),
            municipios=len(df),
        )
        return df
    raise FonteIndisponivel(FONTE, "nenhuma tabela de renda respondeu:\n  - " + "\n  - ".join(erros))


def _renda_de(
    candidata: dict[str, Any], cfg: dict[str, Any], ufs: list[str] | None, *, refresh: bool
) -> pd.DataFrame:
    url = cfg["sidra_url"].format(
        tabela=candidata["tabela"],
        variavel=candidata["variavel"],
        periodo=candidata["periodo"],
        n6=_filtro_n6(ufs),
    )
    chave = f"renda-{candidata['tabela']}-{candidata['periodo']}-" + (
        ",".join(sorted(ufs)) if ufs else "BR"
    )

    with etapa("ingest.ibge.renda") as c:
        bruto = get_or_set(FONTE, chave, lambda: get_json(FONTE, url), refresh=refresh)
        if not bruto or len(bruto) < 2:
            raise FonteIndisponivel(FONTE, "SIDRA devolveu resposta vazia para renda")
        colunas = _mapa_colunas(bruto[0])
        if "codigo" not in colunas or "valor" not in colunas:
            raise FonteIndisponivel(FONTE, f"cabecalho SIDRA inesperado para renda: {bruto[0]}")
        c.entrada = len(bruto) - 1
        linhas = []
        for linha in bruto[1:]:
            codigo = para_codigo7(linha.get(colunas["codigo"]))
            valor = _num(linha.get(colunas["valor"]))
            if not codigo:
                c.descartar("codigo invalido")
                continue
            linhas.append({"codigo_ibge": codigo, "renda_mediana": valor})
        df = pd.DataFrame(linhas).drop_duplicates(subset=["codigo_ibge"])
        c.saida = len(df)
        # Mesma guarda da populacao: respondeu 200 mas nada virou numero e
        # falha, nao "coluna vazia". Aqui a candidata seguinte ganha a vez.
        if df.empty or int(df["renda_mediana"].notna().sum()) == 0:
            raise FonteIndisponivel(
                FONTE, f"tabela {candidata['tabela']} respondeu sem nenhum valor aproveitavel"
            )
    return df


def malha(uf: str, *, refresh: bool = False) -> dict[str, Any]:
    """GeoJSON dos municipios de uma UF. Devolve {codigo_ibge: feature}."""
    cfg = carregar()["ibge"]
    codigo_uf = UF_CODIGO[uf.upper()]
    url = cfg["malha_uf_url"].format(uf=codigo_uf)

    with etapa(f"ingest.ibge.malha.{uf}") as c:
        geojson = get_or_set(FONTE, f"malha-{uf}", lambda: get_json(FONTE, url), refresh=refresh)
        feicoes = geojson.get("features", [])
        c.entrada = len(feicoes)
        saida: dict[str, Any] = {}
        for f in feicoes:
            props = f.get("properties") or {}
            codigo = para_codigo7(props.get("codarea") or props.get("id") or props.get("CD_MUN"))
            if not codigo:
                c.descartar("feicao sem codigo")
                continue
            saida[codigo] = f
        c.saida = len(saida)
    return saida


def geometria_para_atributos(feature: dict[str, Any]) -> dict[str, Any]:
    """Centroide e area a partir da geometria — evita mais uma chamada de API."""
    geom = feature.get("geometry") or {}
    cent = centroide(geom)
    return {
        "lat": round(cent[0], 6) if cent else None,
        "lon": round(cent[1], 6) if cent else None,
        "area_km2": area_km2(geom),
    }
