"""Executor do lote: pega a receita, roda nas 30 imagens e prova o que fez.

Este módulo é a única coisa que orquestra. Ele não sabe apagar texto nem falar
com a API — pede isso a ``textedit``, ``inpaint``, ``reframe``, ``variations`` e
``aigen``. O que ele sabe fazer, e ninguém mais faz, é:

1. **Provar a garantia de zero drift.** Depois de aplicar as operações de uma
   imagem, e *antes* de codificar o arquivo, roda :func:`protect.drift_report`
   contra o original usando a união das caixas alteradas. O número vai para
   ``ImageResult.drift_pixels`` / ``untouched_pixels_verified`` e aparece no
   relatório. Se der diferente de zero, o usuário fica sabendo — não escondemos.

2. **Não derrubar o lote por causa de uma imagem.** Cada imagem é um try/except
   isolado: o erro vira ``ImageResult.error`` em português e o lote segue.

3. **Retomar de onde parou.** Refazer 30 gerações de IA porque a nº 17 falhou é
   caro. Se o arquivo de saída existe e nem a imagem de entrada nem a receita
   mudaram, a imagem é pulada (``skipped=True``). ``force=True`` ignora isso.

4. **Escolher o formato de saída com honestidade.** Salvar JPEG re-comprime a
   imagem INTEIRA (item F do projeto técnico): a garantia byte a byte morre em
   ~87% dos pixels. Por isso o master é PNG por padrão; quem exige JPEG recebe
   o arquivo, um aviso claro e ``untouched_pixels_verified=None`` — nunca
   ``True``.

Estado da retomada
------------------
Fica em ``<saída>/.s7editor-state.json``: para cada arquivo entregue, o SHA-256
dos *bytes* da entrada e a assinatura da receita. Mudou qualquer um dos dois, a
imagem é refeita. É de propósito que a assinatura entre: trocar o texto do CTA
na receita e receber os arquivos antigos seria o pior bug possível aqui.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import warnings as _warnings_mod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
from PIL import Image

from . import aigen as _aigen
from . import imageio_util as _io
from . import inpaint as _inpaint
from . import protect as _protect
from . import reframe as _reframe
from . import textedit as _textedit
from . import variations as _variations
from . import vision as _vision
from .config import Settings, load_settings
from .models import (
    AspectSpec, Box, EditOp, Engine, FontSpec, ImageResult, JobManifest,
    OpKind, TextBlock, TextRole, parse_color,
)
from .recipe import Recipe

__all__ = [
    "PipelineError",
    "run_recipe",
    "run_reframe_batch",
    "run_variations_batch",
    "run_replace_text_batch",
    "MANIFEST_FILENAME",
    "STATE_FILENAME",
    "JPEG_TOLERANCE",
]

log = logging.getLogger("s7editor.pipeline")

MANIFEST_FILENAME = "manifest.json"
STATE_FILENAME = ".s7editor-state.json"

#: Delta por canal ignorado quando o entregável é JPEG (item F do projeto).
JPEG_TOLERANCE = 2

#: Formatos que preservam pixel — só neles o drift 0 é verificável no arquivo.
_LOSSLESS_FORMATS = frozenset({"PNG", "TIFF", "BMP"})

#: Operações confinadas a uma caixa: mantêm o tamanho da imagem e por isso
#: podem (e devem) ser provadas com ``drift_report``.
_CONFINED_OPS = frozenset({
    OpKind.REPLACE_TEXT, OpKind.REMOVE_TEXT, OpKind.ADD_TEXT,
    OpKind.REPLACE_COLOR, OpKind.REPLACE_REGION, OpKind.REMOVE_OBJECT,
    OpKind.OVERLAY,
})

#: Operações que mudam a geometria: a comparação byte a byte deixa de existir.
_GEOMETRY_OPS = frozenset({OpKind.REFRAME, OpKind.RESIZE})

#: Operações que precisam saber onde está o texto quando não vem 'box'.
_NEEDS_ANALYSIS = frozenset({OpKind.REPLACE_TEXT, OpKind.REMOVE_TEXT, OpKind.REMOVE_OBJECT})

_AI_ONLY = frozenset({OpKind.REPLACE_REGION})


class PipelineError(RuntimeError):
    """Erro de uso do lote (pasta vazia, receita impossível), já em português."""


# --------------------------------------------------------------------------- #
# Utilidades pequenas
# --------------------------------------------------------------------------- #
def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _tick(progress: Callable[[int, int, str], None] | None,
          i: int, total: int, msg: str) -> None:
    """Chama o callback de progresso sem deixar que ele derrube o lote."""
    if progress is None:
        return
    try:
        progress(int(i), int(total), str(msg))
    except Exception:  # noqa: BLE001 - progresso é enfeite, nunca causa de falha
        log.debug("callback de progresso levantou exceção; ignorado", exc_info=True)


def _file_sha(path: Path) -> str:
    """SHA-256 dos bytes do arquivo.

    Bytes, não pixels: a retomada quer saber se *o arquivo* mudou, e assim não
    precisamos decodificar 30 imagens só para descobrir que nada mudou.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _recipe_signature(recipe: Recipe, settings: Settings) -> str:
    """Impressão digital do que a receita manda fazer.

    Entra tudo que muda o pixel de saída (operações, alvo, modo, formato) e
    fica de fora o que não muda (job, notas, zip/relatório). Assim, editar a
    descrição do lote não obriga a refazer 30 gerações de IA, mas editar o
    texto do CTA obriga.
    """
    payload = {
        "operations": [op.to_dict() for op in recipe.operations if op.enabled],
        "engine": recipe.engine.value,
        "target": recipe.target.label if recipe.target else None,
        "target_size": (list(recipe.target.resolve(recipe.long_edge))
                        if recipe.target and (recipe.long_edge or
                                              (recipe.target.width and recipe.target.height))
                        else (recipe.target.label if recipe.target else None)),
        "reframe_mode": recipe.reframe_mode,
        "reframe_fill": recipe.reframe_fill,
        "reframe_prompt": recipe.reframe_prompt,
        "variations": dict(recipe.variations) if recipe.variations else None,
        "deliver": {k: recipe.deliver.get(k)
                    for k in sorted(recipe.deliver) if k not in ("zip", "report", "contact_sheet")},
        "image_model": settings.image_model,
        "quality": recipe.quality or settings.quality,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _load_state(out_dir: Path) -> dict[str, Any]:
    p = out_dir / STATE_FILENAME
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(out_dir: Path, state: dict[str, Any]) -> None:
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / STATE_FILENAME).write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:  # estado é conveniência: perder não invalida a entrega
        log.debug("não consegui gravar o estado de retomada: %s", exc)


def _as_bool(value: Any, default: bool | None = None) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "y", "on", "sim", "verdadeiro"):
        return True
    if s in ("0", "false", "no", "n", "off", "nao", "não", "falso"):
        return False
    return default


def _deliver_flag(recipe: Recipe, key: str, default: bool | None = None) -> bool | None:
    """Lê uma chave booleana de ``deliver:`` (ou do topo cru da receita)."""
    if key in (recipe.deliver or {}):
        return _as_bool(recipe.deliver.get(key), default)
    raw = recipe.raw or {}
    if isinstance(raw, dict) and key in raw:
        return _as_bool(raw.get(key), default)
    return default


def _fmt_from_suffix(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP",
            "tif": "TIFF", "tiff": "TIFF", "bmp": "BMP"}.get(ext, "PNG")


def _ext_for(fmt: str) -> str:
    return {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp",
            "TIFF": ".tif", "BMP": ".bmp"}.get(fmt.upper(), ".png")


def _is_lossy(fmt: str, quality: int) -> bool:
    fmt = fmt.upper()
    if fmt in _LOSSLESS_FORMATS:
        return False
    if fmt == "WEBP":
        return int(quality) < 95   # imageio_util grava WEBP lossless a partir de 95
    return True


def _clean_boxes(boxes: Sequence[Box], w: int, h: int) -> list[Box]:
    out: list[Box] = []
    for b in boxes:
        if b is None:
            continue
        c = b.clamp(w, h)
        if c.area > 0:
            out.append(c)
    return out


def _changed_bbox(before: np.ndarray, after: np.ndarray) -> Box | None:
    """Bounding box exata dos pixels que mudaram entre dois arrays iguais em forma."""
    if before.shape != after.shape:
        return None
    diff = np.any(before != after, axis=2) if before.ndim == 3 else (before != after)
    if not diff.any():
        return None
    ys = np.flatnonzero(diff.any(axis=1))
    xs = np.flatnonzero(diff.any(axis=0))
    return Box(int(xs[0]), int(ys[0]), int(xs[-1] - xs[0] + 1), int(ys[-1] - ys[0] + 1))


def _rgb(img: Image.Image) -> np.ndarray:
    """Array (H,W,3) para medir diferença — RGBA entra sem o alfa."""
    if img.mode == "RGB":
        return np.asarray(img)
    if img.mode == "RGBA":
        return np.asarray(img)[..., :3]
    return np.asarray(img.convert("RGB"))


def _box_from_params(params: dict[str, Any], img: Image.Image) -> Box | None:
    raw = params.get("box")
    if raw is None:
        return None
    return Box.from_any(raw, img.width, img.height)


def _op_label(op: EditOp) -> str:
    return op.kind.value if isinstance(op.kind, OpKind) else str(op.kind)


# --------------------------------------------------------------------------- #
# Contexto de uma imagem
# --------------------------------------------------------------------------- #
@dataclass
class _Item:
    """Plano de trabalho de UMA imagem, decidido antes de qualquer thread rodar."""

    index: int
    src: Path
    out: Path
    fmt: str
    quality: int
    ops: list[EditOp]
    sha: str = ""
    analysis: Any = None          # CreativeAnalysis | None
    skip: bool = False


@dataclass
class _Ctx:
    """Estado mutável enquanto as operações de uma imagem são aplicadas."""

    item: _Item
    settings: Settings
    recipe: Recipe
    original: Image.Image
    img: Image.Image
    changed: list[Box] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)
    engines: set[str] = field(default_factory=set)
    cost: float = 0.0
    geometry_changed: bool = False
    reframe_info: dict[str, Any] | None = None

    def warn(self, msg: str) -> None:
        if msg and msg not in self.warnings:
            self.warnings.append(msg)

    def analysis(self) -> Any:
        """Análise da imagem, calculada sob demanda (só quando falta 'box')."""
        if self.item.analysis is None:
            self.item.analysis = _vision.analyze_creative(self.item.src, self.settings)
        return self.item.analysis


# --------------------------------------------------------------------------- #
# Operações
# --------------------------------------------------------------------------- #
def _resolve_engine(op: EditOp, ctx: _Ctx) -> str:
    """Motor efetivo desta operação: 'deterministic' ou 'ai'.

    ``auto`` prefere a trilha determinística sempre que ela existe — ela é de
    graça, é offline e é a única que prova drift zero. A IA só entra quando a
    operação não tem trilha determinística (``replace_region``) ou quando o
    usuário pediu ``engine: ai`` explicitamente.
    """
    wanted = op.engine if isinstance(op.engine, Engine) else Engine(str(op.engine))
    if op.kind in _AI_ONLY:
        wanted = Engine.AI
    if wanted is Engine.AUTO:
        return "ai" if op.kind in _AI_ONLY else "deterministic"
    if wanted is Engine.AI:
        if not ctx.settings.openai_api_key and not ctx.settings.dry_run:
            if op.kind in _AI_ONLY:
                raise PipelineError(
                    f"a operação '{_op_label(op)}' só existe na trilha de IA e a chave da "
                    "OpenAI não foi encontrada.\n"
                    "  Defina OPENAI_API_KEY (ou crie um arquivo .env com ela) e rode de novo,\n"
                    "  ou troque esta operação por uma da trilha determinística "
                    "(replace_text / remove_text / add_text)."
                )
            ctx.warn(f"'{_op_label(op)}' pediu engine: ai mas não há chave da OpenAI; "
                     "usei a trilha determinística (offline).")
            return "deterministic"
        return "ai"
    return "deterministic"


def _find_block(op: EditOp, ctx: _Ctx) -> TextBlock | None:
    """Descobre em qual bloco de texto a operação manda.

    Com ``box`` explícito não há análise nenhuma: a caixa é a licença e o
    caminho fica 100% offline. Sem ela, perguntamos à visão.
    """
    params = op.params
    img = ctx.img
    box = _box_from_params(params, img)
    find = params.get("find")
    role_raw = params.get("role")
    fuzzy = str(params.get("match") or "fuzzy").strip().lower() != "exact"

    if box is not None and not find and not role_raw:
        # Caixa crua: sintetizamos o bloco. O estilo é medido nos pixels por
        # textedit.replace_text, então FontSpec() aqui é só um esqueleto.
        return TextBlock(box=box, text="", role=TextRole.OTHER, style=FontSpec())

    analysis = ctx.analysis()
    block = _vision.find_text_block(analysis, find=find, role=role_raw, box=box, fuzzy=fuzzy)
    if block is None and box is not None:
        ctx.warn("não localizei o texto pedido pela análise; usei a caixa informada na receita.")
        return TextBlock(box=box, text="", role=TextRole.OTHER, style=FontSpec())
    return block


def _describe_target(op: EditOp) -> str:
    p = op.params
    if p.get("find"):
        return f"texto {p['find']!r}"
    if p.get("role"):
        return f"papel {p['role']}"
    if p.get("box"):
        return "a caixa informada"
    return "o alvo pedido"


def _luma(rgb) -> float:
    r, g, b = (float(v) for v in tuple(rgb)[:3])
    return 0.299 * r + 0.587 * g + 0.114 * b


def _readable_color(img: Image.Image, box: Box, preferred) -> tuple[tuple[int, int, int], bool]:
    """Cor legível para escrever em ``box``, partindo de ``preferred``.

    Herdar a cor do bloco-âncora é o certo na maioria das vezes, e é uma
    armadilha quando a âncora vive num selo colorido: o preço é escuro porque o
    selo é amarelo, e essa mesma cor escrita embaixo, no fundo escuro da peça,
    sairia invisível. Aqui medimos o fundo REAL onde vamos desenhar e só
    mantemos a cor herdada se ela tiver contraste; senão caímos para preto ou
    branco, o que for legível.

    Devolve ``(cor, trocada)``.
    """
    b = box.clamp(img.width, img.height)
    if b.area <= 0:
        return (tuple(int(v) for v in tuple(preferred)[:3]), False)
    fundo = _io.average_color(img, b)
    pref = tuple(int(v) for v in tuple(preferred)[:3])
    # 60 em luminância ~ o mínimo para o texto não sumir no fundo.
    if abs(_luma(pref) - _luma(fundo)) >= 60.0:
        return (pref, False)
    return (((0, 0, 0) if _luma(fundo) > 140 else (255, 255, 255)), True)


def _anchor_box(ctx: _Ctx, params: dict[str, Any]) -> tuple[Box, FontSpec] | None:
    """Caixa (e estilo) para escrever colada a um bloco existente.

    É o que resolve "coloca o TESTE GRÁTIS embaixo do preço": a posição não é
    fixa, ela sai de onde o preço está NAQUELA peça — e o preço está em lugares
    diferentes em cada criativo do lote.
    """
    analysis = ctx.analysis()
    if analysis is None:
        return None

    alvo = params.get("ancora") or params.get("anchor") or params.get("abaixo_de")
    texto_ancora = params.get("ancora_texto") or params.get("anchor_text")
    bloco = None
    if texto_ancora:
        bloco = _vision.find_text_block(analysis, find=str(texto_ancora), fuzzy=True)
    if bloco is None and alvo:
        bloco = _vision.find_text_block(analysis, role=str(alvo))
    if bloco is None:
        return None

    a = bloco.box
    onde = str(params.get("posicao") or params.get("position") or "abaixo").lower()
    gap = max(6, int(round(a.h * float(params.get("gap", 0.30) or 0.30))))
    # Altura cheia da âncora: com 0.8 o autofit encolhia o texto para ~40% do
    # corpo do preço e o resultado lia como legenda, não como chamada.
    alt = max(10, int(round(a.h * float(params.get("altura", 1.05) or 1.05))))
    larg = min(ctx.img.width, max(a.w, int(round(a.w * 1.8))))
    x = max(0, min(ctx.img.width - larg, a.center[0] - larg // 2))
    y = (a.y1 + gap) if onde in ("abaixo", "below", "baixo") else (a.y - gap - alt)
    caixa = Box(x, int(y), larg, alt).clamp(ctx.img.width, ctx.img.height)
    if caixa.h < 10 or caixa.w < 10:
        return None

    base = bloco.style
    cor, trocada = _readable_color(ctx.img, caixa, base.color)
    if trocada:
        ctx.warn("a cor herdada da âncora não teria contraste no lugar novo; "
                 f"usei {'preto' if cor == (0, 0, 0) else 'branco'} para o texto ficar legível.")
    spec = FontSpec.from_dict({**base.to_dict(), "color": list(cor),
                               "size_px": max(8, int(round(base.size_px * 0.95))),
                               "align": "center", "valign": "middle",
                               "stroke_width": 0, "shadow": False})
    return (caixa, spec)


def _op_replace_text(op: EditOp, ctx: _Ctx) -> None:
    block = _find_block(op, ctx)
    if block is None:
        senao = (op.params.get("senao_adicionar") or op.params.get("else_add")
                 or op.params.get("senao"))
        if isinstance(senao, dict):
            _add_anchored(op, ctx, senao)
            return
        ctx.warn(f"replace_text: não encontrei {_describe_target(op)} em "
                 f"{ctx.item.src.name}; a imagem saiu sem essa troca.")
        return
    new_text = str(op.params.get("replace") or "")
    rep: dict[str, Any] = {}
    before = _rgb(ctx.img)
    out, changed = _textedit.replace_text(
        ctx.img, block, new_text,
        settings=ctx.settings,
        style_override=op.params.get("style"),
        autofit=bool(op.params.get("autofit", True)),
        report=rep,
    )
    for w in rep.get("warnings", []):
        ctx.warn(w)
    if rep.get("ok") is False:
        # Escada E.3 esgotada: texto não cabe. Falhar alto é melhor que entregar
        # a peça com o CTA cortado.
        raise PipelineError(
            f"o texto {new_text!r} não cabe na caixa nem no menor corpo aceitável "
            f"(55% do original).\n"
            f"  Encurte a copy, aumente a caixa na receita ou permita mais linhas."
        )
    ctx.img = out
    if changed is not None and changed.area > 0:
        ctx.changed.append(changed)
    elif _changed_bbox(before, _rgb(out)) is None:
        ctx.warn("replace_text: nada mudou (o texto novo é igual ao que já estava lá?)")
    ctx.applied.append(f"replace_text -> {new_text!r}")
    if op.params.get("max_lines") is not None or op.params.get("grow_box") is not None:
        ctx.warn("'max_lines'/'grow_box' ainda não são regulados por receita: o ajuste "
                 "segue a escada automática (E.3).")


def _add_anchored(op: EditOp, ctx: _Ctx, senao: dict[str, Any]) -> None:
    """Escreve o texto colado a outro bloco, quando o texto procurado não existe.

    É a segunda metade de "onde diz ASSINE AGORA troca por TESTE GRÁTIS, e onde
    não diz nada põe o TESTE GRÁTIS embaixo do preço": num lote real as duas
    situações convivem, e o lote tem que resolver as duas sozinho.
    """
    texto = str(senao.get("texto") or senao.get("text")
                or op.params.get("replace") or "").strip()
    if not texto:
        ctx.warn("senao_adicionar: sem texto para escrever; a imagem saiu sem alteração.")
        return

    plano = _anchor_box(ctx, senao)
    if plano is None:
        alvo = senao.get("ancora") or senao.get("anchor") or senao.get("abaixo_de") or "?"
        ctx.warn(f"não achei o texto procurado NEM o bloco âncora ({alvo}) em "
                 f"{ctx.item.src.name}; a imagem saiu sem alteração.")
        return

    caixa, spec = plano
    override = senao.get("style") or op.params.get("style")
    if isinstance(override, dict) and override:
        spec = FontSpec.from_dict({**spec.to_dict(), **override})

    rep: dict[str, Any] = {}
    out, changed = _textedit.add_text(ctx.img, caixa, texto, spec,
                                      autofit=bool(senao.get("autofit", True)), report=rep)
    for w in rep.get("warnings", []):
        ctx.warn(w)
    ctx.img = out
    if changed is not None and changed.area > 0:
        ctx.changed.append(changed)
    ctx.applied.append(f"add_text (âncora) -> {texto!r}")


def _op_remove_text(op: EditOp, ctx: _Ctx) -> None:
    block = _find_block(op, ctx)
    if block is None:
        ctx.warn(f"remove_text: não encontrei {_describe_target(op)} em {ctx.item.src.name}.")
        return
    rep: dict[str, Any] = {}
    out, changed = _textedit.remove_text(
        ctx.img, block, settings=ctx.settings,
        feather=int(op.params.get("feather", 1) or 0), report=rep)
    for w in rep.get("warnings", []):
        ctx.warn(w)
    ctx.img = out
    if changed is not None and changed.area > 0:
        ctx.changed.append(changed)
    ctx.applied.append("remove_text")


def _default_spec_for_box(img: Image.Image, box: Box) -> FontSpec:
    """Estilo razoável quando a receita não diz nada: corpo pelo tamanho da
    caixa e cor com contraste garantido contra o fundo que está ali."""
    r, g, b = _io.average_color(img, box)
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return FontSpec(size_px=max(8, int(round(box.h * 0.6))),
                    color=(17, 17, 17) if luma > 140 else (255, 255, 255))


def _op_add_text(op: EditOp, ctx: _Ctx) -> None:
    box = _box_from_params(op.params, ctx.img)
    if box is None or box.area <= 0:
        raise PipelineError("add_text precisa de uma 'box' válida (x/y/w/h ou normalizada 0–1).")
    spec_raw = op.params.get("style")
    if isinstance(spec_raw, FontSpec):
        spec = spec_raw
    elif isinstance(spec_raw, dict) and spec_raw:
        base = _default_spec_for_box(ctx.img, box)
        merged = {**base.to_dict(), **spec_raw}
        spec = FontSpec.from_dict(merged)
    else:
        spec = _default_spec_for_box(ctx.img, box)

    rep: dict[str, Any] = {}
    out, changed = _textedit.add_text(
        ctx.img, box, str(op.params.get("text") or ""), spec,
        autofit=bool(op.params.get("autofit", True)), report=rep)
    for w in rep.get("warnings", []):
        ctx.warn(w)
    ctx.img = out
    if changed is not None and changed.area > 0:
        ctx.changed.append(changed)
    ctx.applied.append("add_text")


def _op_replace_color(op: EditOp, ctx: _Ctx) -> None:
    """Troca uma cor por outra dentro da caixa (ou na imagem toda).

    Escrita confinada: só o slice da caixa é atribuído, e só nos pixels dentro
    da tolerância. O resto é copiado byte a byte.
    """
    src_c = np.array(parse_color(op.params.get("from")), dtype=np.float32)
    dst_c = np.array(parse_color(op.params.get("to")), dtype=np.uint8)
    tol = float(op.params.get("tolerance", 12) or 0)

    box = _box_from_params(op.params, ctx.img) or Box(0, 0, ctx.img.width, ctx.img.height)
    if box.area <= 0:
        ctx.warn("replace_color: a caixa ficou vazia dentro da imagem; nada foi feito.")
        return

    arr = np.array(ctx.img.convert("RGBA") if ctx.img.mode == "RGBA" else ctx.img.convert("RGB"))
    patch = arr[box.y:box.y1, box.x:box.x1]
    rgb = patch[..., :3].astype(np.float32)
    hit = np.linalg.norm(rgb - src_c, axis=2) <= tol
    if not hit.any():
        ctx.warn(f"replace_color: nenhum pixel dentro da tolerância {tol:g} em "
                 f"{ctx.item.src.name}; nada foi trocado.")
        return
    patch[..., :3] = np.where(hit[..., None], dst_c, patch[..., :3])
    arr[box.y:box.y1, box.x:box.x1] = patch

    out = Image.fromarray(arr, ctx.img.mode if ctx.img.mode in ("RGB", "RGBA") else "RGB")
    out.info.update(ctx.img.info)
    changed = _changed_bbox(_rgb(ctx.img), _rgb(out))
    ctx.img = out
    if changed is not None:
        ctx.changed.append(changed)
    ctx.applied.append("replace_color")


def _ai_edit_in_box(ctx: _Ctx, box: Box, prompt: str, *, feather: int, label: str) -> None:
    """Edição por IA com composição protegida (trilha (b) do princípio).

    O resultado final é o ORIGINAL com apenas a região mascarada colada por
    cima: fora da máscara os bytes são os de entrada, sem exceção. É
    :func:`protect.protected_composite` que garante isso, não o modelo.
    """
    base = ctx.img
    mask = _protect.build_mask(base.size, [box], feather=max(0, int(feather)))
    size = _aigen.pick_api_size(ctx.settings.image_model, base.width, base.height)
    outs = _aigen.edit([base], prompt, mask=mask, settings=ctx.settings,
                       size=size, n=1, input_fidelity="high")
    if not outs:
        raise PipelineError(f"{label}: a API não devolveu nenhuma imagem.")
    edited = outs[0]
    if edited.size != base.size:
        ctx.warn(f"{label}: o modelo devolveu {edited.width}x{edited.height} e o master é "
                 f"{base.width}x{base.height}; a região colada foi reamostrada "
                 "(pode aparecer costura DENTRO da caixa — fora dela nada mudou).")
    with _warnings_mod.catch_warnings():
        _warnings_mod.simplefilter("ignore")   # o aviso de rescale já virou o texto acima
        ctx.img = _protect.protected_composite(base, edited, mask)
    ctx.changed.append(box)
    ctx.cost += _aigen.estimate_cost(ctx.settings.image_model, size,
                                     ctx.recipe.quality or ctx.settings.quality, 1)
    ctx.applied.append(label)


def _op_replace_region(op: EditOp, ctx: _Ctx) -> None:
    box = _box_from_params(op.params, ctx.img)
    if box is None or box.area <= 0:
        raise PipelineError("replace_region precisa de uma 'box' válida.")
    prompt = str(op.params.get("prompt") or "").strip()
    if not prompt:
        raise PipelineError("replace_region precisa de 'prompt' descrevendo o que colocar na região.")
    _ai_edit_in_box(ctx, box, prompt, feather=int(op.params.get("feather", 0) or 0),
                    label="replace_region")


def _op_remove_object(op: EditOp, ctx: _Ctx, engine: str) -> None:
    box = _box_from_params(op.params, ctx.img)
    if box is None:
        block = _find_block(op, ctx)
        if block is None:
            ctx.warn(f"remove_object: não encontrei {_describe_target(op)} em "
                     f"{ctx.item.src.name}.")
            return
        box = block.box
    if box.area <= 0:
        ctx.warn("remove_object: a caixa ficou vazia dentro da imagem.")
        return

    if engine == "ai":
        alvo = str(op.params.get("find") or "the object inside the masked area")
        prompt = str(op.params.get("prompt") or "").strip() or (
            f"Remove {alvo} and rebuild the background that was behind it. "
            "Continue the existing lighting, color grade, texture and perspective. "
            "Do not add any people, objects, logos, watermarks or text."
        )
        _ai_edit_in_box(ctx, box, prompt, feather=int(op.params.get("feather", 0) or 0),
                        label="remove_object")
        return

    rep: dict[str, Any] = {}
    before = _rgb(ctx.img)
    out = _inpaint.erase_region(ctx.img, box, feather=int(op.params.get("feather", 1) or 0),
                                report=rep)
    for w in rep.get("warnings", []):
        ctx.warn(w)
    changed = _changed_bbox(before, _rgb(out))
    ctx.img = out
    if changed is not None:
        ctx.changed.append(changed)
    else:
        ctx.warn("remove_object: nada foi apagado na caixa informada.")
    ctx.applied.append("remove_object")


def _resolve_position(pos: str, canvas: tuple[int, int], size: tuple[int, int],
                      margin: int) -> tuple[int, int]:
    cw, ch = canvas
    ow, oh = size
    p = str(pos or "bottom-right").strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "topo": "top", "base": "bottom", "fundo": "bottom", "centro": "center",
        "esquerda": "left", "direita": "right", "meio": "center",
        "superior-esquerdo": "top-left", "superior-direito": "top-right",
        "inferior-esquerdo": "bottom-left", "inferior-direito": "bottom-right",
    }
    p = aliases.get(p, p)
    left, cx, right = margin, (cw - ow) // 2, cw - ow - margin
    top, cy, bottom = margin, (ch - oh) // 2, ch - oh - margin
    table = {
        "top-left": (left, top), "top": (cx, top), "top-right": (right, top),
        "left": (left, cy), "center": (cx, cy), "right": (right, cy),
        "bottom-left": (left, bottom), "bottom": (cx, bottom),
        "bottom-right": (right, bottom),
    }
    return table.get(p, table["bottom-right"])


def _op_overlay(op: EditOp, ctx: _Ctx) -> None:
    """Cola um PNG (logo, selo) por cima. Determinístico e confinado ao retângulo colado."""
    raw = str(op.params.get("image") or "").strip()
    if not raw:
        raise PipelineError("overlay precisa de 'image:' apontando para o arquivo do selo/logo.")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        for base in (ctx.recipe.input_dir, Path(ctx.settings.root), Path.cwd()):
            cand = Path(base) / p
            if cand.exists():
                p = cand
                break
    if not p.exists():
        raise PipelineError(
            f"não encontrei a imagem do overlay: {raw}\n"
            f"  Use o caminho completo ou coloque o arquivo em {ctx.settings.root}."
        )

    logo = _io.load_image(p)
    if logo.mode != "RGBA":
        logo = logo.convert("RGBA")

    box = _box_from_params(op.params, ctx.img)
    if box is not None and box.area > 0:
        fitted = _io.resize_contain(logo, box.w, box.h, pad=False)
        x = box.x + (box.w - fitted.width) // 2
        y = box.y + (box.h - fitted.height) // 2
    else:
        scale = float(op.params.get("scale", 0.2) or 0.2)
        target_w = max(1, int(round(ctx.img.width * scale)) if scale <= 1 else int(scale))
        ratio = target_w / max(1, logo.width)
        fitted = logo.resize((target_w, max(1, int(round(logo.height * ratio)))),
                             Image.Resampling.LANCZOS)
        m = float(op.params.get("margin", 0.04) or 0.0)
        margin = int(round(ctx.img.width * m)) if m <= 1 else int(m)
        x, y = _resolve_position(op.params.get("position", "bottom-right"),
                                 ctx.img.size, fitted.size, margin)

    opacity = float(op.params.get("opacity", 1.0) or 1.0)
    if opacity < 1.0:
        alpha = fitted.getchannel("A").point(lambda v: int(v * max(0.0, min(1.0, opacity))))
        fitted.putalpha(alpha)

    paste = Box(int(x), int(y), fitted.width, fitted.height).clamp(ctx.img.width, ctx.img.height)
    if paste.area <= 0:
        ctx.warn("overlay: o selo caiu fora da imagem; nada foi colado.")
        return

    out = ctx.img.copy()
    out.paste(fitted, (int(x), int(y)), fitted)
    out.info.update(ctx.img.info)
    changed = _changed_bbox(_rgb(ctx.img), _rgb(out)) or paste
    ctx.img = out
    ctx.changed.append(changed)
    ctx.applied.append(f"overlay {p.name}")


def _op_resize(op: EditOp, ctx: _Ctx) -> None:
    w0, h0 = ctx.img.size
    p = op.params
    keep = bool(p.get("keep_aspect", True))
    width, height = p.get("width"), p.get("height")
    scale, long_edge = p.get("scale"), p.get("long_edge")

    if scale:
        s = float(scale)
        nw, nh = max(1, int(round(w0 * s))), max(1, int(round(h0 * s)))
        out = ctx.img.resize((nw, nh), Image.Resampling.LANCZOS)
    elif long_edge:
        s = float(long_edge) / max(w0, h0)
        out = ctx.img.resize((max(1, int(round(w0 * s))), max(1, int(round(h0 * s)))),
                             Image.Resampling.LANCZOS)
    elif width and height:
        if keep:
            out = _io.resize_contain(ctx.img, int(width), int(height), pad=False)
        else:
            ctx.warn(f"resize para {int(width)}x{int(height)} com keep_aspect: false "
                     "DISTORCE a imagem (o pedido do lote é não alterar proporções).")
            out = ctx.img.resize((int(width), int(height)), Image.Resampling.LANCZOS)
    elif width:
        s = float(width) / w0
        out = ctx.img.resize((int(width), max(1, int(round(h0 * s)))), Image.Resampling.LANCZOS)
    elif height:
        s = float(height) / h0
        out = ctx.img.resize((max(1, int(round(w0 * s))), int(height)), Image.Resampling.LANCZOS)
    else:
        raise PipelineError("resize precisa de 'width'/'height', 'scale' ou 'long_edge'.")

    out.info.update(ctx.img.info)
    ctx.img = out
    if (out.width, out.height) != (w0, h0):
        ctx.geometry_changed = True
    ctx.applied.append(f"resize {w0}x{h0} -> {out.width}x{out.height}")


def _op_reframe(op: EditOp, ctx: _Ctx) -> None:
    p = op.params
    target = p.get("target") or ctx.recipe.target
    if target is None:
        raise PipelineError("reframe precisa de 'target' (ex.: '16:9' ou '1920x1080').")
    spec = target if isinstance(target, AspectSpec) else AspectSpec.parse(str(target))
    # Só fixamos o tamanho aqui quando o usuário pediu um ("1920x1080" ou
    # --long-edge). Sem pedido explícito, passamos a proporção adiante e
    # deixamos reframe() derivar do maior lado DESTA imagem — senão um lote
    # de 1080x1920 sairia encolhido para 1440x810.
    long_edge = p.get("long_edge") or ctx.recipe.long_edge
    if long_edge:
        dst: Any = spec.resolve(int(long_edge))
    elif spec.width and spec.height:
        dst = (spec.width, spec.height)
    else:
        dst = spec

    mode = str(p.get("mode") or ctx.recipe.reframe_mode or "pad").strip().lower()
    fill = p.get("fill", ctx.recipe.reframe_fill)
    prompt = p.get("prompt", ctx.recipe.reframe_prompt)
    analysis = ctx.item.analysis
    if analysis is None and mode in ("relayout", "crop"):
        analysis = ctx.analysis()

    out, info = _reframe.reframe(ctx.img, dst, mode=mode, settings=ctx.settings,
                                 analysis=analysis, fill=fill, prompt=prompt)
    for w in info.get("warnings", []):
        ctx.warn(w)
    ctx.cost += float(info.get("cost_usd") or 0.0)
    if info.get("engine"):
        ctx.engines.add(str(info["engine"]))
    ctx.reframe_info = info
    if (out.width, out.height) != ctx.img.size:
        ctx.geometry_changed = True
    ctx.img = out
    ctx.applied.append(f"reframe {mode} -> {out.width}x{out.height}")


def _apply_op(op: EditOp, ctx: _Ctx) -> None:
    """Despacha uma operação. Erros sobem para o try/except da imagem."""
    engine = _resolve_engine(op, ctx)
    ctx.engines.add(engine)
    kind = op.kind

    if kind is OpKind.REPLACE_TEXT:
        _op_replace_text(op, ctx)
    elif kind is OpKind.REMOVE_TEXT:
        _op_remove_text(op, ctx)
    elif kind is OpKind.ADD_TEXT:
        _op_add_text(op, ctx)
    elif kind is OpKind.REPLACE_COLOR:
        _op_replace_color(op, ctx)
    elif kind is OpKind.REPLACE_REGION:
        _op_replace_region(op, ctx)
    elif kind is OpKind.REMOVE_OBJECT:
        _op_remove_object(op, ctx, engine)
    elif kind is OpKind.OVERLAY:
        _op_overlay(op, ctx)
    elif kind is OpKind.RESIZE:
        _op_resize(op, ctx)
    elif kind is OpKind.REFRAME:
        _op_reframe(op, ctx)
    elif kind is OpKind.EXPORT:
        # Decidida na fase de planejamento (muda o nome do arquivo de saída).
        ctx.applied.append("export")
    else:  # pragma: no cover - OpKind é fechado
        raise PipelineError(f"operação sem implementação no pipeline: {_op_label(op)}")


# --------------------------------------------------------------------------- #
# Uma imagem, do começo ao fim
# --------------------------------------------------------------------------- #
def _process_one(item: _Item, recipe: Recipe, settings: Settings) -> ImageResult:
    t0 = time.perf_counter()
    res = ImageResult(source=item.src, output=item.out)
    ctx: _Ctx | None = None

    def _salvage(err: str) -> ImageResult:
        """Falhou: o que já foi medido (e sobretudo o que já foi PAGO) continua valendo."""
        res.ok = False
        res.output = None
        res.error = err
        if ctx is not None:
            res.warnings = list(ctx.warnings)
            res.operations = list(ctx.applied)
            res.cost_usd = ctx.cost
            res.engine_used = "+".join(sorted(ctx.engines)) if ctx.engines else ""
            if ctx.cost:
                res.warnings.append(
                    f"a falha aconteceu depois de US$ {ctx.cost:.4f} em chamadas de IA "
                    "que já foram cobradas.")
        return res

    try:
        original = _io.load_image(item.src)
        ctx = _Ctx(item=item, settings=settings, recipe=recipe,
                   original=original, img=original)

        for op in item.ops:
            _apply_op(op, ctx)

        res.operations = list(ctx.applied)
        res.warnings = list(ctx.warnings)
        res.cost_usd = ctx.cost
        res.engine_used = "+".join(sorted(ctx.engines)) if ctx.engines else ""

        if not ctx.applied:
            res.warnings.append("nenhuma operação se aplicou a esta imagem "
                                "(confira 'scope:' na receita); ela foi só copiada.")

        changed = _clean_boxes(ctx.changed, ctx.img.width, ctx.img.height)
        res.changed_boxes = changed

        # ---- a prova: nada mudou fora das caixas -------------------------- #
        lossy = _is_lossy(item.fmt, item.quality)
        if ctx.geometry_changed or ctx.img.size != original.size:
            res.untouched_pixels_verified = None
            res.drift_pixels = 0
            info = ctx.reframe_info or {}
            # As caixas medidas antes do reenquadramento estão no sistema de
            # coordenadas antigo: listá-las aqui seria informação errada.
            res.changed_boxes = [Box.from_any(b, ctx.img.width, ctx.img.height)
                                 for b in (info.get("generated_boxes") or [])]
            res.warnings.append(
                "as dimensões mudaram (reframe/resize): a comparação byte a byte com o "
                "original não existe. O conteúdo original entrou por reescala uniforme, "
                "sem distorção — as caixas listadas são as áreas geradas, e as caixas "
                "editadas antes do reenquadramento foram omitidas porque as coordenadas "
                "mudaram."
            )
        else:
            n, bbox = _protect.drift_report(original, ctx.img, changed, tol=0)
            res.drift_pixels = int(n)
            res.untouched_pixels_verified = (n == 0)
            if n:
                onde = f" (maior mancha em {bbox.to_dict()})" if bbox else ""
                res.warnings.append(
                    f"ATENÇÃO: {n} pixel(s) mudaram FORA das caixas editadas{onde}. "
                    "Isso é um bug de máscara — reporte, com o nome do arquivo."
                )
                log.warning("drift de %d px em %s", n, item.src.name)

        # ---- gravação ----------------------------------------------------- #
        if lossy and any(op.kind in _CONFINED_OPS for op in item.ops):
            res.warnings.append(
                f"entregável em {item.fmt}: a recodificação é com perdas e mexe em "
                "praticamente todos os pixels da imagem, inclusive fora das caixas "
                "editadas. A garantia foi conferida no master, em memória, antes de "
                "codificar. Para receber o master sem perdas use 'deliver: "
                "{preserve_format: false}' (ou 'format: png')."
            )

        if settings.dry_run:
            res.output = None
            res.warnings.append("dry-run: nada foi gravado em disco.")
            res.ok = True
            return res

        _io.save_image(ctx.img, item.out, fmt=item.fmt, quality=item.quality)
        res.output = item.out

        if lossy and res.untouched_pixels_verified:
            # O arquivo entregue NÃO é o master: medimos o drift real do que o
            # usuário vai abrir, com tolerância, e nunca afirmamos "verificado".
            try:
                saved = _io.load_image(item.out)
                n2, _ = _protect.drift_report(original, saved, res.changed_boxes,
                                              tol=JPEG_TOLERANCE)
            except Exception:  # noqa: BLE001 - conferência é diagnóstico, não entrega
                n2 = -1
            res.untouched_pixels_verified = None
            if n2 >= 0:
                res.drift_pixels = int(n2)
                res.warnings.append(
                    f"drift medido no arquivo entregue, com tolerância de "
                    f"{JPEG_TOLERANCE}/canal: {n2} pixel(s). No master, em memória, era 0."
                )

        res.ok = True
        return res

    except (PipelineError, FileNotFoundError, ValueError) as exc:
        return _salvage(str(exc))
    except Exception as exc:  # noqa: BLE001 - uma imagem ruim não derruba o lote
        log.debug("falha em %s", item.src, exc_info=True)
        return _salvage(f"{type(exc).__name__}: {exc}")
    finally:
        res.duration_s = time.perf_counter() - t0


# --------------------------------------------------------------------------- #
# Planejamento do lote
# --------------------------------------------------------------------------- #
def _collect_paths(recipe: Recipe, paths: Sequence[Any] | None) -> list[Path]:
    if paths is not None:
        return [Path(p) for p in paths]
    try:
        return _io.list_images(recipe.input_dir, recursive=recipe.recursive)
    except FileNotFoundError as exc:
        raise PipelineError(str(exc)) from exc


def _decide_format(recipe: Recipe, src: Path, ops: Sequence[EditOp]) -> tuple[str, int]:
    """Formato e qualidade de saída desta imagem.

    Prioridade: operação ``export`` > ``deliver.preserve_format`` >
    ``deliver.format`` (que já nasce ``png`` — o master do item F).
    """
    fmt_raw = str(recipe.deliver.get("format") or "png")
    quality = int(recipe.deliver.get("quality") or 95)

    preserve = _deliver_flag(recipe, "preserve_format", None)
    if preserve is True:
        fmt = _fmt_from_suffix(src)
    elif preserve is False:
        fmt = "PNG"
    else:
        fmt = {"jpg": "JPEG", "jpeg": "JPEG"}.get(fmt_raw.lower(), fmt_raw.upper())

    for op in ops:
        if op.kind is OpKind.EXPORT:
            if op.params.get("format"):
                f = str(op.params["format"]).strip().lower().lstrip(".")
                fmt = {"jpg": "JPEG", "jpeg": "JPEG"}.get(f, f.upper())
            if op.params.get("quality"):
                quality = int(op.params["quality"])
    return (fmt or "PNG", max(1, min(100, quality)))


def _decide_name(recipe: Recipe, src: Path, ops: Sequence[EditOp], fmt: str) -> str:
    prefix = str(recipe.deliver.get("prefix") or "")
    suffix = str(recipe.deliver.get("suffix") or "")
    for op in ops:
        if op.kind is OpKind.EXPORT:
            prefix = str(op.params.get("prefix", prefix) or "")
            suffix = str(op.params.get("suffix", suffix) or "")
    return f"{prefix}{src.stem}{suffix}{_ext_for(fmt)}"


def _plan(recipe: Recipe, settings: Settings, paths: Sequence[Path],
          *, force: bool, sig: str) -> tuple[list[_Item], dict[str, Any], list[str]]:
    """Decide, em thread única e de forma determinística, o que cada imagem vira."""
    total = len(paths)
    state = _load_state(recipe.output_dir)
    notes: list[str] = []
    used_names: set[str] = set()
    items: list[_Item] = []

    for i, src in enumerate(paths):
        ops = recipe.ops_for(src, i, total)
        if recipe.target is not None and not any(o.kind is OpKind.REFRAME for o in ops):
            # 'target:' no topo da receita é um reframe implícito no fim da fila.
            ops = list(ops) + [EditOp(kind=OpKind.REFRAME,
                                      params={"target": recipe.target,
                                              "mode": recipe.reframe_mode,
                                              "fill": recipe.reframe_fill,
                                              "prompt": recipe.reframe_prompt,
                                              "long_edge": recipe.long_edge},
                                      engine=recipe.engine)]
        fmt, quality = _decide_format(recipe, src, ops)
        name = _decide_name(recipe, src, ops, fmt)
        if name.lower() in used_names:
            # Dois arquivos de entrada com o mesmo nome-base (a.png e a.jpg):
            # renomear é melhor que sobrescrever em silêncio.
            stem, ext = name.rsplit(".", 1)
            k = 2
            while f"{stem}-{k}.{ext}".lower() in used_names:
                k += 1
            name = f"{stem}-{k}.{ext}"
            notes.append(f"'{src.name}' foi entregue como '{name}' para não sobrescrever "
                         "outro arquivo de mesmo nome.")
        used_names.add(name.lower())

        item = _Item(index=i, src=src, out=recipe.output_dir / name,
                     fmt=fmt, quality=quality, ops=list(ops))

        if not force:
            prev = state.get(name)
            if isinstance(prev, dict) and item.out.exists() and prev.get("recipe") == sig:
                try:
                    item.sha = _file_sha(src)
                except OSError:
                    item.sha = ""
                if item.sha and prev.get("src_sha") == item.sha:
                    item.skip = True
        items.append(item)

    return items, state, notes


def _needs_analysis(items: Sequence[_Item]) -> list[_Item]:
    """Imagens que precisam da visão: operação de texto sem 'box' explícito."""
    out: list[_Item] = []
    for it in items:
        if it.skip:
            continue
        for op in it.ops:
            if op.kind in _NEEDS_ANALYSIS and not op.params.get("box"):
                out.append(it)
                break
            if op.kind is OpKind.REPLACE_TEXT and (op.params.get("find") or op.params.get("role")):
                out.append(it)
                break
            if op.kind is OpKind.REFRAME and str(
                    op.params.get("mode") or "").lower() in ("relayout", "crop"):
                out.append(it)
                break
    return out


# --------------------------------------------------------------------------- #
# run_recipe
# --------------------------------------------------------------------------- #
def run_recipe(recipe: Recipe, settings: Settings | None = None, *,
               progress: Callable[[int, int, str], None] | None = None,
               force: bool | None = None,
               paths: Sequence[Any] | None = None) -> JobManifest:
    """Executa a receita inteira e devolve o :class:`JobManifest`.

    ``force=True`` refaz tudo, ignorando a retomada (o mesmo que
    ``deliver: {force: true}`` na receita). ``paths`` limita o lote a uma lista
    explícita de arquivos — é por aí que os atalhos (``run_reframe_batch`` e
    companhia) entram sem duplicar lógica.

    Nunca levanta por causa de UMA imagem: o erro dela vira ``ImageResult.error``
    e o lote segue. Levanta :class:`PipelineError` só quando o lote inteiro é
    impossível (pasta vazia, receita sem nada para fazer).
    """
    settings = settings or load_settings()
    if force is None:
        force = bool(_deliver_flag(recipe, "force", False))

    manifest = JobManifest(
        job=recipe.job,
        recipe_path=recipe.recipe_path,
        input_dir=str(recipe.input_dir),
        output_dir=str(recipe.output_dir),
        started_at=_now(),
    )
    manifest.notes.extend(recipe.notes)
    manifest.notes.extend(recipe.warnings)

    files = _collect_paths(recipe, paths)

    if recipe.variations:
        results, notes = _run_variations(recipe, settings, files,
                                         progress=progress, force=bool(force))
        manifest.results = results
        manifest.notes.extend(notes)
        return _finish_manifest(manifest, settings, recipe)

    if not files and paths is not None:
        raise PipelineError(
            "a lista de imagens veio vazia: não há o que processar.\n"
            "  Escolha os arquivos (ou aponte uma pasta com criativos) e rode de novo."
        )
    if not files:
        raise PipelineError(
            f"não achei nenhuma imagem em {recipe.input_dir}\n"
            f"  Coloque os arquivos na pasta (aceitos: "
            f"{', '.join(_io.SUPPORTED_EXT)}) ou corrija 'input:' na receita.\n"
            f"  Se as imagens estão em subpastas, use 'recursive: true'."
        )
    if not recipe.has_operations and recipe.target is None:
        raise PipelineError(
            "a receita não faz nada: nenhuma operação habilitada e nenhum 'target:'.\n"
            "  Adicione 'operations:' (ex.: replace_text) ou 'target: 16:9'."
        )

    sig = _recipe_signature(recipe, settings)
    recipe.output_dir.mkdir(parents=True, exist_ok=True)
    items, state, plan_notes = _plan(recipe, settings, files, force=force, sig=sig)
    manifest.notes.extend(plan_notes)

    total = len(items)
    reaproveitadas = sum(1 for it in items if it.skip)
    if reaproveitadas:
        manifest.notes.append(
            f"{reaproveitadas} de {total} imagens foram reaproveitadas da execução "
            "anterior (entrada e receita idênticas). Use force=true para refazer tudo.")

    # ---- análise (só de quem precisa, em blocos, para o progresso andar) --- #
    pendentes = _needs_analysis(items)
    if pendentes:
        workers = max(1, int(settings.max_concurrency or 1))
        done = 0
        for start in range(0, len(pendentes), workers):
            chunk = pendentes[start:start + workers]
            _tick(progress, done, len(pendentes),
                  f"analisando {done + 1}-{done + len(chunk)} de {len(pendentes)}")
            for it, an in zip(chunk, _vision.analyze_batch(
                    [c.src for c in chunk], settings, max_workers=workers)):
                it.analysis = an
            done += len(chunk)
        _tick(progress, len(pendentes), len(pendentes), "análise concluída")

    # ---- execução --------------------------------------------------------- #
    results: list[ImageResult | None] = [None] * total
    lock = threading.Lock()
    counter = {"n": 0}

    def work(it: _Item) -> None:
        if it.skip:
            r = ImageResult(source=it.src, output=it.out, ok=True, skipped=True,
                            operations=[_op_label(o) for o in it.ops],
                            warnings=["reaproveitada da execução anterior "
                                      "(entrada e receita não mudaram)"])
            prev = state.get(it.out.name) or {}
            r.drift_pixels = int(prev.get("drift_pixels") or 0)
            r.untouched_pixels_verified = prev.get("untouched_pixels_verified")
            r.engine_used = str(prev.get("engine_used") or "")
        else:
            r = _process_one(it, recipe, settings)
        results[it.index] = r
        with lock:
            counter["n"] += 1
            n = counter["n"]
        estado = "pulada" if r.skipped else ("ok" if r.ok else "FALHOU")
        _tick(progress, n, total, f"{it.src.name}: {estado}")

    workers = max(1, int(settings.max_concurrency or 1))
    if workers == 1 or total == 1:
        for it in items:
            work(it)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(work, items))

    manifest.results = [r for r in results if r is not None]

    # ---- estado da retomada ----------------------------------------------- #
    if not settings.dry_run:
        for it, r in zip(items, manifest.results):
            if not r.ok or r.skipped or r.output is None:
                continue
            sha = it.sha or (_file_sha(it.src) if it.src.exists() else "")
            state[it.out.name] = {
                "src": str(it.src),
                "src_sha": sha,
                "recipe": sig,
                "drift_pixels": r.drift_pixels,
                "untouched_pixels_verified": r.untouched_pixels_verified,
                "engine_used": r.engine_used,
                "at": _now(),
            }
        _save_state(recipe.output_dir, state)

    return _finish_manifest(manifest, settings, recipe)


def _finish_manifest(manifest: JobManifest, settings: Settings, recipe: Recipe) -> JobManifest:
    manifest.finished_at = _now()
    manifest.total_cost_usd = round(sum(r.cost_usd for r in manifest.results), 4)

    verificadas = sum(1 for r in manifest.results if r.untouched_pixels_verified)
    com_drift = [r for r in manifest.results if r.drift_pixels and r.untouched_pixels_verified is False]
    if verificadas:
        manifest.notes.append(
            f"garantia de zero drift verificada em {verificadas} imagem(ns): fora das "
            "caixas editadas os pixels são idênticos aos originais, byte a byte.")
    if com_drift:
        manifest.notes.append(
            f"{len(com_drift)} imagem(ns) com drift fora das caixas — veja os avisos "
            "de cada uma no relatório.")
    if manifest.fail_count:
        manifest.notes.append(
            f"{manifest.fail_count} imagem(ns) falharam e NÃO foram gravadas; as demais "
            "estão prontas. Corrija o erro e rode de novo: o lote retoma de onde parou.")
    if settings.dry_run:
        manifest.notes.append("execução de teste (dry_run): nenhum arquivo foi gravado.")
    else:
        try:
            manifest.write(recipe.output_dir / MANIFEST_FILENAME)
        except OSError as exc:
            log.warning("não consegui gravar o manifesto: %s", exc)
    return manifest


# --------------------------------------------------------------------------- #
# Variações (n saídas novas, não uma por entrada)
# --------------------------------------------------------------------------- #
_VARIATIONS_STATE_KEY = "__variations__"


def _run_variations(recipe: Recipe, settings: Settings, files: Sequence[Path], *,
                    progress: Callable[[int, int, str], None] | None,
                    force: bool = False) -> tuple[list[ImageResult], list[str]]:
    cfg = dict(recipe.variations or {})
    n = int(cfg.get("n") or 0)
    mode = str(cfg.get("mode") or "generative").strip().lower()
    notes: list[str] = []

    if n <= 0:
        raise PipelineError("'variations' precisa de 'n:' — quantas peças gerar (ex.: n: 30).")
    if mode == "template" and not files:
        raise PipelineError(
            f"o modo 'template' troca os textos dos SEUS criativos, e não achei nenhuma "
            f"imagem em {recipe.input_dir}.\n"
            f"  Coloque as referências na pasta ou use mode: hybrid / generative."
        )

    recipe.output_dir.mkdir(parents=True, exist_ok=True)
    sig = _recipe_signature(recipe, settings)
    state = _load_state(recipe.output_dir)

    # Retomada do caso caro: 30 imagens de IA custam dinheiro de verdade, então
    # um lote idêntico já entregue não é refeito sem 'force'. Aqui é tudo ou
    # nada — a IA não devolve a mesma peça duas vezes, e completar um lote pela
    # metade trocaria os ângulos de lugar.
    prev = state.get(_VARIATIONS_STATE_KEY)
    if not force and isinstance(prev, dict) and prev.get("recipe") == sig:
        antigos = [recipe.output_dir / str(nm) for nm in (prev.get("outputs") or [])]
        if antigos and all(p.exists() for p in antigos):
            notes.append(
                f"as {len(antigos)} variações deste lote já estavam prontas na pasta de "
                "saída (mesma receita, mesmas referências) e não foram geradas de novo. "
                "Use force=true para gerar outro conjunto.")
            return ([ImageResult(source=recipe.input_dir, output=p, ok=True, skipped=True,
                                 operations=["variação"],
                                 warnings=["reaproveitada da execução anterior"])
                     for p in antigos], notes)

    t0 = time.perf_counter()

    _tick(progress, 0, n + 1, f"analisando {len(files)} referência(s)")
    analyses = _vision.analyze_batch(files, settings,
                                     max_workers=max(1, int(settings.max_concurrency or 1)))
    dna = _vision.extract_dna(analyses, settings)
    if recipe.target is not None and not cfg.get("aspect"):
        cfg["aspect"] = recipe.target.label

    _variations.clear_variation_warnings()
    outs = _variations.generate_variations(
        dna, n, settings=settings, mode=mode,
        base_images=list(analyses) if files else None,
        copy_variants=cfg.get("copy"),
        aspect=cfg.get("aspect"),
        progress=lambda i, t, m: _tick(progress, i, n + 1, m),
    )

    results: list[ImageResult] = []
    fmt = str(recipe.deliver.get("format") or "png")
    fmt = {"jpg": "JPEG", "jpeg": "JPEG"}.get(fmt.lower(), fmt.upper())
    quality = int(recipe.deliver.get("quality") or 95)
    prefix = str(recipe.deliver.get("prefix") or "")
    suffix = str(recipe.deliver.get("suffix") or "")

    for k, (img, meta) in enumerate(outs, 1):
        stem = Path(str(meta.get("suggested_name") or f"var_{k:02d}.png")).stem
        out = recipe.output_dir / f"{prefix}{stem}{suffix}{_ext_for(fmt)}"
        base = meta.get("base") or ""
        res = ImageResult(
            source=Path(base) if base else recipe.input_dir,
            output=None if settings.dry_run else out,
            operations=[f"variação {meta.get('angle_label') or meta.get('angle')}"],
            engine_used=str(meta.get("engine") or ""),
            cost_usd=float(meta.get("cost_usd") or 0.0),
            warnings=list(meta.get("warnings") or []),
        )
        res.changed_boxes = [Box.from_any(b, img.width, img.height)
                             for b in (meta.get("changed_boxes") or [])]
        if meta.get("drift_pixels") is not None:
            res.drift_pixels = int(meta["drift_pixels"])
            res.untouched_pixels_verified = meta.get("untouched_pixels_verified")
        try:
            if not settings.dry_run:
                _io.save_image(img, out, fmt=fmt, quality=quality)
            res.ok = True
        except OSError as exc:
            res.ok = False
            res.error = str(exc)
        results.append(res)

    if not settings.dry_run:
        state[_VARIATIONS_STATE_KEY] = {
            "recipe": sig,
            "outputs": [Path(r.output).name for r in results if r.ok and r.output],
            "mode": mode,
            "at": _now(),
        }
        _save_state(recipe.output_dir, state)

    for w in _variations.variation_warnings():
        notes.append(w)
    if len(outs) < n:
        notes.append(f"pedi {n} variações e saíram {len(outs)}: as que falharam na IA "
                     "foram omitidas (o motivo está nos avisos).")
    if mode == "generative":
        notes.append("modo 'generative': o texto foi desenhado pelo modelo de imagem e "
                     "pode sair com erro de ortografia. Para texto sempre correto use "
                     "mode: hybrid (fundo por IA, texto por PIL) ou template.")
    notes.append(f"DNA extraído de {dna.sample_count} referência(s) em "
                 f"{time.perf_counter() - t0:.1f}s.")
    _tick(progress, n + 1, n + 1, f"{len(results)} variação(ões) prontas")
    return results, notes


# --------------------------------------------------------------------------- #
# Atalhos — todos montam a Recipe equivalente e caem no mesmo run_recipe
# --------------------------------------------------------------------------- #
def _common_parent(paths: Sequence[Path], fallback: Path) -> Path:
    dirs = {p.parent for p in paths}
    if len(dirs) == 1:
        return dirs.pop()
    if not dirs:
        return fallback
    try:
        return Path(os.path.commonpath([str(d) for d in dirs]))
    except ValueError:
        return fallback


def _ad_hoc_recipe(job: str, paths: Sequence[Path], out_dir: Any, settings: Settings,
                   *, operations: Sequence[EditOp] = (), **extra: Any) -> Recipe:
    """Receita montada em memória (sem YAML) para os atalhos do CLI."""
    items = [Path(p) for p in paths]
    return Recipe(
        job=job,
        input_dir=_common_parent(items, Path(settings.inbox)),
        output_dir=Path(out_dir),
        engine=extra.pop("engine", Engine.AUTO),
        operations=list(operations),
        deliver={"zip": False, "report": True, "contact_sheet": False,
                 "format": "png", "quality": 95, "suffix": "", "prefix": "",
                 **extra.pop("deliver", {})},
        raw={},
        **extra,
    )


def _opt_int(value: Any) -> int | None:
    """Inteiro quando veio algo utilizável, None quando não veio nada.

    None significa "deriva do maior lado da origem", que é o padrão do
    reenquadramento — por isso 0 e "" também viram None em vez de virarem 0.
    """
    if value in (None, "", 0):
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def run_reframe_batch(paths: Sequence[Any], target: Any, settings: Settings | None = None,
                      out_dir: Any = None, *, mode: str = "pad",
                      progress: Callable[[int, int, str], None] | None = None,
                      **kw: Any) -> JobManifest:
    """Reenquadra uma lista de imagens para ``target`` (ex.: ``'16:9'``).

    Atalho: monta a receita equivalente (``target:`` + ``reframe_mode:``) e
    chama :func:`run_recipe`. Nenhuma lógica de execução vive aqui.
    """
    settings = settings or load_settings()
    items = [Path(p) for p in paths]
    spec = target if isinstance(target, AspectSpec) else AspectSpec.parse(str(target))
    out = Path(out_dir) if out_dir else Path(settings.outbox) / f"reframe-{spec.ratio_w}x{spec.ratio_h}"
    recipe = _ad_hoc_recipe(
        f"reframe {spec.label}", items, out, settings,
        target=spec, reframe_mode=str(mode or "pad"),
        reframe_fill=kw.pop("fill", "blur"), reframe_prompt=kw.pop("prompt", None),
        long_edge=_opt_int(kw.pop("long_edge", None)),
    )
    return run_recipe(recipe, settings, progress=progress, paths=items,
                      force=kw.pop("force", None))


def run_variations_batch(paths: Sequence[Any], n: int, settings: Settings | None = None,
                         out_dir: Any = None, *, mode: str = "generative",
                         progress: Callable[[int, int, str], None] | None = None,
                         **kw: Any) -> JobManifest:
    """Gera ``n`` criativos novos no padrão das referências em ``paths``."""
    settings = settings or load_settings()
    items = [Path(p) for p in paths]
    out = Path(out_dir) if out_dir else Path(settings.outbox) / "variacoes"
    aspect = kw.pop("aspect", None)
    recipe = _ad_hoc_recipe(
        f"variações ({mode})", items, out, settings,
        variations={"n": int(n), "mode": str(mode or "generative"),
                    "aspect": str(aspect) if aspect else None,
                    "copy": kw.pop("copy", None)},
    )
    return run_recipe(recipe, settings, progress=progress, paths=items)


def run_replace_text_batch(paths: Sequence[Any], find: str | None, replace: str,
                           settings: Settings | None = None, out_dir: Any = None, *,
                           role: Any = None, box: Any = None,
                           progress: Callable[[int, int, str], None] | None = None,
                           **kw: Any) -> JobManifest:
    """O caso central: troca o mesmo texto (CTA) em N imagens, sem mexer no resto.

    Pelo menos um entre ``find``, ``role`` e ``box`` precisa vir — é por ele que
    o bloco é localizado. Com ``box`` explícito o caminho é 100% offline.
    """
    settings = settings or load_settings()
    items = [Path(p) for p in paths]
    if not (find or role or box):
        raise PipelineError(
            "diga QUAL texto trocar: passe find='TEXTO ATUAL', role='cta' ou "
            "box={'x':...,'y':...,'w':...,'h':...}."
        )
    params: dict[str, Any] = {"replace": str(replace)}
    if find:
        params["find"] = str(find)
    if role is not None:
        params["role"] = role.value if isinstance(role, TextRole) else str(role)
    if box is not None:
        params["box"] = box
    if kw.get("style"):
        params["style"] = kw.pop("style")
    senao = kw.pop("senao_adicionar", None)
    if senao:
        params["senao_adicionar"] = senao
    params["match"] = str(kw.pop("match", "fuzzy"))

    out = Path(out_dir) if out_dir else Path(settings.outbox) / "troca-de-texto"
    op = EditOp(kind=OpKind.REPLACE_TEXT, params=params, engine=Engine.DETERMINISTIC)
    recipe = _ad_hoc_recipe("troca de texto", items, out, settings,
                            operations=[op], engine=Engine.DETERMINISTIC)
    return run_recipe(recipe, settings, progress=progress, paths=items,
                      force=kw.pop("force", None))


# --------------------------------------------------------------------------- #
# Teste de fumaça: python -m s7editor.pipeline
# --------------------------------------------------------------------------- #
def _demo_batch(folder: Path, n: int = 3) -> list[Path]:
    """Cria criativos sintéticos com headline e CTA em pastilha chapada."""
    from PIL import ImageDraw

    folder.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for i in range(n):
        w, h = 720, 1280
        img = Image.new("RGB", (w, h), (250, 250, 248))
        d = ImageDraw.Draw(img)
        for y in range(int(h * 0.55)):
            t = y / (h * 0.55)
            d.line([(0, y), (w, y)], fill=(int(20 + 60 * t), int(40 + 40 * t), int(110 - 30 * t)))
        cta = Box(int(w * 0.20), int(h * 0.80), int(w * 0.60), int(h * 0.07))
        d.rectangle(list(cta.xyxy), fill=(240, 92, 30))
        spec = FontSpec(family="Inter", weight="bold", size_px=int(h * 0.032),
                        color=(255, 255, 255), align="center", valign="middle")
        img, _ = _textedit.add_text(img, cta, "SAIBA MAIS", spec)
        p = folder / f"criativo_{i + 1:02d}.png"
        _io.save_image(img, p, fmt="PNG")
        out.append(p)
    return out


def _smoke_test() -> int:  # pragma: no cover - roda na mão
    import shutil
    import tempfile

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    tmp = Path(tempfile.mkdtemp(prefix="s7pipe-"))
    falhas = 0
    try:
        inbox = tmp / "inbox"
        outbox = tmp / "outbox"
        srcs = _demo_batch(inbox, 3)
        settings = load_settings(root=tmp, inbox=inbox, outbox=outbox,
                                 cache_dir=tmp / ".cache", max_concurrency=3)

        # 1) o caso central: trocar o CTA sem mexer em mais nada
        cta_box = {"x": 0.20, "y": 0.80, "w": 0.60, "h": 0.07, "norm": True}
        m = run_replace_text_batch(srcs, None, "QUERO AGORA", settings, outbox / "cta",
                                   box=cta_box,
                                   progress=lambda i, t, s: print(f"  [{i}/{t}] {s}"))
        print(f"\ntroca de CTA: ok={m.ok_count} falhas={m.fail_count} "
              f"custo=US$ {m.total_cost_usd:.4f}")
        for r in m.results:
            print(f"  {r.source.name}: drift={r.drift_pixels} "
                  f"verificado={r.untouched_pixels_verified} caixas={len(r.changed_boxes)}")
            if not r.ok:
                print(f"    ERRO: {r.error}")
            for w in r.warnings:
                print(f"    aviso: {w}")
        if m.ok_count != 3 or any(r.drift_pixels for r in m.results):
            falhas += 1
            print("  FALHA: o lote não entregou 3 imagens com drift zero")
        if not all(r.untouched_pixels_verified for r in m.results):
            falhas += 1
            print("  FALHA: a garantia não foi verificada em todas")

        # 2) retomada: rodar de novo pula tudo
        m2 = run_replace_text_batch(srcs, None, "QUERO AGORA", settings, outbox / "cta",
                                    box=cta_box)
        pulou = sum(1 for r in m2.results if r.skipped)
        print(f"\nretomada: {pulou}/3 puladas")
        if pulou != 3:
            falhas += 1
            print("  FALHA: a retomada não reaproveitou as imagens")

        # 3) receita diferente invalida a retomada
        m3 = run_replace_text_batch(srcs, None, "OUTRO TEXTO", settings, outbox / "cta",
                                    box=cta_box)
        if any(r.skipped for r in m3.results):
            falhas += 1
            print("  FALHA: mudou o texto da receita e o lote reaproveitou o arquivo velho")
        else:
            print("mudança de receita: refez as 3 (correto)")

        # 4) uma imagem quebrada não derruba o lote
        ruim = inbox / "quebrada.png"
        ruim.write_bytes(b"isto nao e um png")
        m4 = run_replace_text_batch(list(srcs) + [ruim], None, "TESTE", settings,
                                    outbox / "misto", box=cta_box)
        print(f"\nlote com 1 arquivo corrompido: ok={m4.ok_count} falhas={m4.fail_count}")
        if m4.ok_count != 3 or m4.fail_count != 1:
            falhas += 1
            print("  FALHA: o arquivo ruim deveria falhar sozinho")

        # 5) reframe 9:16 -> 16:9 (offline, modo pad)
        m5 = run_reframe_batch(srcs, "16:9", settings, outbox / "wide", mode="pad")
        r0 = m5.results[0]
        img0 = _io.load_image(r0.output) if r0.output else None
        print(f"\nreframe: ok={m5.ok_count} tamanho={img0.size if img0 else '?'} "
              f"verificado={r0.untouched_pixels_verified}")
        if m5.ok_count != 3 or (img0 and abs(img0.width / img0.height - 16 / 9) > 0.01):
            falhas += 1
            print("  FALHA: o reframe não entregou 16:9")

        # 6) política de formato: JPEG avisa e nunca diz "verificado"
        jpg_dir = outbox / "jpg"
        rec = _ad_hoc_recipe(
            "cta em jpeg", srcs, jpg_dir, settings,
            operations=[EditOp(kind=OpKind.REPLACE_TEXT,
                               params={"box": cta_box, "replace": "EM JPEG"},
                               engine=Engine.DETERMINISTIC)],
            deliver={"format": "jpg", "quality": 92})
        m6 = run_recipe(rec, settings, paths=srcs)
        r = m6.results[0]
        print(f"\nJPEG: verificado={r.untouched_pixels_verified} "
              f"drift_tolerante={r.drift_pixels}")
        if r.untouched_pixels_verified is not None:
            falhas += 1
            print("  FALHA: JPEG jamais pode reportar a garantia como verificada")
        if not any("perdas" in w for w in r.warnings):
            falhas += 1
            print("  FALHA: faltou o aviso sobre a recodificação com perdas")

        # 7) pasta vazia => erro em português, sem traceback
        try:
            run_replace_text_batch([], None, "x", settings, outbox / "vazio", box=cta_box)
        except PipelineError as exc:
            print(f"\npasta vazia: {str(exc).splitlines()[0]}")
        else:
            falhas += 1
            print("  FALHA: pasta vazia deveria levantar PipelineError")

        print(f"\n{'TUDO OK' if not falhas else f'{falhas} FALHA(S)'}")
        return 1 if falhas else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_smoke_test())
