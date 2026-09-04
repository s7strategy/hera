"""Funções de apoio da suíte — nada aqui é teste, só leitura de fixture e drift.

Concentrar a conversão "entrada do manifesto -> Box/TextBlock" num lugar só
evita que cada teste invente a sua e acabe medindo drift contra a caixa errada.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
from PIL import Image

from s7editor import protect
from s7editor.models import Box, FontSpec, TextBlock, TextRole

__all__ = [
    "arr", "block_entry", "box_of", "text_block_of", "path_of",
    "assert_sem_drift", "region_std", "changed_bbox", "contido_em",
]


def arr(img: Image.Image | np.ndarray) -> np.ndarray:
    """Imagem como ``np.uint8`` RGB — a forma em que drift se mede."""
    if isinstance(img, np.ndarray):
        return img
    return np.asarray(img.convert("RGB") if img.mode != "RGB" else img)


def path_of(base: Path, entry: dict[str, Any]) -> Path:
    return base / entry["relpath"]


def block_entry(entry: dict[str, Any], role: str = "cta") -> dict[str, Any]:
    """A entrada bruta do bloco com aquele papel (levanta se não existir)."""
    for b in entry["blocks"]:
        if b["role"] == role:
            return b
    raise KeyError(f"o fixture {entry['file']} não tem bloco '{role}'")


def box_of(entry: dict[str, Any], role: str = "cta") -> Box:
    return Box(**block_entry(entry, role)["box"])


def text_block_of(entry: dict[str, Any], role: str = "cta") -> TextBlock:
    """:class:`TextBlock` fiel ao que o gerador desenhou — inclusive o estilo.

    É o equivalente ao que ``vision.analyze_creative`` devolveria, só que sem
    depender de IA: o fixture já sabe a verdade.
    """
    b = block_entry(entry, role)
    try:
        papel = TextRole(b["role"])
    except ValueError:
        papel = TextRole.OTHER
    style = FontSpec(
        family="DejaVuSans",
        weight=b.get("weight", "bold"),
        size_px=int(b.get("size_px") or 48),
        color=tuple(b["color"]),
        align=b.get("align", "center"),
        uppercase=str(b.get("text", "")).isupper(),
    )
    bg = b.get("background_color")
    return TextBlock(
        box=Box(**b["box"]),
        text=b["text"],
        role=papel,
        style=style,
        background_color=tuple(bg) if bg else None,
        on_solid_background=bool(b.get("on_solid_background")),
        confidence=1.0,
    )


def changed_bbox(antes: Image.Image | np.ndarray, depois: Image.Image | np.ndarray) -> Box | None:
    """Bounding box dos pixels que mudaram entre duas imagens do mesmo tamanho."""
    a, b = arr(antes), arr(depois)
    assert a.shape == b.shape, "as imagens têm tamanhos diferentes"
    diff = np.any(a != b, axis=2)
    if not diff.any():
        return None
    ys, xs = np.nonzero(diff)
    return Box(int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))


def contido_em(interna: Box, externa: Box, folga: int = 0) -> bool:
    """``interna`` cabe dentro de ``externa`` (com ``folga`` px de tolerância)?"""
    return (interna.x >= externa.x - folga and interna.y >= externa.y - folga
            and interna.x1 <= externa.x1 + folga and interna.y1 <= externa.y1 + folga)


def assert_sem_drift(original: Image.Image | np.ndarray, resultado: Image.Image | np.ndarray,
                     caixas: Iterable[Any], *, contexto: str = "") -> None:
    """Falha com diagnóstico se QUALQUER pixel mudou fora de ``caixas``."""
    lista = list(caixas)
    detalhe = protect.drift_details(original, resultado, lista)
    if detalhe["drift_pixels"]:
        raise AssertionError(
            f"{contexto or 'operação'}: {detalhe['drift_pixels']} pixel(s) mudaram FORA das "
            f"caixas {[b.to_dict() if isinstance(b, Box) else b for b in lista]}; "
            f"maior mancha em {detalhe['drift_bbox']}, delta máximo {detalhe['max_delta_outside']}, "
            f"amostra {detalhe['sample'][:3]}"
        )


def region_std(img: Image.Image | np.ndarray, box: Box) -> float:
    """Desvio padrão máximo por canal dentro da caixa.

    Serve para dizer "o texto sumiu": uma faixa chapada com texto tem desvio
    alto; depois de apagar, o desvio cai para o nível do ruído do fundo.
    """
    a = arr(img)[box.y:box.y1, box.x:box.x1]
    return float(a.reshape(-1, a.shape[-1]).std(axis=0).max())


def media_rgb(img: Image.Image | np.ndarray, box: Box) -> np.ndarray:
    a = arr(img)[box.y:box.y1, box.x:box.x1].reshape(-1, 3).astype(np.float64)
    return a.mean(axis=0)


def erro_medio(a: Image.Image | np.ndarray, b: Image.Image | np.ndarray,
               box: Box | None = None) -> float:
    """Erro absoluto médio por canal entre duas imagens (opcionalmente só na caixa)."""
    x, y = arr(a).astype(np.int32), arr(b).astype(np.int32)
    if box is not None:
        x = x[box.y:box.y1, box.x:box.x1]
        y = y[box.y:box.y1, box.x:box.x1]
    return float(np.abs(x - y).mean())


def sequencia_de_caixas(boxes: Sequence[Box]) -> list[dict[str, int]]:
    return [b.to_dict() for b in boxes]
