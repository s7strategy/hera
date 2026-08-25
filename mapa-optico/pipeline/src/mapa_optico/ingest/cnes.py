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

import ftplib
import re
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx
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
#
# O 443 desse host NAO responde: doze tentativas de HTTPS deram ConnectTimeout
# no runner do GitHub. O servico vive no 80 e no 21. Por isso cada arquivo tem
# uma lista de transportes, tentados em ordem, e nao uma URL unica.
DIR_DBC = "/dissemin/publicos/CNES/200801_/Dados/PF"
DIR_BASE_ZIP = "/cnes"
HOST_DATASUS = "ftp.datasus.gov.br"
TRANSPORTES = ("ftp", "http", "https")
# Transferir a base completa leva minutos; o socket nao pode desistir no meio.
TIMEOUT_FTP_S = 900
# Generoso porque a base completa passa de 200 MB, mas nao infinito: uma
# competencia que nao existe nao pode segurar o pipeline por meia hora.
_TIMEOUT_DOWNLOAD = httpx.Timeout(connect=15.0, read=120.0, write=60.0, pool=15.0)
# Quantas competencias voltar procurando a ultima publicada. O CNES publica com
# um a dois meses de atraso, e as vezes atrasa mais.
COMPETENCIAS_PARA_TENTAR = 6


def _listar(diretorio: str) -> list[str]:
    """Nomes de arquivo do diretorio, via FTP.

    Adivinhar o nome do arquivo custou seis competencias x tres transportes de
    tentativa para descobrir que a convencao era outra. Listar responde de uma
    vez, e continua respondendo quando o DATASUS mudar o padrao de nome.
    """
    ftp = _conectar_ftp()
    try:
        return [n.rsplit("/", 1)[-1] for n in ftp.nlst(diretorio)]
    finally:
        _fechar(ftp)


def _mais_recente(nomes: list[str], padrao: re.Pattern[str]) -> tuple[str, str] | None:
    """(nome, competencia) do arquivo mais novo que casa com o padrao."""
    casados = [(m.group("comp"), n) for n in nomes if (m := padrao.match(n))]
    if not casados:
        return None
    comp, nome = max(casados)
    return nome, comp


class HostInalcancavel(FonteIndisponivel):
    """O host nao atendeu — distinto de "o arquivo nao existe".

    A diferenca importa: arquivo ausente significa tentar a competencia
    anterior; host mudo significa desistir do caminho inteiro agora, em vez de
    gastar seis timeouts de conexao para descobrir a mesma coisa seis vezes.
    """


def _baixar(caminho: str, destino: Path) -> Path:
    """Baixa `caminho` do DATASUS tentando cada transporte, em streaming.

    Streaming porque a base completa passa de 200 MB e nao cabe
    confortavelmente na memoria do runner.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and destino.stat().st_size > 0:
        log("arquivo ja em cache", arquivo=destino.name, bytes=destino.stat().st_size)
        return destino

    erros: list[str] = []
    ausente = False
    for transporte in TRANSPORTES:
        parcial = destino.with_suffix(destino.suffix + ".parcial")
        try:
            if transporte == "ftp":
                _baixar_ftp(caminho, parcial, destino.name)
            else:
                _baixar_http(f"{transporte}://{HOST_DATASUS}{caminho}", parcial, destino.name)
        except FileNotFoundError as exc:
            # O host atendeu e disse que o arquivo nao existe. Trocar de
            # transporte nao muda isso; trocar de competencia muda.
            parcial.unlink(missing_ok=True)
            ausente = True
            erros.append(f"{transporte}: {exc}")
            continue
        except (OSError, httpx.HTTPError) as exc:
            parcial.unlink(missing_ok=True)
            erros.append(f"{transporte}: {type(exc).__name__}: {exc}")
            continue
        parcial.rename(destino)
        log("arquivo baixado", arquivo=destino.name, bytes=destino.stat().st_size, via=transporte)
        return destino

    detalhe = f"{caminho} nao veio por nenhum transporte:\n  - " + "\n  - ".join(erros)
    raise FonteIndisponivel(FONTE, detalhe) if ausente else HostInalcancavel(FONTE, detalhe)


def _baixar_http(url: str, parcial: Path, nome: str) -> None:
    with cliente().stream("GET", url, timeout=_TIMEOUT_DOWNLOAD) as resp:
        if resp.status_code == 404:
            raise FileNotFoundError(f"HTTP 404 em {url}")
        if resp.status_code != 200:
            raise httpx.HTTPError(f"HTTP {resp.status_code} em {url}")
        total = int(resp.headers.get("content-length") or 0)
        baixado = proximo_aviso = 0
        with parcial.open("wb") as saida:
            for bloco in resp.iter_bytes(chunk_size=1 << 20):
                saida.write(bloco)
                baixado += len(bloco)
                # Sem isto um download de centenas de MB fica minutos mudo no
                # log e nao da para distinguir travado de lento.
                if baixado >= proximo_aviso:
                    log("baixando", arquivo=nome, mb=baixado >> 20, total_mb=total >> 20)
                    proximo_aviso = baixado + (64 << 20)


def _conectar_ftp() -> ftplib.FTP:
    """FTP anonimo — o unico transporte que este servidor realmente atende.

    O 443 nao responde e o 80 tambem nao; so a 21. Servidor publico do
    Ministerio da Saude, sem credencial e sem dado sensivel.
    """
    ftp = ftplib.FTP(HOST_DATASUS, timeout=TIMEOUT_FTP_S)
    ftp.login()
    ftp.set_pasv(True)
    return ftp


def _fechar(ftp: ftplib.FTP) -> None:
    try:
        ftp.quit()
    except Exception:  # noqa: BLE001 - fechar conexao nao pode mascarar o erro real
        ftp.close()


def _baixar_ftp(caminho: str, parcial: Path, nome: str) -> None:
    ftp = _conectar_ftp()
    baixado = proximo_aviso = 0

    def escrever(bloco: bytes, saida) -> None:
        nonlocal baixado, proximo_aviso
        saida.write(bloco)
        baixado += len(bloco)
        if baixado >= proximo_aviso:
            log("baixando", arquivo=nome, mb=baixado >> 20, via="ftp")
            proximo_aviso = baixado + (64 << 20)

    try:
        with parcial.open("wb") as saida:
            ftp.retrbinary(f"RETR {caminho}", lambda b: escrever(b, saida), blocksize=1 << 20)
    except ftplib.error_perm as exc:
        # 550 e "arquivo nao existe"; o resto e problema de servidor.
        if str(exc).startswith("550"):
            raise FileNotFoundError(f"FTP 550 em {caminho}") from exc
        raise OSError(str(exc)) from exc
    finally:
        _fechar(ftp)


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
    padrao = re.compile(rf"^PF{uf.upper()}(?P<comp>\d{{4}})\.dbc$", re.IGNORECASE)
    nomes = _listar(DIR_DBC)
    if competencia:
        alvo = f"PF{uf.upper()}{competencia[2:6]}.dbc"
        escolha = (alvo, competencia[2:6]) if alvo in nomes else None
    else:
        escolha = _mais_recente(nomes, padrao)
    if not escolha:
        raise CnesIndisponivel(
            f"nenhum PF{uf.upper()}AAMM.dbc em {DIR_DBC} ({len(nomes)} arquivos listados)"
        )
    nome, comp = escolha
    arquivo = _baixar(f"{DIR_DBC}/{nome}", CACHE_DIR / "cnes" / nome)
    df = _decodificar_dbc(arquivo)
    if not len(df):
        raise CnesIndisponivel(f"{nome} veio vazio")
    # AAMM -> AAAAMM. O CNES so publica de 2008 em diante, entao 20xx resolve.
    return df, f"20{comp[:2]}{comp[2:]}", f"dbc:{nome}"


def _via_base_csv(uf: str, competencia: str | None) -> tuple[pd.DataFrame, str, str]:
    """Base mensal completa em CSV.

    Pesa centenas de MB e por isso nao e o primeiro caminho — mas nao depende de
    dependencia compilada nenhuma, o que faz dele o que sobra quando o resto
    falha. Junta carga horaria (o vinculo) com estabelecimento (o municipio).
    """
    cfg = carregar()["cnes"]
    cbos = {str(c).strip() for c in [*cfg["cbo_oftalmologista"], *(cfg.get("cbo_correlatos") or [])]}
    prefixo_uf = CODIGO_POR_UF.get(uf.upper())

    padrao = re.compile(r"^BASE_DE_DADOS_CNES_(?P<comp>\d{6})\.ZIP$", re.IGNORECASE)
    disponiveis = _listar(DIR_BASE_ZIP)
    if competencia:
        alvo = f"BASE_DE_DADOS_CNES_{competencia}.ZIP"
        escolha = (alvo, competencia) if alvo in disponiveis else None
    else:
        escolha = _mais_recente(disponiveis, padrao)
    if not escolha:
        raise CnesIndisponivel(
            f"nenhum BASE_DE_DADOS_CNES_AAAAMM.ZIP em {DIR_BASE_ZIP} "
            f"({len(disponiveis)} arquivos listados)"
        )

    nome, comp = escolha
    arquivo = _baixar(f"{DIR_BASE_ZIP}/{nome}", CACHE_DIR / "cnes" / nome)
    try:
        with zipfile.ZipFile(arquivo) as z:
            conteudo = z.namelist()
            carga = _achar(conteudo, "tbCargaHorariaSus")
            estab = _achar(conteudo, "tbEstabelecimento")
            if not (carga and estab):
                raise CnesIndisponivel(
                    f"{nome} sem tbCargaHorariaSus/tbEstabelecimento ({conteudo[:5]})"
                )
            with z.open(carga) as f:
                vinculos = _ler_carga_horaria(f, cbos)
            with z.open(estab) as f:
                unidades = pd.read_csv(
                    f, sep=";", dtype=str, encoding="latin-1", low_memory=False,
                    usecols=lambda c: c.strip().upper() in {"CO_UNIDADE", "CO_MUNICIPIO_GESTOR"},
                )
    except zipfile.BadZipFile as exc:
        # Download truncado deixa um ZIP invalido em cache; apagar evita que a
        # proxima execucao repita o erro achando que ja tem o arquivo.
        arquivo.unlink(missing_ok=True)
        raise CnesIndisponivel(f"{nome} nao abriu como ZIP: {exc}") from exc

    if vinculos.empty:
        raise CnesIndisponivel(f"{nome}: nenhum vinculo com CBO de oftalmologista")

    vinculos.columns = [c.strip() for c in vinculos.columns]
    unidades.columns = [c.strip() for c in unidades.columns]
    df = vinculos.merge(unidades, on="CO_UNIDADE", how="left")
    if prefixo_uf:
        # A base e do Brasil inteiro; corta pela UF antes de qualquer conta.
        df = df[df["CO_MUNICIPIO_GESTOR"].astype(str).str.startswith(prefixo_uf)]
    log("CNES lido da base completa", arquivo=nome, competencia=comp, linhas=len(df))
    return df, comp, f"base_csv:{nome}"


def _ler_carga_horaria(arquivo: Any, cbos: set[str]) -> pd.DataFrame:
    """Vinculos de oftalmologista, lidos em blocos.

    A tabela e do Brasil inteiro: dezenas de milhoes de linhas. Ler inteira,
    mesmo so com as colunas uteis, engasga o runner. Filtrando o CBO na entrada
    de cada bloco, o que fica na memoria e so quem interessa.
    """
    pedacos = []
    for bloco in pd.read_csv(
        arquivo, sep=";", dtype=str, encoding="latin-1",
        usecols=lambda c: c.strip().upper() in _COLUNAS_CARGA,
        chunksize=500_000,
    ):
        cbo = (
            bloco[_col(bloco, "CO_CBO")]
            .astype(str).str.strip().str.replace(r"\D", "", regex=True)
        )
        pedacos.append(bloco[cbo.isin(cbos)])
    return pd.concat(pedacos, ignore_index=True) if pedacos else pd.DataFrame()


_COLUNAS_CARGA = {
    "CO_UNIDADE",
    "CO_PROFISSIONAL_SUS",
    "CO_CBO",
    "QT_CARGA_HOR_AMBULATORIAL",
    "QT_CARGA_HORARIA_AMBULATORIAL",
}


def _col(df: pd.DataFrame, nome: str) -> str:
    """Coluna pelo nome, tolerante a espaco e caixa."""
    for c in df.columns:
        if str(c).strip().upper() == nome:
            return str(c)
    raise CnesIndisponivel(f"coluna {nome} ausente; vieram {list(df.columns)[:10]}")


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
