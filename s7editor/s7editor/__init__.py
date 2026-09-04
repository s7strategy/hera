"""S7 Editor — edição de criativos em lote com garantia de zero drift.

Três fluxos, um pacote:
  * trocar texto (CTA, headline, preço) em N imagens sem alterar mais nada;
  * mudar o formato (9:16 -> 16:9 e afins) sem distorcer o conteúdo;
  * gerar criativos novos a partir de um conjunto de referências.

Uso típico pela linha de comando::

    ./s7edit trocar-texto inbox/campanha --de "GARANTA O SEU" --para "ÚLTIMAS VAGAS"
"""
from __future__ import annotations

__version__ = "1.0.0"

from .models import (  # noqa: F401
    AspectSpec, BackgroundKind, Box, CreativeAnalysis, CreativeDNA, EditOp,
    Engine, FontSpec, ImageResult, JobManifest, OpKind, TextBlock, TextRole,
    color_to_hex, parse_color,
)

__all__ = [
    "__version__",
    "AspectSpec", "BackgroundKind", "Box", "CreativeAnalysis", "CreativeDNA",
    "EditOp", "Engine", "FontSpec", "ImageResult", "JobManifest", "OpKind",
    "TextBlock", "TextRole", "color_to_hex", "parse_color",
]
