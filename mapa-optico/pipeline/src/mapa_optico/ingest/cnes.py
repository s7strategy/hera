"""CNES: quantos oftalmologistas cada municipio tem, de verdade.

Este e o modulo de maior risco do projeto (Fase 0 do briefing). Quatro
caminhos, tentados nesta ordem, e o pipeline registra qual foi usado:

  1. `.dbc` do DATASUS — o arquivo PF por UF, ~5 MB. Rapido, mas o .DBC e um
     DBF comprimido com algoritmo proprietario: precisa de um decodificador
     nativo, e wheel nativa e coisa que falta em runner as vezes.
  2. Base completa em CSV — o ZIP mensal `BASE_DE_DADOS_CNES_AAAAMM`, que traz
     os mesmos vinculos em CSV puro. Pesa centenas de MB e por isso vem depois,
     mas nao depende de dependencia compilada nenhuma: se o disco e a rede
     aguentam, ele funciona.
  3. `pysus` — biblioteca que embrulha o passo 1. A API dela ja mudou de nome
     tres vezes, entao aqui ela e conveniencia, nao alicerce.
  4. CSV manual — a extracao baixada a mao do portal do CNES, em data/manual/.

Armadilhas tratadas aqui, todas citadas no briefing:
  - codigo de municipio de 6 digitos do CNES vira 7 (transform.normalize)
  - um medico com varios vinculos conta UMA vez por municipio
  - carga horaria ambulatorial vira "oftalmologista equivalente" (40h = 1,0)
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from ..http import FonteIndisponivel, cliente
from ..logs import aviso, etapa, log
from ..settings import CACHE_DIR, DATA_DIR
from ..transform.normalize import CODIGO_POR_UF, deduplicar_profissionais, para_codigo7
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



# O DATASUS serve o mesmo FTP por HTTPS. Nomes conferidos contra o layout de
# disseminacao publica; a competencia entra como AAMM (dois digitos de ano).
URL_DBC = "https://ftp.datasus.gov.br/dissemin/publicos/CNES/200801_/Dados/PF/PF{uf}{aamm}.dbc"
URL_BASE_ZIP = "https://ftp.datasus.gov.br/cnes/BASE_DE_DADOS_CNES_{competencia}.ZIP"
# Quantas competencias voltar procurando a ultima publicada. O CNES publica com
# um a dois meses de atraso, e as vezes atrasa mais.
COMPETENCIAS_PARA_TENTAR = 6


def _competencias_candidatas(competencia: str | None) -> list[tuple[int, int]]:
    """Da competencia pedida (ou de hoje) para tras, mes a mes."""
    if competencia:
        return [(int(competencia[:4]), int(competencia[4:6]))]
    hoje = pd.Timestamp.utcnow()
    return [
        ((hoje - pd.DateOffset(months=n)).year, (hoje - pd.DateOffset(months=n)).month)
        for n in range(1, COMPETENCIAS_PARA_TENTAR + 1)
    ]


def _baixar(url: str, destino: Path) -> Path:
    """Baixa em streaming: estes arquivos nao cabem confortavelmente em memoria."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and destino.stat().st_size > 0:
        log("arquivo ja em cache", arquivo=destino.name, bytes=destino.stat().st_size)
        return destino
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    with cliente().stream("GET", url, timeout=600.0) as resp:
        if resp.status_code != 200:
            raise FonteIndisponivel(FONTE, f"HTTP {resp.status_code} em {url}")
        with parcial.open("wb") as saida:
            for bloco in resp.iter_bytes(chunk_size=1 << 20):
                saida.write(bloco)
    parcial.rename(destino)
    log("arquivo baixado", arquivo=destino.name, bytes=destino.stat().st_size, url=url)
    return destino


def _decodificar_dbc(origem: Path) -> pd.DataFrame:
    """DBC -> DataFrame. Tenta os decodificadores conhecidos, na ordem."""
    destino = origem.with_suffix(".dbf")
    erros: list[str] = []

    if not destino.exists():
        for nome, fn in (
            ("datasus_dbc", lambda: __import__("datasus_dbc").decompress(str(origem), str(destino))),
            ("pyreaddbc", lambda: __import__("pyreaddbc").dbc2dbf(str(origem), str(destino))),
            (
                "pysus.utilities",
                lambda: __import__(
                    "pysus.utilities.readdbc", fromlist=["dbc2dbf"]
                ).dbc2dbf(str(origem), str(destino)),
            ),
        ):
            try:
                fn()
                log("dbc decodificado", decodificador=nome, arquivo=origem.name)
                break
            except Exception as exc:  # noqa: BLE001 - qualquer falha e "tenta o proximo"
                erros.append(f"{nome}: {type(exc).__name__}: {exc}")
        else:
            raise CnesIndisponivel("nenhum decodificador de .dbc funcionou:\n  - " + "\n  - ".join(erros))

    try:
        from dbfread import DBF  # type: ignore
    except ImportError as exc:
        raise CnesIndisponivel("dbfread nao instalado; sem ele o .dbf nao vira tabela") from exc
    return pd.DataFrame(iter(DBF(str(destino), encoding="latin-1", load=False)))


def _via_dbc(uf: str, competencia: str | None) -> tuple[pd.DataFrame, str, str]:
    """Arquivo PF por UF: o caminho mais barato quando o decodificador existe."""
    erros: list[str] = []
    for ano, mes in _competencias_candidatas(competencia):
        aamm = f"{ano % 100:02d}{mes:02d}"
        url = URL_DBC.format(uf=uf.upper(), aamm=aamm)
        try:
            arquivo = _baixar(url, CACHE_DIR / "cnes" / f"PF{uf.upper()}{aamm}.dbc")
        except FonteIndisponivel as exc:
            erros.append(str(exc))
            continue
        df = _decodificar_dbc(arquivo)
        if len(df):
            return df, f"{ano}{mes:02d}", f"dbc:PF{uf.upper()}{aamm}"
        erros.append(f"PF{uf.upper()}{aamm}: arquivo vazio")
    raise CnesIndisponivel("nenhuma competencia .dbc respondeu:\n  - " + "\n  - ".join(erros[:6]))


def _via_base_csv(uf: str, competencia: str | None) -> tuple[pd.DataFrame, str, str]:
    """Base mensal completa em CSV.

    Pesa centenas de MB e por isso nao e o primeiro caminho — mas nao depende de
    dependencia compilada nenhuma, o que faz dele o que sobra quando o resto
    falha. Junta carga horaria (vinculo) com estabelecimento (municipio).
    """
    erros: list[str] = []
    prefixo_uf = CODIGO_POR_UF.get(uf.upper())
    for ano, mes in _competencias_candidatas(competencia):
        comp = f"{ano}{mes:02d}"
        try:
            arquivo = _baixar(URL_BASE_ZIP.format(competencia=comp), CACHE_DIR / "cnes" / f"CNES{comp}.zip")
        except FonteIndisponivel as exc:
            erros.append(str(exc))
            continue
        try:
            with zipfile.ZipFile(arquivo) as z:
                nomes = z.namelist()
                carga = _achar(nomes, "tbCargaHorariaSus")
                estab = _achar(nomes, "tbEstabelecimento")
                if not (carga and estab):
                    erros.append(f"{comp}: ZIP sem tbCargaHorariaSus/tbEstabelecimento ({nomes[:5]})")
                    continue
                with z.open(carga) as f:
                    vinculos = pd.read_csv(f, sep=";", dtype=str, encoding="latin-1", low_memory=False)
                with z.open(estab) as f:
                    unidades = pd.read_csv(
                        f, sep=";", dtype=str, encoding="latin-1", low_memory=False,
                        usecols=lambda c: c.strip().upper() in {"CO_UNIDADE", "CO_MUNICIPIO_GESTOR"},
                    )
        except (zipfile.BadZipFile, ValueError) as exc:
            erros.append(f"{comp}: {type(exc).__name__}: {exc}")
            continue

        vinculos.columns = [c.strip() for c in vinculos.columns]
        unidades.columns = [c.strip() for c in unidades.columns]
        df = vinculos.merge(unidades, on="CO_UNIDADE", how="left")
        if prefixo_uf:
            # A base e do Brasil inteiro; corta pela UF antes de qualquer conta.
            df = df[df["CO_MUNICIPIO_GESTOR"].astype(str).str.startswith(prefixo_uf)]
        log("CNES lido da base completa", competencia=comp, linhas=len(df))
        return df, comp, f"base_csv:{comp}"
    raise CnesIndisponivel("base completa do CNES indisponivel:\n  - " + "\n  - ".join(erros[:6]))


def _achar(nomes: list[str], prefixo: str) -> str | None:
    alvo = prefixo.lower()
    for n in nomes:
        if n.rsplit("/", 1)[-1].lower().startswith(alvo):
            return n
    return None


def _via_pysus(uf: str, competencia: str | None, refresh: bool) -> tuple[pd.DataFrame, str, str]:
    ano, mes = _competencia_partes(competencia)
    log("baixando CNES via pysus", uf=uf, ano=ano, mes=mes)
    # A API do pysus ja se chamou `online_data.CNES` e hoje se chama
    # `ftp.databases.cnes`. Tentar as duas custa nada e evita que a biblioteca
    # trocar de nome derrube a Fase 0 de novo.
    erros: list[str] = []
    for rotulo, baixar in (
        ("ftp.databases.cnes", lambda: _pysus_ftp(uf, ano, mes)),
        ("online_data.CNES", lambda: _pysus_legado(uf, ano, mes)),
    ):
        try:
            df = baixar()
        except Exception as exc:  # noqa: BLE001 - cada API falha de um jeito
            erros.append(f"{rotulo}: {type(exc).__name__}: {exc}")
            continue
        if df is not None and len(df):
            return df, f"{ano}{mes:02d}", f"pysus:{rotulo}"
        erros.append(f"{rotulo}: base vazia")
    raise CnesIndisponivel("pysus nao entregou dados:\n  - " + "\n  - ".join(erros))


def _pysus_ftp(uf: str, ano: int, mes: int) -> pd.DataFrame:
    from pysus.ftp.databases.cnes import CNES  # type: ignore

    cnes = CNES().load()
    arquivos = cnes.get_files("PF", uf=uf, year=ano, month=mes)
    if not arquivos:
        return pd.DataFrame()
    from pysus.ftp import CACHEPATH  # type: ignore

    return cnes.download(arquivos, local_dir=str(CACHEPATH)).to_dataframe()


def _pysus_legado(uf: str, ano: int, mes: int) -> pd.DataFrame:
    from pysus.online_data import CNES  # type: ignore

    arquivos = CNES.download(["PF"], [uf], [ano], [mes])  # type: ignore[attr-defined]
    return arquivos.to_dataframe() if hasattr(arquivos, "to_dataframe") else pd.DataFrame(arquivos)


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
        "dbc": lambda: _via_dbc(uf, competencia),
        "base_csv": lambda: _via_base_csv(uf, competencia),
        "pysus": lambda: _via_pysus(uf, competencia, refresh),
        "csv": lambda: _via_csv_manual(uf, competencia),
    }
    # Do mais barato para o mais pesado, e a dependencia compilada por ultimo.
    ordem = [caminho_preferido] if caminho_preferido else ["dbc", "base_csv", "pysus", "csv"]
    erros: list[str] = []

    with etapa(f"ingest.cnes.{uf}") as c:
        for nome in ordem:
            if nome not in caminhos:
                erros.append(f"{nome}: caminho desconhecido")
                continue
            try:
                bruto, comp, origem = caminhos[nome]()
            except (CnesIndisponivel, FonteIndisponivel) as exc:
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
