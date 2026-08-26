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
# Quanto da resposta do SIDRA precisa virar numero para a populacao valer.
# Abaixo disso o ranking sairia pela metade parecendo completo.
COBERTURA_MINIMA = 0.9
# Faixa plausivel para a fracao da populacao com 40 anos ou mais. O Censo 2022
# da ~45% para o Brasil, e nenhum municipio realista sai de 25%–65%.
FRACAO_40_MAIS_MIN = 0.25
FRACAO_40_MAIS_MAX = 0.65

_VALOR_AUSENTE = {"-", "..", "...", "X", "..X", None, ""}


# Quantos municipios por chamada ao SIDRA. Pedir "todos do estado" de uma vez
# devolve uma resposta truncada sem dizer que truncou: em SC vieram 171 dos 295,
# e os que faltaram sumiram do ranking parecendo que nao existiam. Lotes
# explicitos de codigo tornam a resposta determinstica e conferivel.
#
# 25 e nao 60: com 60 codigos a URL passa de 500 caracteres e o SIDRA derruba a
# conexao antes de responder (ConnectTimeout nas cinco tentativas). O limite
# nao esta documentado, entao o numero e conservador de proposito.
MUNICIPIOS_POR_LOTE = 25


def _lotes(codigos: list[str], tamanho: int | None = None) -> list[list[str]]:
    # Lido na chamada, nao no default: um default congela o valor na definicao
    # do modulo e o torna impossivel de ajustar.
    n = tamanho or MUNICIPIOS_POR_LOTE
    return [codigos[i : i + n] for i in range(0, len(codigos), n)]


def _filtro_n6(ufs: list[str] | None) -> str:
    """Filtro territorial do SIDRA: municipios de uma UF ou do Brasil inteiro."""
    if not ufs:
        return "n6/all"
    codigos = [str(UF_CODIGO[uf.upper()]) for uf in ufs if uf.upper() in UF_CODIGO]
    if not codigos:
        return "n6/all"
    return "n6/in n3 " + ",".join(codigos)


# Achar a coluna de faixa etaria por substring de "idade" errou duas vezes
# seguidas, de dois jeitos diferentes:
#
#   "Forma de declaração da idade"  — casa, mas vale "Total" em toda linha
#   "Unidade de Medida"             — casa dentro de "UNidade", e vale "Pessoas"
#
# Nenhuma das duas levantou erro: a populacao 40+ so saiu zerada nos 295
# municipios. Dai a palavra inteira mais uma lista de impostoras conhecidas.
_IDADE = re.compile(r"\b(idade|et[áa]ri[ao])\b")
_IDADE_IMPOSTORA = ("forma de declara", "unidade de medida")


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
        elif _IDADE.search(r) and not e_codigo and not any(i in r for i in _IDADE_IMPOSTORA):
            # setdefault e nao atribuicao: o primeiro rotulo de idade e o mais
            # direto ("Idade", "Grupo de idade"); o que vier depois e adorno.
            mapa.setdefault("idade", chave)
        elif "variável" in r or "variavel" in r:
            # Com v/all o SIDRA devolve varias variaveis por municipio; sem
            # saber o rotulo de cada linha nao da para escolher a certa.
            (mapa.__setitem__("variavel_codigo", chave) if e_codigo
             else mapa.setdefault("variavel", chave))
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
    # A classificacao por ano simples traz "2 meses", "27 dias". O numero ali
    # nao e idade em anos: sao bebes, e todos entram na faixa zero.
    if "mes" in r or "mês" in r or "dia" in r or "semana" in r:
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


def _classificacao_de_idade(tabela: str, *, refresh: bool = False) -> str | None:
    """`c<id>` da classificacao de faixa etaria da tabela, lida dos metadados.

    O codigo estava fixo em c287 e a tabela nao respondia por ele: vinha so a
    linha "Total" e a populacao 40+ saia zerada em todos os municipios, sem
    erro. Perguntar aos metadados custa uma chamada cacheada e sobrevive a
    renumeracao.
    """
    cfg = carregar()["ibge"]
    url = cfg.get("metadados_url", "").format(tabela=tabela)
    if not url:
        return None
    try:
        meta = get_or_set(
            FONTE, f"metadados-{tabela}", lambda: get_json(FONTE, url), refresh=refresh
        )
    except FonteIndisponivel as exc:
        aviso("metadados da tabela indisponiveis", tabela=tabela, erro=str(exc)[:120])
        return None
    candidatas = [
        c for c in (meta.get("classificacoes") or [])
        if "idade" in str(c.get("nome", "")).lower()
    ]
    # "Grupo de idade" antes de "Idade": a segunda e por ano simples e devolve
    # uma linha por ano de vida por municipio, resposta muito maior para a
    # mesma informacao.
    candidatas.sort(key=lambda c: 0 if "grupo" in str(c.get("nome", "")).lower() else 1)
    if candidatas:
        escolhida = candidatas[0]
        log(
            "classificacao de idade descoberta",
            tabela=tabela, id=escolhida.get("id"), nome=escolhida.get("nome"),
        )
        return f"c{escolhida['id']}"
    aviso("tabela sem classificacao de idade", tabela=tabela)
    return None


def _buscar_em_lotes(
    cfg: dict[str, Any], ufs: list[str] | None, codigos: list[str] | None, *, refresh: bool
) -> list[dict[str, Any]]:
    """Uma chamada por lote de municipios; devolve cabecalho + linhas de todos.

    Sem a lista de codigos cai no filtro por UF, que e o comportamento antigo —
    util para uma consulta exploratoria, arriscado para producao.
    """
    idade = _classificacao_de_idade(str(cfg["tabela"]), refresh=refresh) or cfg.get("classificacao_idade")
    classificacao = f"{idade}/all" if idade else ""
    base_chave = f"populacao-{cfg['tabela']}-{cfg['periodo']}-{idade}-"
    if not codigos:
        url = cfg["sidra_url"].format(
            tabela=cfg["tabela"],
            variavel=cfg["variavel"],
            periodo=cfg["periodo"],
            n6=_filtro_n6(ufs),
            classificacao=classificacao,
        )
        chave = base_chave + (",".join(sorted(ufs)) if ufs else "BR")
        return get_or_set(FONTE, chave, lambda: get_json(FONTE, url), refresh=refresh)

    cabecalho: dict[str, Any] | None = None
    linhas: list[dict[str, Any]] = []
    lotes = _lotes(sorted(set(codigos)))
    for i, lote in enumerate(lotes, start=1):
        url = cfg["sidra_url"].format(
            tabela=cfg["tabela"],
            variavel=cfg["variavel"],
            periodo=cfg["periodo"],
            n6="n6/" + ",".join(lote),
            classificacao=classificacao,
        )
        chave = f"{base_chave}lote-{lote[0]}-{lote[-1]}"
        parte = get_or_set(FONTE, chave, lambda u=url: get_json(FONTE, u), refresh=refresh)
        if not parte or len(parte) < 2:
            aviso("lote de populacao veio vazio", lote=i, de=lote[0], ate=lote[-1])
            continue
        cabecalho = cabecalho or parte[0]
        linhas.extend(parte[1:])
    log("populacao buscada em lotes", lotes=len(lotes), municipios=len(set(codigos)), linhas=len(linhas))
    return [cabecalho, *linhas] if cabecalho else []


def populacao_por_idade(
    ufs: list[str] | None = None,
    *,
    codigos: list[str] | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Populacao total e populacao 40+ por municipio (Censo, via SIDRA).

    A populacao 40+ e o proxy de presbiopia — o publico que efetivamente compra
    oculos de leitura. Sem ela o modelo perde o fator de mercado enderecavel.
    """
    cfg = carregar()["ibge"]["populacao"]
    idade_min = int(cfg.get("idade_minima", 40))

    with etapa("ingest.ibge.populacao") as c:
        bruto = _buscar_em_lotes(cfg, ufs, codigos, refresh=refresh)
        if not bruto or len(bruto) < 2:
            raise FonteIndisponivel(FONTE, "SIDRA devolveu resposta vazia para populacao")
        colunas = _mapa_colunas(bruto[0])
        faltando = {"codigo", "valor", "idade"} - set(colunas)
        if faltando:
            raise FonteIndisponivel(FONTE, f"cabecalho SIDRA inesperado, faltam {faltando}: {bruto[0]}")
        c.entrada = len(bruto) - 1

        acumulado: dict[str, dict[str, float | None]] = {}
        rotulos_vistos: set[str] = set()
        somadas: set[str] = set()
        amostra_sem_valor: list[dict[str, Any]] = []
        for linha in bruto[1:]:
            codigo = para_codigo7(linha.get(colunas["codigo"]))
            if not codigo:
                c.descartar("codigo invalido")
                continue
            rotulo = str(linha.get(colunas["idade"], ""))
            rotulos_vistos.add(rotulo.strip())
            valor = _num(linha.get(colunas["valor"]))
            if valor is None and len(amostra_sem_valor) < 3:
                amostra_sem_valor.append(linha)
            reg = acumulado.setdefault(codigo, {"populacao_total": None, "populacao_40mais": None})
            inicio = idade_inicial(rotulo)
            if rotulo.strip().lower().startswith("total"):
                reg["populacao_total"] = valor
            elif inicio is not None and valor is not None and inicio >= idade_min:
                somadas.add(rotulo.strip())
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
        # Medir contra o universo PEDIDO, nao contra o que a resposta trouxe:
        # uma resposta truncada e 100% coerente consigo mesma e mesmo assim
        # deixou 124 municipios de fora do ranking.
        vistos = len(set(codigos)) if codigos else len(acumulado)
        cobertura = uteis / vistos if vistos else 0.0
        if cobertura < COBERTURA_MINIMA:
            # Cobertura parcial e mais perigosa que zero: o ranking sai pela
            # metade e parece completo. Quem ficou de fora nao e aleatorio — sao
            # os municipios de um recorte inteiro da resposta —, entao isto e
            # falha, nao aviso.
            raise FonteIndisponivel(
                FONTE,
                f"SIDRA cobriu {uteis} de {vistos} municipios ({cobertura:.0%}) para populacao — "
                f"abaixo do minimo de {COBERTURA_MINIMA:.0%}. "
                f"Cabecalho: {bruto[0]}. "
                f"Rotulos de idade vistos: {sorted(rotulos_vistos)[:12]}. "
                f"Linhas sem valor: {amostra_sem_valor}",
            )
        sem_40 = int(df["populacao_40mais"].isna().sum()) if not df.empty else 0
        if sem_40:
            aviso("municipios sem populacao 40+", quantidade=sem_40)

        # A fracao 40+ e o que dimensiona a demanda inteira do modelo: se ela
        # dobrar, toda projecao de faturamento dobra junto. No Brasil ela fica
        # perto de 45%; fora da faixa abaixo alguma faixa etaria esta sendo
        # contada duas vezes ou de menos, e isso nao pode passar calado.
        fracao = (df["populacao_40mais"] / df["populacao_total"]).median()
        log(
            "faixas etarias somadas em 40+",
            quantidade=len(somadas),
            fracao_mediana=None if pd.isna(fracao) else round(float(fracao), 3),
            faixas=", ".join(sorted(somadas)[:40]),
        )
        if pd.notna(fracao) and not (FRACAO_40_MAIS_MIN <= fracao <= FRACAO_40_MAIS_MAX):
            raise FonteIndisponivel(
                FONTE,
                f"populacao 40+ deu {fracao:.0%} da populacao total, fora da faixa plausivel "
                f"({FRACAO_40_MAIS_MIN:.0%}–{FRACAO_40_MAIS_MAX:.0%}). "
                f"Faixas somadas ({len(somadas)}): {sorted(somadas)[:40]}",
            )
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
        preferencia = [p.lower() for p in (candidata.get("preferir_variavel") or [])]
        col_var = colunas.get("variavel")
        linhas = []
        for linha in bruto[1:]:
            codigo = para_codigo7(linha.get(colunas["codigo"]))
            if not codigo:
                c.descartar("codigo invalido")
                continue
            if preferencia and col_var:
                # Pedir v/all e escolher pelo rotulo e mais robusto do que
                # fixar um codigo de variavel: o IBGE renumera variavel entre
                # tabelas, e o rotulo ("mediano", "medio") sobrevive melhor.
                rotulo = str(linha.get(col_var, "")).lower()
                if not any(termo in rotulo for termo in preferencia):
                    c.descartar("variavel diferente da pedida")
                    continue
            valor = _num(linha.get(colunas["valor"]))
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
