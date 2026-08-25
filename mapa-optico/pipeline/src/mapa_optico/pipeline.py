"""Orquestracao: junta as quatro fontes numa base unica por municipio.

Principio que atravessa o arquivo: FONTE QUE FALHA VIRA NULO + AVISO, nunca
zero e nunca chute. Cada campo carrega sua proveniencia em `fonte_por_campo`,
e a ausencia derruba a confianca do municipio no score.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .http import FonteIndisponivel
from .ingest import cnes as ing_cnes
from .ingest import ibge as ing_ibge
from .ingest import mirrors as ing_espelho
from .ingest import osrm as ing_osrm
from .ingest import places as ing_places
from .load import exports
from .logs import aviso, etapa, log
from .score.model import calcular_score, circuitos, pares_canibalizacao
from .score.projecao import projecao_de_circuito, projetar
from .settings import DATA_DIR, carregar_negocio, carregar_pesos, garantir_dirs

COLUNAS_BASE = [
    "codigo_ibge", "nome", "uf", "microrregiao", "mesorregiao", "lat", "lon", "area_km2",
    "populacao_total", "populacao_40mais", "renda_mediana",
    "qtd_oftalmologistas", "oftalmo_equivalente", "horas_semanais_total", "competencia_cnes",
    "polo_codigo_ibge", "polo_nome", "distancia_km", "tempo_minutos",
    "qtd_oticas", "oticas_nota_media", "oticas_avaliacoes",
]


class Proveniencia:
    """Registra de onde veio cada bloco de dado, quando, e o que faltou.

    O carimbo de tempo por bloco existe para a tela de sincronizacao: ela
    precisa dizer "os medicos sao da competencia de junho, as oticas foram
    consultadas ha 4 meses" sem ter que adivinhar pela data do arquivo inteiro.
    Fontes diferentes envelhecem em ritmos diferentes.
    """

    def __init__(self) -> None:
        self.fontes: dict[str, str] = {}
        self.avisos: list[str] = []
        self.detalhes: dict[str, dict[str, Any]] = {}
        # Quantos municipios têm cada campo, no fim da montagem. Um merge que
        # erra a chave nao levanta excecao — devolve tudo nulo e o pipeline
        # segue. Isto viaja junto do snapshot para que a diferenca entre "a
        # fonte falhou" e "a juncao falhou" seja visivel de fora.
        self.preenchimento: dict[str, int] = {}

    def ok(self, bloco: str, origem: str, **extra: Any) -> None:
        self.fontes[bloco] = origem
        self.detalhes[bloco] = {
            "origem": origem,
            "atualizado_em": datetime.now(UTC).isoformat(timespec="seconds"),
            **{k: v for k, v in extra.items() if isinstance(v, (str, int, float, bool))},
        }
        log("fonte carregada", bloco=bloco, origem=origem, **extra)

    def falhou(self, bloco: str, motivo: str) -> None:
        self.fontes[bloco] = "indisponivel"
        texto = f"{bloco}: {motivo}"
        self.avisos.append(texto)
        self.detalhes[bloco] = {
            "origem": "indisponivel",
            "atualizado_em": None,
            "motivo": motivo,
        }
        aviso("fonte indisponivel — campos ficarao NULOS", bloco=bloco, motivo=motivo)

    def como_dict(self) -> dict[str, Any]:
        return {
            "fontes": self.fontes,
            "avisos": self.avisos,
            "detalhes": self.detalhes,
            "preenchimento": self.preenchimento,
        }


def caminho_base(ufs: list[str]) -> Path:
    return DATA_DIR / f"base-{'-'.join(sorted(ufs)) if ufs else 'BR'}.json"


def salvar_base(
    df: pd.DataFrame, ufs: list[str], prov: Proveniencia, oticas: pd.DataFrame | None = None
) -> Path:
    garantir_dirs()
    destino = caminho_base(ufs)
    payload = {
        "proveniencia": prov.como_dict(),
        "oticas": json.loads(oticas.to_json(orient="records")) if oticas is not None and not oticas.empty else [],
        "municipios": json.loads(df.to_json(orient="records")),
    }
    destino.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    log("base salva", arquivo=str(destino), municipios=len(df))
    return destino


def carregar_base(ufs: list[str]) -> tuple[pd.DataFrame, Proveniencia, list[dict[str, Any]]]:
    destino = caminho_base(ufs)
    if not destino.exists():
        raise FileNotFoundError(
            f"{destino} nao existe. Rode `mapa-optico ingest --uf {','.join(ufs)}` antes."
        )
    payload = json.loads(destino.read_text(encoding="utf-8"))
    prov = Proveniencia()
    guardado = payload.get("proveniencia", {})
    prov.fontes = guardado.get("fontes", {})
    prov.avisos = guardado.get("avisos", [])
    prov.detalhes = guardado.get("detalhes", {})
    return pd.DataFrame(payload["municipios"]), prov, payload.get("oticas", [])


def montar_base(
    ufs: list[str],
    *,
    usar_espelho: bool = False,
    com_places: bool = True,
    com_osrm: bool = True,
    refresh: bool = False,
    salvar_malha: bool = True,
) -> tuple[pd.DataFrame, Proveniencia, list[dict[str, Any]]]:
    """Ingestao das quatro fontes -> uma linha por municipio."""
    prov = Proveniencia()

    # ---------------------------------------------------------- 1. municipios
    base: pd.DataFrame | None = None
    if not usar_espelho:
        try:
            base = ing_ibge.municipios(ufs, refresh=refresh)
            prov.ok("municipios", "ibge_localidades", linhas=len(base))
        except FonteIndisponivel as exc:
            prov.falhou("municipios", f"API do IBGE indisponivel ({exc}); tentando espelho")
    if base is None or base.empty:
        base = ing_espelho.municipios(ufs, refresh=refresh)
        prov.ok("municipios", "espelho", linhas=len(base))
    if base.empty:
        raise RuntimeError("nenhum municipio carregado — sem dimensao nao ha pipeline")

    # ------------------------------------------------- 2. malha (centroide/area)
    malhas: dict[str, Any] = {}
    for uf in ufs or sorted(base["uf"].dropna().unique()):
        try:
            if usar_espelho:
                raise FonteIndisponivel("ibge", "espelho forcado por parametro")
            malhas[uf] = ing_ibge.malha(uf, refresh=refresh)
            prov.ok(f"malha_{uf}", "ibge_malhas", feicoes=len(malhas[uf]))
        except FonteIndisponivel as exc:
            try:
                malhas[uf] = ing_espelho.malha(uf, refresh=refresh)
                prov.ok(f"malha_{uf}", "espelho", feicoes=len(malhas[uf]))
            except FonteIndisponivel as exc2:
                prov.falhou(f"malha_{uf}", f"{exc}; espelho tambem falhou: {exc2}")

    atributos = {}
    for uf, malha in malhas.items():
        for codigo, feature in malha.items():
            atributos[codigo] = ing_ibge.geometria_para_atributos(feature)
    if atributos:
        geo = pd.DataFrame(
            [{"codigo_ibge": k, **v} for k, v in atributos.items()]
        )
        base = base.merge(geo, on="codigo_ibge", how="left", suffixes=("", "_geo"))
        for col in ("lat", "lon"):
            if f"{col}_geo" in base.columns:
                base[col] = base[col].fillna(base[f"{col}_geo"])
                base = base.drop(columns=[f"{col}_geo"])
    for col in ("lat", "lon", "area_km2"):
        if col not in base.columns:
            base[col] = pd.NA

    if salvar_malha:
        for uf, malha in malhas.items():
            exports.malha_para_web(malha, uf)

    # ------------------------------------------------ 3. populacao e renda
    try:
        # Passar os codigos faz a busca ir em lotes explicitos. Sem isso o
        # SIDRA trunca a resposta calado.
        pop = ing_ibge.populacao_por_idade(
            ufs, codigos=base["codigo_ibge"].dropna().astype(str).tolist(), refresh=refresh
        )
        base = base.merge(pop, on="codigo_ibge", how="left")
        prov.ok("populacao", "sidra", linhas=len(pop))
    except FonteIndisponivel as exc:
        base["populacao_total"] = pd.NA
        base["populacao_40mais"] = pd.NA
        prov.falhou("populacao", str(exc))

    try:
        renda = ing_ibge.renda(ufs, refresh=refresh)
        base = base.merge(renda, on="codigo_ibge", how="left")
        prov.ok("renda", "sidra", linhas=len(renda))
    except FonteIndisponivel as exc:
        base["renda_mediana"] = pd.NA
        prov.falhou("renda", str(exc))

    # ------------------------------------------------------------- 4. CNES
    oferta = pd.DataFrame()
    partes = []
    for uf in ufs or sorted(base["uf"].dropna().unique()):
        try:
            parte, meta = ing_cnes.oftalmologistas_por_municipio(uf, refresh=refresh)
            parte["origem"] = meta["origem"]
            partes.append(parte)
            prov.ok(f"cnes_{uf}", meta["origem"], **{k: meta[k] for k in ("competencia", "profissionais_unicos")})
        except ing_cnes.CnesIndisponivel as exc:
            prov.falhou(f"cnes_{uf}", str(exc))
    if partes:
        oferta = pd.concat(partes, ignore_index=True)
        base = base.merge(oferta, on="codigo_ibge", how="left")
        # Municipio da UF processada e ausente na base do CNES = zero de verdade.
        base["qtd_oftalmologistas"] = base["qtd_oftalmologistas"].fillna(0)
        base["oftalmo_equivalente"] = base["oftalmo_equivalente"].fillna(0.0)
    else:
        for col in ("qtd_oftalmologistas", "oftalmo_equivalente", "horas_semanais_total", "competencia_cnes"):
            base[col] = pd.NA

    # ------------------------------------------- 5. distancia ao polo (OSRM)
    distancias = pd.DataFrame()
    min_oftalmo = int(carregar_pesos().get("polo", {}).get("min_oftalmologistas", 3))
    if com_osrm and "qtd_oftalmologistas" in base.columns and base["qtd_oftalmologistas"].notna().any():
        polos = base[pd.to_numeric(base["qtd_oftalmologistas"], errors="coerce") >= min_oftalmo]
        log("polos identificados", quantidade=len(polos), min_oftalmologistas=min_oftalmo)
        try:
            distancias = ing_osrm.calcular(base, polos, refresh=refresh)
            base = base.merge(distancias, on="codigo_ibge", how="left")
            prov.ok("distancia_polo", "osrm", polos=len(polos))
        except FonteIndisponivel as exc:
            prov.falhou("distancia_polo", str(exc))
    else:
        prov.falhou("distancia_polo", "sem CNES nao ha polo definido")
    for col in ("distancia_km", "tempo_minutos", "polo_nome", "polo_codigo_ibge"):
        if col not in base.columns:
            base[col] = pd.NA

    # ------------------------------------------------------------ 6. Places
    oticas = pd.DataFrame()
    if com_places:
        try:
            oticas = ing_places.coletar(base, refresh=refresh)
            contagem = ing_places.contar_por_municipio(oticas, base)
            base = base.merge(contagem, on="codigo_ibge", how="left")
            prov.ok("oticas", "google_places", encontradas=len(oticas))
        except (FonteIndisponivel, RuntimeError) as exc:
            for col in ("qtd_oticas", "oticas_nota_media", "oticas_avaliacoes"):
                base[col] = pd.NA
            prov.falhou("oticas", str(exc))
    else:
        for col in ("qtd_oticas", "oticas_nota_media", "oticas_avaliacoes"):
            base[col] = pd.NA
        prov.falhou("oticas", "coleta do Places desligada nesta execucao (--sem-places)")

    for col in COLUNAS_BASE:
        if col not in base.columns:
            base[col] = pd.NA
    base = base[COLUNAS_BASE]
    # Contagem de preenchimento por coluna. Um merge que erra a chave nao
    # levanta excecao — ele devolve tudo nulo e o pipeline segue. Este log e o
    # que separa "a fonte falhou" de "a juncao falhou", e ja pegou uma vez os
    # 295 municipios virando 124 sem ninguem notar.
    prov.preenchimento = {"_municipios": len(base)} | {
        col: int(base[col].notna().sum()) for col in COLUNAS_BASE if col != "codigo_ibge"
    }
    log("preenchimento da base", **prov.preenchimento)
    vazias = [col for col, n in prov.preenchimento.items() if n == 0]
    if vazias:
        aviso("colunas inteiramente nulas na base", colunas=",".join(vazias))
    salvar_base(base, ufs, prov, oticas)
    registros_oticas = json.loads(oticas.to_json(orient="records")) if not oticas.empty else []
    return base, prov, registros_oticas


def rodar_score(
    base: pd.DataFrame,
    prov: Proveniencia,
    *,
    caminho_pesos: str | None = None,
    caminho_negocio: str | None = None,
    exportar: bool = True,
    oticas: list[dict[str, Any]] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Score + projecao financeira + circuitos + canibalizacao + exportacoes.

    A ordem importa: os circuitos saem do score, e a projecao de circuito soma a
    projecao ja calculada por municipio. Rodar a projecao depois do cluster
    permite diluir o deslocamento do medico uma vez por viagem, nao por cidade.
    """
    pesos = carregar_pesos(caminho_pesos)
    negocio = carregar_negocio(caminho_negocio)
    with etapa("pipeline.score"):
        ranking = calcular_score(base, pesos)
        if ranking.empty:
            return ranking, {"canibalizacao": [], "circuitos": 0, "circuitos_projetados": []}
        cl = circuitos(ranking, pesos)
        ranking = ranking.merge(cl, on="codigo_ibge", how="left")
        canibais = pares_canibalizacao(ranking, pesos)
        ranking = projetar(ranking, negocio)
        circuitos_projetados = projecao_de_circuito(ranking, negocio)
    if exportar:
        exports.exportar_planilhas(ranking, prefixo=f"ranking-{pesos.get('versao', 'v1')}")
        exports.snapshot_para_web(
            ranking,
            pesos,
            negocio=negocio,
            canibalizacao=canibais,
            circuitos=json.loads(circuitos_projetados.to_json(orient="records"))
            if not circuitos_projetados.empty
            else [],
            oticas=oticas,
            proveniencia=prov.como_dict(),
            avisos=prov.avisos,
        )
    return ranking, {
        "canibalizacao": canibais,
        "circuitos": int(cl["circuito"].nunique()) if not cl.empty else 0,
        "circuitos_projetados": json.loads(circuitos_projetados.to_json(orient="records"))
        if not circuitos_projetados.empty
        else [],
    }
