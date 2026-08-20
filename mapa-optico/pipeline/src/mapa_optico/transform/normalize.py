"""Normalizacoes que evitam os erros silenciosos do briefing.

O maior deles: CNES usa codigo IBGE de 6 digitos (sem digito verificador) e o
IBGE usa 7. Um join direto nao da erro — ele so devolve zero linha, e o
municipio some do ranking sem ninguem perceber. Tudo aqui converge para 7.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

_SO_DIGITOS = re.compile(r"\D+")


def digito_verificador_ibge(codigo6: str) -> str:
    """Calcula o 7o digito do codigo de municipio a partir dos 6 primeiros.

    Pesos 1,2,1,2,1,2; soma dos digitos de cada produto; DV = (10 - soma % 10) % 10.
    Confere com os casos oficiais (Florianopolis 420540 -> 4205407,
    Joinville 420910 -> 4209102, Sao Paulo 355030 -> 3550308).
    """
    if len(codigo6) != 6 or not codigo6.isdigit():
        raise ValueError(f"codigo de 6 digitos invalido: {codigo6!r}")
    soma = 0
    for i, ch in enumerate(codigo6):
        produto = int(ch) * (1 if i % 2 == 0 else 2)
        soma += produto // 10 + produto % 10
    return str((10 - soma % 10) % 10)


def para_codigo7(valor: object) -> str | None:
    """Aceita 6 ou 7 digitos (int, str, com pontuacao) e devolve sempre 7 digitos.

    Devolve None quando o valor nao e um codigo de municipio — nunca chuta.
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    bruto = _SO_DIGITOS.sub("", str(valor).strip())
    if not bruto:
        return None
    if len(bruto) == 7:
        return bruto
    if len(bruto) == 6:
        return bruto + digito_verificador_ibge(bruto)
    return None


def para_codigo6(valor: object) -> str | None:
    """Trunca para 6 digitos (formato do CNES)."""
    c7 = para_codigo7(valor)
    return c7[:6] if c7 else None


def normalizar_coluna_codigo(df: pd.DataFrame, coluna: str, destino: str = "codigo_ibge") -> pd.DataFrame:
    df = df.copy()
    df[destino] = df[coluna].map(para_codigo7)
    return df


def slug_nome(nome: str) -> str:
    """Nome de municipio comparavel: sem acento, minusculo, sem pontuacao.

    Usado so como ultimo recurso de conferencia — o join oficial e por codigo.
    """
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()


def deduplicar_profissionais(
    df: pd.DataFrame,
    *,
    coluna_id: str = "id_profissional",
    coluna_municipio: str = "codigo_ibge",
    coluna_horas: str | None = "horas_ambulatorial",
) -> pd.DataFrame:
    """Um medico com vinculo em varios estabelecimentos conta uma vez por municipio.

    Contamos profissionais unicos, nao vinculos. A carga horaria dos vinculos do
    mesmo profissional no mesmo municipio e somada (e teto de 60h/semana, para
    que cadastro duplicado nao vire um oftalmo de 200h).
    """
    if df.empty:
        return df.assign(**{coluna_id: [], coluna_municipio: []}).iloc[0:0]
    trabalho = df.dropna(subset=[coluna_id, coluna_municipio]).copy()
    trabalho[coluna_id] = trabalho[coluna_id].astype(str).str.strip()
    if coluna_horas and coluna_horas in trabalho.columns:
        horas = (
            trabalho.groupby([coluna_municipio, coluna_id])[coluna_horas]
            .sum()
            .clip(upper=60)
            .reset_index()
        )
        return horas
    unicos = trabalho[[coluna_municipio, coluna_id]].drop_duplicates()
    return unicos


def validar_join(
    esquerda: pd.DataFrame,
    direita: pd.DataFrame,
    chave: str = "codigo_ibge",
    nome: str = "join",
) -> list[str]:
    """Devolve os codigos orfaos (existem na direita e nao na esquerda).

    O pipeline usa isso para falhar alto quando o join de codigos quebra.
    """
    validos = set(esquerda[chave].dropna().astype(str))
    orfaos = sorted({str(c) for c in direita[chave].dropna().astype(str)} - validos)
    return orfaos
