"""Contrato de dados do S7 Editor.

Todos os módulos falam esta linguagem. Nada aqui depende de PIL, OpenAI ou
qualquer coisa pesada — são só dataclasses puras + helpers de geometria, para
que possam ser importadas de qualquer lugar sem custo.

Convenção de coordenadas
------------------------
`Box` guarda pixels inteiros (x, y, w, h) com origem no canto superior
esquerdo. Receitas em YAML usam caixas *normalizadas* (0.0–1.0) porque o mesmo
criativo aparece em tamanhos diferentes; `Box.from_norm` converte.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    "Box", "FontSpec", "TextRole", "TextBlock", "BackgroundKind",
    "CreativeAnalysis", "CreativeDNA", "OpKind", "EditOp", "Engine",
    "ImageResult", "JobManifest", "AspectSpec",
    "parse_color", "color_to_hex",
]


# --------------------------------------------------------------------------- #
# Geometria
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Box:
    """Retângulo em pixels inteiros."""

    x: int
    y: int
    w: int
    h: int

    # -- construtores ------------------------------------------------------ #
    @classmethod
    def from_norm(cls, x: float, y: float, w: float, h: float, img_w: int, img_h: int) -> "Box":
        """Caixa normalizada (0–1) -> pixels, com clamp nos limites da imagem."""
        px = int(round(x * img_w))
        py = int(round(y * img_h))
        pw = int(round(w * img_w))
        ph = int(round(h * img_h))
        return cls(px, py, pw, ph).clamp(img_w, img_h)

    @classmethod
    def from_xyxy(cls, x0: int, y0: int, x1: int, y1: int) -> "Box":
        return cls(int(min(x0, x1)), int(min(y0, y1)), int(abs(x1 - x0)), int(abs(y1 - y0)))

    @classmethod
    def from_any(cls, raw: Any, img_w: int, img_h: int) -> "Box":
        """Aceita dict normalizado, dict em pixels, [x,y,w,h] ou Box."""
        if isinstance(raw, Box):
            return raw.clamp(img_w, img_h)
        if isinstance(raw, (list, tuple)) and len(raw) == 4:
            raw = {"x": raw[0], "y": raw[1], "w": raw[2], "h": raw[3]}
        if not isinstance(raw, dict):
            raise ValueError(f"caixa inválida: {raw!r}")
        vals = [raw.get(k, 0) for k in ("x", "y", "w", "h")]
        # Heurística: os quatro valores dentro de [0, 1] => normalizado. Uma caixa
        # de 1x1 pixel nunca é um pedido real, então não há ambiguidade prática.
        # Receitas geradas por nós sempre gravam "norm": true, que tem prioridade.
        looks_norm = all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and -0.001 <= float(v) <= 1.001
            for v in vals
        )
        if raw.get("norm") is True or (looks_norm and raw.get("norm") is not False):
            return cls.from_norm(float(vals[0]), float(vals[1]), float(vals[2]), float(vals[3]), img_w, img_h)
        return cls(int(vals[0]), int(vals[1]), int(vals[2]), int(vals[3])).clamp(img_w, img_h)

    # -- propriedades ------------------------------------------------------ #
    @property
    def x1(self) -> int:
        return self.x + self.w

    @property
    def y1(self) -> int:
        return self.y + self.h

    @property
    def xyxy(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x1, self.y1)

    @property
    def area(self) -> int:
        return max(0, self.w) * max(0, self.h)

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    # -- operações --------------------------------------------------------- #
    def clamp(self, img_w: int, img_h: int) -> "Box":
        x = max(0, min(int(self.x), img_w))
        y = max(0, min(int(self.y), img_h))
        w = max(0, min(int(self.w), img_w - x))
        h = max(0, min(int(self.h), img_h - y))
        return Box(x, y, w, h)

    def pad(self, px: int, img_w: int | None = None, img_h: int | None = None) -> "Box":
        b = Box(self.x - px, self.y - px, self.w + 2 * px, self.h + 2 * px)
        return b.clamp(img_w, img_h) if img_w and img_h else b

    def scale(self, fx: float, fy: float | None = None) -> "Box":
        fy = fx if fy is None else fy
        return Box(int(round(self.x * fx)), int(round(self.y * fy)),
                   int(round(self.w * fx)), int(round(self.h * fy)))

    def union(self, other: "Box") -> "Box":
        return Box.from_xyxy(min(self.x, other.x), min(self.y, other.y),
                             max(self.x1, other.x1), max(self.y1, other.y1))

    def intersects(self, other: "Box") -> bool:
        return not (self.x1 <= other.x or other.x1 <= self.x or self.y1 <= other.y or other.y1 <= self.y)

    def iou(self, other: "Box") -> float:
        if not self.intersects(other):
            return 0.0
        ix = min(self.x1, other.x1) - max(self.x, other.x)
        iy = min(self.y1, other.y1) - max(self.y, other.y)
        inter = ix * iy
        union = self.area + other.area - inter
        return inter / union if union else 0.0

    def to_norm(self, img_w: int, img_h: int) -> dict[str, float]:
        return {"x": round(self.x / img_w, 5), "y": round(self.y / img_h, 5),
                "w": round(self.w / img_w, 5), "h": round(self.h / img_h, 5), "norm": True}

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


# --------------------------------------------------------------------------- #
# Tipografia
# --------------------------------------------------------------------------- #
@dataclass
class FontSpec:
    """Estilo tipográfico de um bloco de texto, o suficiente para redesenhá-lo."""

    family: str = "Inter"
    weight: str = "bold"          # thin|light|regular|medium|semibold|bold|black
    italic: bool = False
    size_px: int = 48
    color: tuple[int, int, int] = (255, 255, 255)
    letter_spacing: float = 0.0   # em px, pode ser negativo
    line_height: float = 1.2      # múltiplo de size_px
    align: str = "center"         # left|center|right
    valign: str = "middle"        # top|middle|bottom
    uppercase: bool = False
    stroke_width: int = 0
    stroke_color: tuple[int, int, int] | None = None
    shadow: bool = False
    shadow_color: tuple[int, int, int] = (0, 0, 0)
    shadow_offset: tuple[int, int] = (0, 2)
    shadow_blur: int = 4
    opacity: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FontSpec":
        known = {f for f in cls.__dataclass_fields__}  # noqa: F821
        clean: dict[str, Any] = {}
        for k, v in (d or {}).items():
            if k not in known:
                continue
            if k in ("color", "stroke_color", "shadow_color") and isinstance(v, str):
                v = parse_color(v)
            if k in ("color", "stroke_color", "shadow_color") and isinstance(v, list):
                v = tuple(int(c) for c in v[:3])
            if k == "shadow_offset" and isinstance(v, list):
                v = (int(v[0]), int(v[1]))
            clean[k] = v
        return cls(**clean)


def parse_color(value: Any) -> tuple[int, int, int]:
    """'#ff0044' | 'ff0044' | [255,0,68] | (255,0,68) -> (255, 0, 68)."""
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        return (int(value[0]), int(value[1]), int(value[2]))
    if isinstance(value, str):
        s = value.strip().lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        if len(s) >= 6:
            try:
                return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
            except ValueError:
                pass
    return (0, 0, 0)


def color_to_hex(rgb: Iterable[int]) -> str:
    r, g, b = list(rgb)[:3]
    return "#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b))


class TextRole(str, Enum):
    HEADLINE = "headline"
    SUBHEAD = "subhead"
    CTA = "cta"
    PRICE = "price"
    BADGE = "badge"
    LEGAL = "legal"
    LOGO = "logo"
    OTHER = "other"


@dataclass
class TextBlock:
    """Um bloco de texto localizado dentro de um criativo."""

    box: Box
    text: str = ""
    role: TextRole = TextRole.OTHER
    style: FontSpec = field(default_factory=FontSpec)
    background_color: tuple[int, int, int] | None = None   # cor sólida atrás do texto, se houver
    on_solid_background: bool = False                      # True => apagar é trivial e exato
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "box": self.box.to_dict(),
            "text": self.text,
            "role": self.role.value if isinstance(self.role, TextRole) else str(self.role),
            "style": self.style.to_dict(),
            "background_color": list(self.background_color) if self.background_color else None,
            "on_solid_background": self.on_solid_background,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any], img_w: int, img_h: int) -> "TextBlock":
        role_raw = (d.get("role") or "other").lower()
        try:
            role = TextRole(role_raw)
        except ValueError:
            role = TextRole.OTHER
        bg = d.get("background_color")
        return cls(
            box=Box.from_any(d.get("box") or d.get("bbox") or {}, img_w, img_h),
            text=str(d.get("text") or ""),
            role=role,
            style=FontSpec.from_dict(d.get("style") or {}),
            background_color=parse_color(bg) if bg else None,
            on_solid_background=bool(d.get("on_solid_background", False)),
            confidence=float(d.get("confidence") or 0.0),
        )


# --------------------------------------------------------------------------- #
# Análise de criativo
# --------------------------------------------------------------------------- #
class BackgroundKind(str, Enum):
    SOLID = "solid"          # cor chapada -> apagar texto é pixel-perfeito
    GRADIENT = "gradient"    # degradê suave -> reconstrução analítica
    PHOTO = "photo"          # foto/textura -> inpaint ou IA
    PATTERN = "pattern"
    MIXED = "mixed"


@dataclass
class CreativeAnalysis:
    """O que sabemos sobre um criativo depois de olhá-lo."""

    path: Path
    width: int
    height: int
    text_blocks: list[TextBlock] = field(default_factory=list)
    palette: list[tuple[int, int, int]] = field(default_factory=list)
    background_kind: BackgroundKind = BackgroundKind.MIXED
    layout_archetype: str = ""       # ex.: "foto full-bleed + faixa inferior"
    subject_description: str = ""
    safe_areas: list[Box] = field(default_factory=list)   # regiões a nunca tocar (logo, rosto, produto)
    notes: str = ""
    source: str = "vision"           # vision | cache | manual | heuristic

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 1.0

    def block_by_role(self, role: TextRole) -> TextBlock | None:
        for b in self.text_blocks:
            if b.role == role:
                return b
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "width": self.width,
            "height": self.height,
            "text_blocks": [b.to_dict() for b in self.text_blocks],
            "palette": [color_to_hex(c) for c in self.palette],
            "background_kind": self.background_kind.value,
            "layout_archetype": self.layout_archetype,
            "subject_description": self.subject_description,
            "safe_areas": [b.to_dict() for b in self.safe_areas],
            "notes": self.notes,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CreativeAnalysis":
        w, h = int(d.get("width") or 0), int(d.get("height") or 0)
        try:
            bk = BackgroundKind(str(d.get("background_kind") or "mixed").lower())
        except ValueError:
            bk = BackgroundKind.MIXED
        return cls(
            path=Path(str(d.get("path") or "")),
            width=w,
            height=h,
            text_blocks=[TextBlock.from_dict(b, w, h) for b in (d.get("text_blocks") or [])],
            palette=[parse_color(c) for c in (d.get("palette") or [])],
            background_kind=bk,
            layout_archetype=str(d.get("layout_archetype") or ""),
            subject_description=str(d.get("subject_description") or ""),
            safe_areas=[Box.from_any(b, w, h) for b in (d.get("safe_areas") or [])],
            notes=str(d.get("notes") or ""),
            source=str(d.get("source") or "vision"),
        )


@dataclass
class CreativeDNA:
    """Padrão extraído de um conjunto de referências, usado para gerar novos."""

    palette: list[tuple[int, int, int]] = field(default_factory=list)
    fonts: list[str] = field(default_factory=list)
    layout_archetype: str = ""
    subject_matter: str = ""
    mood: str = ""
    copy_patterns: list[str] = field(default_factory=list)
    cta_patterns: list[str] = field(default_factory=list)
    logo_placement: str = ""
    aspect: str = "9:16"
    do_not: list[str] = field(default_factory=list)
    prompt_seed: str = ""
    sample_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["palette"] = [color_to_hex(c) for c in self.palette]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CreativeDNA":
        known = {f for f in cls.__dataclass_fields__}  # noqa: F821
        clean = {k: v for k, v in (d or {}).items() if k in known}
        clean["palette"] = [parse_color(c) for c in (clean.get("palette") or [])]
        return cls(**clean)


# --------------------------------------------------------------------------- #
# Operações / receita
# --------------------------------------------------------------------------- #
class OpKind(str, Enum):
    REPLACE_TEXT = "replace_text"
    REMOVE_TEXT = "remove_text"
    ADD_TEXT = "add_text"
    REPLACE_COLOR = "replace_color"
    REPLACE_REGION = "replace_region"     # IA dentro de máscara, resto intacto
    REMOVE_OBJECT = "remove_object"
    REFRAME = "reframe"
    OVERLAY = "overlay"                   # logo/selo PNG
    RESIZE = "resize"
    EXPORT = "export"
    REDO = "refazer"


class Engine(str, Enum):
    DETERMINISTIC = "deterministic"   # nunca chama IA: pixels fora da caixa idênticos
    AI = "ai"                         # usa gpt-image-1
    AUTO = "auto"                     # tenta determinístico, cai pra IA se o fundo exigir


@dataclass
class EditOp:
    """Uma operação de edição. `params` é validado por quem executa."""

    kind: OpKind
    params: dict[str, Any] = field(default_factory=dict)
    engine: Engine = Engine.AUTO
    scope: str = "all"        # "all" | glob de nome de arquivo | "1,3,5" índices
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.kind.value, "engine": self.engine.value,
                "scope": self.scope, "enabled": self.enabled, **self.params}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EditOp":
        d = dict(d or {})
        raw_kind = str(d.pop("type", d.pop("kind", "")) or "").lower()
        try:
            kind = OpKind(raw_kind)
        except ValueError as exc:
            valid = ", ".join(k.value for k in OpKind)
            raise ValueError(f"operação desconhecida: {raw_kind!r}. Use uma de: {valid}") from exc
        engine_raw = str(d.pop("engine", "auto") or "auto").lower()
        try:
            engine = Engine(engine_raw)
        except ValueError as exc:
            raise ValueError(f"engine inválida: {engine_raw!r} (deterministic|ai|auto)") from exc
        scope = str(d.pop("scope", "all") or "all")
        enabled = bool(d.pop("enabled", True))
        return cls(kind=kind, params=d, engine=engine, scope=scope, enabled=enabled)


@dataclass(frozen=True)
class AspectSpec:
    """Formato de saída: '16:9', '1080x1920', '9:16@1080'."""

    ratio_w: int
    ratio_h: int
    width: int | None = None
    height: int | None = None

    @property
    def ratio(self) -> float:
        return self.ratio_w / self.ratio_h

    @property
    def label(self) -> str:
        return f"{self.ratio_w}:{self.ratio_h}"

    def resolve(self, long_edge: int = 1440) -> tuple[int, int]:
        """Dimensões finais em pixels, preservando exatamente a razão pedida.

        Se a spec já traz largura/altura explícitas ('1080x1920' ou '9:16@1080'),
        elas mandam e `long_edge` é ignorado.
        """
        if self.width and self.height:
            return (int(self.width), int(self.height))
        if self.ratio >= 1:
            w = int(long_edge)
            h = int(round(w * self.ratio_h / self.ratio_w))
        else:
            h = int(long_edge)
            w = int(round(h * self.ratio_w / self.ratio_h))
        return (w - w % 2, h - h % 2)

    @classmethod
    def parse(cls, text: str) -> "AspectSpec":
        s = str(text).strip().lower().replace(" ", "")
        size_part = None
        if "@" in s:
            s, size_part = s.split("@", 1)
        if "x" in s and ":" not in s:
            w, h = s.split("x", 1)
            wi, hi = int(w), int(h)
            g = _gcd(wi, hi) or 1
            return cls(wi // g, hi // g, wi, hi)
        if ":" in s:
            a, b = s.split(":", 1)
            rw, rh = int(a), int(b)
            if size_part:
                w = int(size_part)
                h = int(round(w * rh / rw))
                return cls(rw, rh, w - w % 2, h - h % 2)
            return cls(rw, rh)
        raise ValueError(f"formato inválido: {text!r} (use '16:9', '1080x1920' ou '9:16@1080')")


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return abs(a)


# --------------------------------------------------------------------------- #
# Resultados
# --------------------------------------------------------------------------- #
@dataclass
class ImageResult:
    """O que aconteceu com uma imagem no lote."""

    source: Path
    output: Path | None = None
    ok: bool = False
    skipped: bool = False
    operations: list[str] = field(default_factory=list)
    engine_used: str = ""
    changed_boxes: list[Box] = field(default_factory=list)
    untouched_pixels_verified: bool | None = None   # None = não checado
    drift_pixels: int = 0                           # nº de pixels alterados fora das caixas
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    cost_usd: float = 0.0
    duration_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": str(self.source),
            "output": str(self.output) if self.output else None,
            "ok": self.ok,
            "skipped": self.skipped,
            "operations": self.operations,
            "engine_used": self.engine_used,
            "changed_boxes": [b.to_dict() for b in self.changed_boxes],
            "untouched_pixels_verified": self.untouched_pixels_verified,
            "drift_pixels": self.drift_pixels,
            "warnings": self.warnings,
            "error": self.error,
            "cost_usd": round(self.cost_usd, 4),
            "duration_s": round(self.duration_s, 2),
        }


@dataclass
class JobManifest:
    """Registro completo de um lote — vira manifest.json ao lado do ZIP."""

    job: str
    recipe_path: str = ""
    input_dir: str = ""
    output_dir: str = ""
    started_at: str = ""
    finished_at: str = ""
    results: list[ImageResult] = field(default_factory=list)
    total_cost_usd: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.ok and not r.skipped)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job": self.job,
            "recipe_path": self.recipe_path,
            "input_dir": self.input_dir,
            "output_dir": self.output_dir,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "ok": self.ok_count,
            "failed": self.fail_count,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "results": [r.to_dict() for r in self.results],
            "notes": self.notes,
        }

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path
