"""Interface de linha de comando do pipeline.

    mapa-optico fase0 --uf SC          # valida a leitura do CNES (o maior risco)
    mapa-optico checar-fontes          # testa cada endpoint configurado
    mapa-optico ingest --uf SC         # ingestao das 4 fontes -> data/base-SC.json
    mapa-optico score                  # recalcula o ranking a partir da base
    mapa-optico exportar               # CSV/XLSX + snapshot do dashboard
    mapa-optico carregar               # sobe para o Supabase
    mapa-optico demo --uf SC           # snapshot SINTETICO so para exercitar a interface
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from . import pipeline as pipe
from .http import FonteIndisponivel, get_json
from .ingest import cnes as ing_cnes
from .ingest.fontes import carregar as carregar_fontes
from .load import exports
from .logs import configurar
from .settings import carregar_negocio, carregar_pesos, garantir_dirs, get_settings

app = typer.Typer(add_completion=False, help="Mapa Optico — ranking de municipios para eventos de saude ocular")
console = Console()


def _ufs(valor: str) -> list[str]:
    return [u.strip().upper() for u in valor.split(",") if u.strip()]


@app.callback()
def _global(json_logs: bool = typer.Option(False, "--json-logs", help="logs em JSON")) -> None:
    configurar(json_output=json_logs)
    garantir_dirs()


# ------------------------------------------------------------------- fase 0
@app.command()
def fase0(
    uf: str = typer.Option("SC", help="UF a validar"),
    competencia: str = typer.Option(None, help="YYYYMM; vazio = ultima disponivel"),
    caminho: str = typer.Option(None, "--caminho", help="forcar 'pysus' ou 'csv'"),
) -> None:
    """Fase 0: prova que conseguimos ler o CNES e contar oftalmologistas por municipio.

    Criterio de saida do briefing: Florianopolis e Joinville tem que bater com a
    realidade (dezenas de oftalmologistas, nao 2 e nao 500).
    """
    console.rule(f"[bold]Fase 0 — leitura do CNES ({uf})")
    try:
        agregado, meta = ing_cnes.oftalmologistas_por_municipio(
            uf, competencia=competencia, caminho_preferido=caminho
        )
    except ing_cnes.CnesIndisponivel as exc:
        console.print(f"[bold red]CNES indisponivel.[/]\n{exc}")
        console.print(
            "\n[yellow]Conforme o briefing, o pipeline PARA aqui em vez de improvisar uma terceira "
            "solucao. Caminhos possiveis:[/]\n"
            "  1. `uv sync --extra cnes` e rodar de novo (baixa o .DBC do DATASUS)\n"
            "  2. baixar a extracao CSV da UF em "
            "https://cnes.datasus.gov.br/pages/profissionais/extracao.jsp e salvar em pipeline/data/manual/\n"
            "  3. Base dos Dados (BigQuery) — exige credencial GCP"
        )
        raise typer.Exit(code=2)

    tabela = Table(title=f"Oftalmologistas por municipio — {uf} (competencia {meta['competencia']})")
    tabela.add_column("codigo IBGE")
    tabela.add_column("oftalmologistas", justify="right")
    tabela.add_column("horas/semana", justify="right")
    tabela.add_column("equivalente 40h", justify="right")
    top = agregado.sort_values("qtd_oftalmologistas", ascending=False).head(25)
    for r in top.to_dict("records"):
        tabela.add_row(
            str(r["codigo_ibge"]),
            str(int(r["qtd_oftalmologistas"])),
            "—" if pd.isna(r.get("horas_semanais_total")) else f"{float(r['horas_semanais_total']):.0f}",
            "—" if pd.isna(r.get("oftalmo_equivalente")) else f"{float(r['oftalmo_equivalente']):.1f}",
        )
    console.print(tabela)

    conferencia = {"4205407": "Florianopolis", "4209102": "Joinville"}
    console.rule("[bold]Conferencia de sanidade")
    for codigo, nome in conferencia.items():
        linha = agregado[agregado["codigo_ibge"] == codigo]
        if linha.empty:
            console.print(f"[red]{nome} ({codigo}): NAO aparece na base — o join ou o filtro estao errados.[/]")
        else:
            qtd = int(linha.iloc[0]["qtd_oftalmologistas"])
            cor = "green" if qtd >= 10 else "yellow"
            console.print(f"[{cor}]{nome} ({codigo}): {qtd} oftalmologistas unicos[/]")
    console.print(f"\norigem: [bold]{meta['origem']}[/] · CBOs: {meta['cbos']} · vinculos lidos: {meta['vinculos']}")


# ------------------------------------------------------------ checar fontes
@app.command("checar-fontes")
def checar_fontes(uf: str = typer.Option("SC")) -> None:
    """Testa cada endpoint configurado e diz qual esta de pe. Nao grava nada."""
    cfg = carregar_fontes()
    s = get_settings()
    alvos: list[tuple[str, str]] = [
        ("IBGE localidades", cfg["ibge"]["localidades_url"]),
        ("IBGE malhas", cfg["ibge"]["malha_uf_url"].format(uf=42)),
        (
            "SIDRA populacao",
            cfg["ibge"]["populacao"]["sidra_url"].format(
                tabela=cfg["ibge"]["populacao"]["tabela"],
                variavel=cfg["ibge"]["populacao"]["variavel"],
                periodo=cfg["ibge"]["populacao"]["periodo"],
                n6="n6/4205407",
            ),
        ),
        (
            "SIDRA renda",
            cfg["ibge"]["renda"]["sidra_url"].format(
                tabela=cfg["ibge"]["renda"]["tabela"],
                variavel=cfg["ibge"]["renda"]["variavel"],
                periodo=cfg["ibge"]["renda"]["periodo"],
                n6="n6/4205407",
            ),
        ),
        ("OSRM", f"{s.osrm_base_url}/route/v1/driving/-48.5,-27.6;-48.8,-26.3?overview=false"),
        ("Espelho municipios", cfg["espelhos"]["municipios_csv"]),
    ]

    tabela = Table(title="Fontes externas")
    tabela.add_column("fonte")
    tabela.add_column("status")
    tabela.add_column("detalhe", overflow="fold")
    for nome, url in alvos:
        fonte = "mirror" if "Espelho" in nome else ("osrm" if "OSRM" in nome else "ibge")
        try:
            if "Espelho" in nome:
                # CSV, nao JSON: basta confirmar que responde e tem conteudo.
                from .http import requisitar

                resp = requisitar(fonte, url, tentativas=1)
                amostra = f"{len(resp.content) // 1024} KB, {resp.text.count(chr(10))} linhas"
            else:
                dados = get_json(fonte, url, tentativas=1)
                amostra = (
                    f"{len(dados)} itens"
                    if isinstance(dados, list)
                    else json.dumps(dados, ensure_ascii=False)[:90]
                )
            tabela.add_row(nome, "[green]ok[/]", amostra)
        except FonteIndisponivel as exc:
            tabela.add_row(nome, "[red]falhou[/]", str(exc)[:120])
        except Exception as exc:  # noqa: BLE001 - checagem nao pode derrubar o comando
            tabela.add_row(nome, "[yellow]?[/]", f"{type(exc).__name__}: {exc}"[:120])

    tabela.add_row(
        "Google Places",
        "[green]chave presente[/]" if s.tem_places else "[yellow]sem chave[/]",
        "GOOGLE_PLACES_API_KEY no .env" if not s.tem_places else "nao consultado (custa dinheiro)",
    )
    tabela.add_row(
        "Supabase",
        "[green]configurado[/]" if s.tem_supabase else "[yellow]nao configurado[/]",
        "sem Supabase o pipeline exporta so arquivo local",
    )
    console.print(tabela)


# ---------------------------------------------------------------- ingestao
@app.command()
def ingest(
    uf: str = typer.Option("SC", help="UFs separadas por virgula"),
    espelho: bool = typer.Option(False, "--espelho", help="usar espelhos publicos em vez das APIs do IBGE"),
    sem_places: bool = typer.Option(False, "--sem-places", help="pular o Google Places (nao gasta)"),
    sem_osrm: bool = typer.Option(False, "--sem-osrm", help="pular o calculo de distancia"),
    refresh: bool = typer.Option(False, "--refresh", help="ignorar o cache em disco"),
    pular_score: bool = typer.Option(False, "--pular-score"),
) -> None:
    """Roda a ingestao das quatro fontes e ja calcula o score."""
    ufs = _ufs(uf)
    base, prov, oticas = pipe.montar_base(
        ufs,
        usar_espelho=espelho,
        com_places=not sem_places,
        com_osrm=not sem_osrm,
        refresh=refresh,
    )
    _resumo_proveniencia(prov, base)
    if not pular_score:
        ranking, extras = pipe.rodar_score(base, prov, oticas=oticas)
        _mostrar_ranking(ranking, extras)


@app.command()
def score(
    uf: str = typer.Option("SC"),
    pesos: str = typer.Option(None, "--pesos", help="caminho de um weights.yaml alternativo"),
    negocio: str = typer.Option(None, "--negocio", help="caminho de um negocio.yaml alternativo"),
) -> None:
    """Recalcula ranking e projecao financeira a partir da base ja ingerida (nao toca a rede)."""
    base, prov, oticas = pipe.carregar_base(_ufs(uf))
    ranking, extras = pipe.rodar_score(
        base, prov, caminho_pesos=pesos, caminho_negocio=negocio, oticas=oticas
    )
    _mostrar_ranking(ranking, extras)


@app.command()
def exportar(uf: str = typer.Option("SC")) -> None:
    """Regera CSV/XLSX e o snapshot do dashboard a partir da base."""
    base, prov, oticas = pipe.carregar_base(_ufs(uf))
    ranking, _ = pipe.rodar_score(base, prov, oticas=oticas)
    console.print(f"[green]exportado[/] {len(ranking)} municipios")


@app.command()
def carregar(uf: str = typer.Option("SC")) -> None:
    """Sobe a base e o ranking para o Supabase (upsert idempotente)."""
    from .load.supabase_loader import SupabaseIndisponivel, carregar_tudo

    base, prov, oticas_registros = pipe.carregar_base(_ufs(uf))
    ranking, _ = pipe.rodar_score(base, prov, exportar=False)
    vazio = pd.DataFrame()
    negocio = carregar_negocio()
    try:
        resumo = carregar_tudo(
            municipios=base,
            oferta=base[base["qtd_oftalmologistas"].notna()][
                ["codigo_ibge", "qtd_oftalmologistas", "horas_semanais_total", "oftalmo_equivalente", "competencia_cnes"]
            ]
            if "competencia_cnes" in base.columns
            else vazio,
            distancias=base[base["distancia_km"].notna()][
                ["codigo_ibge", "polo_codigo_ibge", "polo_nome", "distancia_km", "tempo_minutos"]
            ],
            oticas=pd.DataFrame(oticas_registros) if oticas_registros else vazio,
            scores=ranking,
            projecoes=ranking,
            versao_negocio=negocio.get("versao", "n1"),
        )
    except SupabaseIndisponivel as exc:
        console.print(f"[yellow]{exc}[/]")
        raise typer.Exit(code=1)
    console.print(resumo)


# --------------------------------------------------------------------- demo
@app.command()
def demo(uf: str = typer.Option("SC")) -> None:
    """Gera um snapshot SINTETICO para exercitar o dashboard sem dado real.

    Existe por um motivo so: permitir desenvolver a interface antes de o CNES
    estar disponivel. O snapshot sai marcado com `demo: true` e o dashboard
    exibe uma tarja vermelha permanente. NUNCA usar para decisao comercial.
    """
    import hashlib

    from .ingest import mirrors

    ufs = _ufs(uf)
    base = mirrors.municipios(ufs)
    malhas: dict[str, Any] = {}
    for u in ufs:
        try:
            malhas[u] = mirrors.malha(u)
            exports.malha_para_web(malhas[u], u)
        except FonteIndisponivel as exc:
            console.print(f"[yellow]malha de {u} indisponivel: {exc}[/]")

    def _rnd(codigo: str, sal: str, minimo: float, maximo: float) -> float:
        h = int(hashlib.sha256((codigo + sal).encode()).hexdigest()[:8], 16)
        return minimo + (h % 10_000) / 10_000 * (maximo - minimo)

    def _oticas_demo(codigo: str, pop: int, rnd: Any) -> dict[str, Any]:
        """Cidade sem otica nao tem nota — e nao pode ter nota zero inventada."""
        qtd = int(rnd(codigo, "ot", 0, 14))
        if qtd == 0:
            return {"qtd_oticas": 0, "oticas_nota_media": None, "oticas_avaliacoes": 0}
        return {
            "qtd_oticas": qtd,
            "oticas_nota_media": round(rnd(codigo, "nota", 3.1, 4.9), 2),
            "oticas_avaliacoes": int(qtd * rnd(codigo, "aval", 2, 90)),
        }

    linhas = []
    for r in base.to_dict("records"):
        codigo = r["codigo_ibge"]
        pop = int(_rnd(codigo, "pop", 3_000, 60_000))
        oftalmo = 0 if _rnd(codigo, "of", 0, 1) < 0.55 else int(_rnd(codigo, "of2", 1, 12))
        linhas.append(
            {
                **r,
                "area_km2": round(_rnd(codigo, "area", 80, 900), 1),
                "populacao_total": pop,
                "populacao_40mais": int(pop * _rnd(codigo, "40", 0.30, 0.46)),
                "renda_mediana": round(_rnd(codigo, "renda", 700, 4200)),
                "qtd_oftalmologistas": oftalmo,
                "oftalmo_equivalente": round(oftalmo * _rnd(codigo, "eq", 0.2, 1.0), 2),
                "horas_semanais_total": round(oftalmo * _rnd(codigo, "h", 8, 40)),
                "competencia_cnes": "DEMO00",
                "polo_codigo_ibge": None,
                "polo_nome": "(demo)",
                "distancia_km": round(_rnd(codigo, "dist", 5, 220), 1),
                "tempo_minutos": round(_rnd(codigo, "dist", 5, 220) * 1.15, 1),
                **_oticas_demo(codigo, pop, _rnd),
            }
        )
    df = pd.DataFrame(linhas)
    for col in pipe.COLUNAS_BASE:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[pipe.COLUNAS_BASE]

    prov = pipe.Proveniencia()
    prov.fontes = {"TUDO": "DEMO_SINTETICO"}
    prov.avisos = [
        (
            "DADOS SINTETICOS: numeros gerados por funcao pseudoaleatoria apenas para "
            "exercitar a interface. Nenhum numero desta tela veio de CNES, IBGE ou Google Places."
        )
    ]
    pesos = carregar_pesos()
    ranking, extras = pipe.rodar_score(df, prov)
    caminho = exports.snapshot_para_web(
        ranking,
        pesos,
        negocio=carregar_negocio(),
        canibalizacao=extras["canibalizacao"],
        circuitos=extras.get("circuitos_projetados", []),
        proveniencia={**prov.como_dict(), "demo": True},
        avisos=prov.avisos,
    )
    console.print(f"[bold yellow]SNAPSHOT DEMO (sintetico)[/] gravado em {caminho}")
    _mostrar_ranking(ranking, extras)


# ------------------------------------------------------------------ helpers
def _resumo_proveniencia(prov: pipe.Proveniencia, base: pd.DataFrame) -> None:
    tabela = Table(title="Proveniencia dos dados")
    tabela.add_column("bloco")
    tabela.add_column("origem")
    for bloco, origem in prov.fontes.items():
        cor = "red" if origem == "indisponivel" else ("yellow" if origem == "espelho" else "green")
        tabela.add_row(bloco, f"[{cor}]{origem}[/]")
    console.print(tabela)
    if prov.avisos:
        console.print("[yellow]Campos que ficaram NULOS (nao zero):[/]")
        for a in prov.avisos:
            console.print(f"  · {a}")


def _mostrar_ranking(ranking: pd.DataFrame, extras: dict[str, Any]) -> None:
    if ranking.empty:
        console.print("[yellow]Nenhum municipio no ranking com os filtros atuais.[/]")
        return
    tabela = Table(title=f"Top 15 — modelo {ranking['versao_modelo'].iloc[0]}")
    colunas = (
        "#", "municipio", "UF", "potencial", "faturamento", "lucro",
        "consultas", "score", "pop 40+", "oftalmo", "km ao polo", "oticas", "nota",
    )
    for col in colunas:
        tabela.add_column(col, justify="right" if col not in ("municipio", "UF") else "left")
    for r in ranking.head(15).to_dict("records"):
        def _f(v: Any, casas: int = 0) -> str:
            return "—" if v is None or pd.isna(v) else f"{float(v):.{casas}f}"

        def _reais(v: Any) -> str:
            if v is None or pd.isna(v):
                return "—"
            cor = "green" if float(v) > 0 else "red"
            return f"[{cor}]{float(v):,.0f}[/]".replace(",", ".")

        tabela.add_row(
            str(r["posicao"]),
            str(r["nome"]),
            str(r["uf"]),
            _f(r.get("potencial_pct"), 1) + "%" if r.get("potencial_pct") is not None else "—",
            _reais(r.get("faturamento_estimado")),
            _reais(r.get("lucro_estimado")),
            _f(r.get("consultas_esperadas")),
            _f(r["score_total"], 1),
            _f(r.get("populacao_40mais")),
            _f(r.get("qtd_oftalmologistas")),
            _f(r.get("distancia_km"), 1),
            _f(r.get("qtd_oticas")),
            _f(r.get("oticas_nota_media"), 1),
        )
    console.print(tabela)
    if "lucro_estimado" in ranking.columns:
        lucro = pd.to_numeric(ranking["lucro_estimado"], errors="coerce")
        console.print(
            f"[dim]projecao: {int(lucro.notna().sum())} municipios com projecao · "
            f"{int((lucro > 0).sum())} com lucro estimado positivo · "
            f"valores dependem de config/negocio.yaml[/]"
        )
    if extras.get("canibalizacao"):
        console.print("[yellow]Alerta de canibalizacao (viram um circuito unico, nao dois eventos):[/]")
        for p in extras["canibalizacao"][:8]:
            console.print(f"  · {p['a_nome']} ↔ {p['b_nome']}: {p['distancia_km']} km")


if __name__ == "__main__":
    app()
