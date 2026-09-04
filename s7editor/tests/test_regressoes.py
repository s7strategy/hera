"""Regressões dos bugs encontrados na integração ponta a ponta.

Cada teste aqui existe porque a coisa realmente quebrou uma vez.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from s7editor import ocr, vision
from s7editor.models import AspectSpec, Box, TextRole


# --------------------------------------------------------------------------- #
# Reenquadramento: o tamanho tem que sair da origem
# --------------------------------------------------------------------------- #
def test_reframe_deriva_tamanho_da_origem(fixtures_dir, settings_offline, tmp_path):
    """9:16 -> 16:9 num 1080x1920 tem que dar 1920x1080, não 1440x810.

    O pipeline resolvia o alvo com um `long_edge` fixo de 1440 e atropelava a
    derivação por origem que o reframe já fazia, encolhendo o lote inteiro.
    """
    from s7editor import pipeline

    paths = sorted(fixtures_dir.glob("criativo-0[1-2].png"))
    assert paths, "fixtures não geradas"
    m = pipeline.run_reframe_batch(paths, "16:9", settings_offline,
                                   tmp_path / "wide", mode="pad")
    assert m.ok_count == len(paths)
    for r in m.results:
        assert Image.open(r.output).size == (1920, 1080)


def test_reframe_respeita_tamanho_explicito(fixtures_dir, settings_offline, tmp_path):
    """Quando o usuário PEDE um tamanho, ele manda — a derivação não atropela."""
    from s7editor import pipeline

    paths = sorted(fixtures_dir.glob("criativo-01.png"))
    m = pipeline.run_reframe_batch(paths, "1280x720", settings_offline,
                                   tmp_path / "hd", mode="pad")
    assert Image.open(m.results[0].output).size == (1280, 720)


# --------------------------------------------------------------------------- #
# Agrupamento de linha
# --------------------------------------------------------------------------- #
def test_cta_com_espacos_largos_vira_um_bloco_so(fixtures_dir):
    """"GARANTA O SEU" voltava partido em "GARANTA" + "SEU".

    O limiar de espaço entre palavras era 1.1x a altura da caixa, e a altura da
    caixa é a de caixa alta — menor que o corpo da fonte. Com um glifo fino
    perdido na detecção, o buraco estourava o limite e a troca de texto pegava
    só metade do CTA.
    """
    a = vision.heuristic_analysis(fixtures_dir / "criativo-01.png")
    ctas = [b for b in a.text_blocks if b.role is TextRole.CTA]
    assert len(ctas) == 1, f"CTA veio partido em {len(ctas)} blocos"
    # A caixa tem que cobrir a linha inteira, não uma palavra.
    assert ctas[0].box.w > 400


# --------------------------------------------------------------------------- #
# OCR offline
# --------------------------------------------------------------------------- #
requer_ocr = pytest.mark.skipif(not ocr.ocr_available(),
                                reason="Tesseract não instalado nesta máquina")


@requer_ocr
def test_ocr_le_cta_e_preco_do_mesmo_criativo(fixtures_dir):
    """Uma peça mistura texto claro sobre faixa rosa e escuro sobre selo amarelo.

    Uma binarização global lia um e perdia o outro; por isso a leitura é feita
    bloco a bloco, com a polaridade decidida por bloco.
    """
    a = vision.heuristic_analysis(fixtures_dir / "criativo-01.png")
    cta = a.block_by_role(TextRole.CTA)
    preco = a.block_by_role(TextRole.PRICE)
    assert cta is not None and "GARANTA O SEU" in cta.text.upper()
    assert preco is not None and "97" in preco.text


@requer_ocr
def test_selo_de_preco_nao_e_confundido_com_cta(fixtures_dir):
    """Sem ler o texto, um selo amarelo e uma faixa rosa são o mesmo padrão.

    O primeiro `--papel cta` trocava o preço em vez do CTA.
    """
    a = vision.heuristic_analysis(fixtures_dir / "criativo-01.png")
    cta = a.block_by_role(TextRole.CTA)
    assert cta is not None
    assert "R$" not in cta.text, "o bloco de preço foi eleito CTA"


@requer_ocr
def test_ordem_de_leitura_em_bloco_multilinha(fixtures_dir):
    """Agrupar por faixa fixa embaralhava as palavras entre linhas."""
    a = vision.heuristic_analysis(fixtures_dir / "criativo-01.png")
    sub = a.block_by_role(TextRole.SUBHEAD)
    if sub is None or not sub.text:
        pytest.skip("subhead não detectada nesta fixture")
    assert "em lote" in sub.text.lower()


def test_binarize_normaliza_polaridade():
    """Texto claro sobre escuro e escuro sobre claro saem os dois com texto preto."""
    claro_sobre_escuro = np.full((40, 120, 3), 20, dtype=np.uint8)
    claro_sobre_escuro[10:30, 10:110] = 240
    escuro_sobre_claro = np.full((40, 120, 3), 240, dtype=np.uint8)
    escuro_sobre_claro[10:30, 10:110] = 20
    for arr in (claro_sobre_escuro, escuro_sobre_claro):
        bw = ocr._binarize(arr)
        # A minoria (o "texto") tem que ficar preta nos dois casos.
        assert int((bw == 0).sum()) < int((bw == 255).sum())


def test_fuzzy_equal_tolera_acento_caixa_e_erro_de_ocr():
    assert ocr.fuzzy_equal("garanta o seu", "GARANTA O SEU!")
    assert ocr.fuzzy_equal("GARANTA 0 SEU", "garanta o seu")   # zero por O
    assert ocr.fuzzy_equal("últimas vagas", "ULTIMAS VAGAS")
    assert not ocr.fuzzy_equal("garanta o seu", "compre agora")


# --------------------------------------------------------------------------- #
# Honestidade do relatório
# --------------------------------------------------------------------------- #
def test_lote_sem_nenhuma_troca_nao_e_sucesso(fixtures_dir, settings_offline, tmp_path):
    """Pedir a troca de um texto que não existe não pode sair como "30 de 30 pronto".

    Antes, o lote copiava as imagens, registrava o aviso no manifesto e imprimia
    sucesso com selo de zero drift — que era verdade e não queria dizer nada.
    """
    from s7editor import pipeline

    paths = sorted(fixtures_dir.glob("criativo-0[1-3].png"))
    m = pipeline.run_replace_text_batch(
        paths, "TEXTO QUE NAO EXISTE EM LUGAR NENHUM", "OUTRO",
        settings_offline, tmp_path / "vazio")
    sem_op = [r for r in m.results if r.ok and not r.skipped and not r.operations]
    assert len(sem_op) == len(paths), "as imagens deveriam sair sem nenhuma operação"
    for r in sem_op:
        assert r.warnings, "sem operação e sem aviso é o pior dos mundos"


def test_troca_por_texto_altera_de_verdade(fixtures_dir, settings_offline, tmp_path):
    """O caminho principal do produto, ponta a ponta e offline."""
    if not ocr.ocr_available():
        pytest.skip("casar por texto sem chave exige Tesseract")
    from s7editor import pipeline

    paths = sorted(fixtures_dir.glob("criativo-0[1-3].png"))
    m = pipeline.run_replace_text_batch(paths, "GARANTA O SEU", "ÚLTIMAS VAGAS",
                                        settings_offline, tmp_path / "cta")
    assert m.ok_count == len(paths)
    for r in m.results:
        assert r.operations, f"{r.source} saiu sem nenhuma operação"
        antes = np.array(Image.open(r.source).convert("RGB"), dtype=np.int16)
        depois = np.array(Image.open(r.output).convert("RGB"), dtype=np.int16)
        dif = np.abs(antes - depois).max(axis=2) > 0
        assert dif.any(), "a imagem saiu idêntica"
        for b in r.changed_boxes:
            dif[b.y:b.y1, b.x:b.x1] = False
        assert int(dif.sum()) == 0, "mudou pixel fora da caixa declarada"
