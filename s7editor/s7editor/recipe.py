"""Receita YAML — a interface principal do S7 Editor.

O usuário descreve o lote inteiro num arquivo de texto e nós garantimos que
ele nunca rode um lote de 30 imagens com um erro de digitação silencioso.

Formato canônico::

    job: trocar-cta-setembro
    input: inbox/campanha-agosto
    output: outbox/campanha-setembro
    engine: deterministic
    operations:
      - type: replace_text
        find: "GARANTA O SEU"
        replace: "ULTIMAS VAGAS"
        match: fuzzy
      - type: replace_text
        role: cta
        replace: "COMPRE AGORA"
        scope: "*.png"
      - type: replace_text
        box: {x: 0.1, y: 0.82, w: 0.8, h: 0.07, norm: true}
        replace: "FRETE GRATIS"
        style: {color: "#ffffff", weight: bold, uppercase: true}
    target: "16:9"          # opcional - reenquadra tudo no fim
    reframe_mode: relayout
    deliver:
      zip: true
      report: true

Três decisões que valem explicar:

1. **Caminhos relativos resolvem a partir de ``settings.root``**, nunca do
   ``cwd``. A receita fica versionada junto do projeto; se o usuário rodar o
   CLI de dentro de ``~/Downloads`` o lote tem que apontar para as mesmas
   pastas de sempre.
2. **Validação antes de qualquer I/O de imagem.** :func:`validate_recipe`
   devolve *todos* os erros de uma vez, em português, apontando linha e campo —
   ninguém merece descobrir o terceiro erro de digitação na terceira execução.
3. **``engine`` do topo é herdada pelas operações** que não declaram a sua.
   Escrever ``engine: deterministic`` uma vez no topo tem que travar o lote
   inteiro na trilha offline, senão a garantia de zero drift vira loteria.
"""
from __future__ import annotations

import difflib
import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

from .models import AspectSpec, EditOp, Engine, OpKind

__all__ = [
    "Recipe",
    "RecipeError",
    "load_recipe",
    "validate_recipe",
    "matches_scope",
    "EXAMPLE_RECIPES",
    "write_example",
    "REFRAME_MODES",
    "VARIATION_MODES",
    "MATCH_MODES",
    "DELIVER_FORMATS",
]


# --------------------------------------------------------------------------- #
# Vocabulários aceitos
# --------------------------------------------------------------------------- #
REFRAME_MODES: tuple[str, ...] = ("pad", "outpaint", "relayout", "crop")
VARIATION_MODES: tuple[str, ...] = ("generative", "remix", "copy", "hybrid")
MATCH_MODES: tuple[str, ...] = ("fuzzy", "exact")
DELIVER_FORMATS: tuple[str, ...] = ("png", "jpg", "jpeg", "webp")
FILL_MODES: tuple[str, ...] = ("blur", "mirror", "color", "white", "black")

# Espelha fonts.WEIGHT_SCALE/WEIGHT_ALIASES sem importar o módulo (que carrega
# PIL e varre o disco atrás de fontes). Se fonts.py ganhar um peso novo, some
# aqui também — a validação é só uma rede de proteção contra erro de digitação.
_WEIGHTS: frozenset[str] = frozenset({
    "thin", "extralight", "light", "regular", "medium", "semibold",
    "bold", "extrabold", "black",
    "hairline", "ultralight", "book", "normal", "roman", "text", "demi",
    "demibold", "ultrabold", "heavy", "ultra", "ultrablack", "fat", "poster",
})
_ALIGNS: frozenset[str] = frozenset({"left", "center", "right"})
_VALIGNS: frozenset[str] = frozenset({"top", "middle", "bottom"})

# Cores por nome: o usuário escreve "branco" e a gente entrega #ffffff. Sem
# isto, models.parse_color("branco") devolveria preto silenciosamente — o pior
# tipo de bug, porque o lote roda inteiro e sai errado.
NAMED_COLORS: dict[str, str] = {
    "branco": "#ffffff", "white": "#ffffff",
    "preto": "#000000", "black": "#000000",
    "vermelho": "#e01b24", "red": "#e01b24",
    "verde": "#2ec27e", "green": "#2ec27e",
    "azul": "#1c71d8", "blue": "#1c71d8",
    "amarelo": "#f6d32d", "yellow": "#f6d32d",
    "laranja": "#ff7800", "orange": "#ff7800",
    "roxo": "#9141ac", "purple": "#9141ac",
    "rosa": "#ff70a6", "pink": "#ff70a6",
    "cinza": "#77767b", "gray": "#77767b", "grey": "#77767b",
    "transparente": "#00000000", "transparent": "#00000000",
}

_RE_HEX = re.compile(r"^#?(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


class RecipeError(ValueError):
    """Receita inválida ou ilegível. A mensagem já é o texto para o usuário."""


# --------------------------------------------------------------------------- #
# Aliases de campo (o usuário escreve em português ou abrevia)
# --------------------------------------------------------------------------- #
_TOP_ALIASES: dict[str, str] = {
    "name": "job", "nome": "job", "titulo": "job", "título": "job",
    "input_dir": "input", "inbox": "input", "entrada": "input",
    "pasta": "input", "from": "input", "src": "input", "source": "input",
    "output_dir": "output", "outbox": "output", "saida": "output",
    "saída": "output", "dest": "output", "destino": "output", "to": "output",
    "ops": "operations", "operacoes": "operations", "operações": "operations",
    "motor": "engine",
    "aspect": "target", "formato": "target", "ratio": "target",
    "modo_reframe": "reframe_mode", "reframe": "reframe_mode",
    "preenchimento": "reframe_fill", "fill": "reframe_fill",
    "delivery": "deliver", "entrega": "deliver",
    "variacoes": "variations", "variações": "variations",
    "notas": "notes", "descricao": "notes", "descrição": "notes",
    "recursivo": "recursive",
    "qualidade": "quality",
    "lado_maior": "long_edge",
}

_TOP_KNOWN: frozenset[str] = frozenset({
    "job", "input", "output", "engine", "operations", "target",
    "reframe_mode", "reframe_fill", "reframe_prompt", "long_edge",
    "deliver", "variations", "notes", "recursive", "quality", "version",
})

# Chaves comuns a qualquer operação.
_OP_COMMON: frozenset[str] = frozenset({"type", "engine", "scope", "enabled", "note"})

_OP_COMMON_ALIASES: dict[str, str] = {
    "kind": "type", "tipo": "type", "op": "type",
    "escopo": "scope", "arquivos": "scope", "files": "scope",
    "ativo": "enabled", "ativa": "enabled", "on": "enabled",
    "motor": "engine",
    "comentario": "note", "comentário": "note", "comment": "note",
}

# Por operação: aliases de parâmetro, obrigatórios, "pelo menos um de", e o
# conjunto completo de chaves conhecidas (usado só para sugerir correção de
# digitação — chave desconhecida que não parece typo é ignorada, porque quem
# executa a operação pode aceitar mais parâmetros do que este módulo conhece).
_OP_SPEC: dict[str, dict[str, Any]] = {
    "replace_text": {
        "aliases": {
            "text": "replace", "to": "replace", "new": "replace",
            "new_text": "replace", "novo": "replace", "novo_texto": "replace",
            "para": "replace", "texto": "replace",
            "search": "find", "procurar": "find", "de": "find",
            "old": "find", "antigo": "find", "texto_atual": "find",
            "papel": "role", "caixa": "box", "estilo": "style",
            "modo": "match", "match_mode": "match", "casamento": "match",
            "auto_fit": "autofit", "ajustar": "autofit",
            "linhas": "max_lines", "max_linhas": "max_lines",
            "crescer_caixa": "grow_box", "grow": "grow_box",
        },
        "requires": ["replace"],
        "requires_any": [(("find", "role", "box"),
                          "precisa de 'find', 'role' ou 'box' para saber qual texto trocar")],
        "known": {"find", "role", "box", "replace", "match", "style",
                  "autofit", "max_lines", "grow_box"},
    },
    "remove_text": {
        "aliases": {
            "search": "find", "procurar": "find", "texto": "find",
            "papel": "role", "caixa": "box", "modo": "match",
        },
        "requires": [],
        "requires_any": [(("find", "role", "box"),
                          "precisa de 'find', 'role' ou 'box' para saber qual texto apagar")],
        "known": {"find", "role", "box", "match", "feather"},
    },
    "add_text": {
        "aliases": {
            "texto": "text", "caixa": "box", "estilo": "style",
            "papel": "role", "content": "text", "conteudo": "text",
        },
        "requires": ["box", "text"],
        "requires_any": [],
        "known": {"box", "text", "style", "role", "max_lines", "autofit"},
    },
    "replace_color": {
        "aliases": {
            "from_color": "from", "to_color": "to", "de": "from", "para": "to",
            "source": "from", "target": "to", "old": "from", "new": "to",
            "tolerancia": "tolerance", "tolerância": "tolerance",
            "caixa": "box",
        },
        "requires": ["from", "to"],
        "requires_any": [],
        "known": {"from", "to", "tolerance", "box"},
    },
    "replace_region": {
        "aliases": {"caixa": "box", "descricao": "prompt", "descrição": "prompt",
                    "instrucao": "prompt", "instrução": "prompt"},
        "requires": ["box", "prompt"],
        "requires_any": [],
        "known": {"box", "prompt", "feather", "strength"},
    },
    "remove_object": {
        "aliases": {"caixa": "box", "objeto": "find", "object": "find",
                    "describe": "find", "description": "find", "descricao": "find"},
        "requires": [],
        "requires_any": [(("box", "find"),
                          "precisa de 'box' ou 'find' para saber o que remover")],
        "known": {"box", "find", "prompt", "feather"},
    },
    "reframe": {
        "aliases": {"to": "target", "aspect": "target", "formato": "target",
                    "modo": "mode", "preenchimento": "fill",
                    "lado_maior": "long_edge"},
        "requires": ["target"],
        "requires_any": [],
        "known": {"target", "mode", "fill", "prompt", "long_edge"},
    },
    "overlay": {
        "aliases": {"file": "image", "path": "image", "arquivo": "image",
                    "imagem": "image", "logo": "image", "caixa": "box",
                    "posicao": "position", "posição": "position",
                    "opacidade": "opacity", "margem": "margin", "escala": "scale"},
        "requires": ["image"],
        "requires_any": [],
        "known": {"image", "box", "position", "opacity", "scale", "margin"},
    },
    "resize": {
        "aliases": {"largura": "width", "altura": "height", "escala": "scale",
                    "lado_maior": "long_edge", "w": "width", "h": "height"},
        "requires": [],
        "requires_any": [(("width", "height", "scale", "long_edge"),
                          "precisa de 'width'/'height', 'scale' ou 'long_edge'")],
        "known": {"width", "height", "scale", "long_edge", "keep_aspect"},
    },
    "export": {
        "aliases": {"fmt": "format", "formato": "format",
                    "qualidade": "quality", "sufixo": "suffix", "prefixo": "prefix"},
        "requires": [],
        "requires_any": [],
        "known": {"format", "quality", "suffix", "prefix"},
    },
}

_DELIVER_ALIASES: dict[str, str] = {
    "zipar": "zip", "compactar": "zip", "zip_file": "zip",
    "relatorio": "report", "relatório": "report", "html": "report",
    "folha_de_contato": "contact_sheet", "contato": "contact_sheet",
    "contactsheet": "contact_sheet", "mosaico": "contact_sheet",
    "formato": "format", "fmt": "format",
    "qualidade": "quality", "sufixo": "suffix", "prefixo": "prefix",
}
_DELIVER_KNOWN: frozenset[str] = frozenset({
    "zip", "report", "contact_sheet", "format", "quality", "suffix", "prefix",
})

_VARIATIONS_ALIASES: dict[str, str] = {
    "quantidade": "n", "count": "count", "qtd": "n", "quantos": "n",
    "modo": "mode", "formato": "aspect", "target": "aspect",
    "copias": "copy", "copy_variants": "copy", "textos": "copy",
    "descricao": "prompt", "descrição": "prompt",
}
_VARIATIONS_KNOWN: frozenset[str] = frozenset({
    "n", "count", "mode", "aspect", "copy", "prompt", "seed",
})

# Mapa reverso alias -> canônico, só para achar a linha original no YAML.
_ALL_ALIASES: dict[str, list[str]] = {}
for _table in (_TOP_ALIASES, _OP_COMMON_ALIASES, _DELIVER_ALIASES, _VARIATIONS_ALIASES,
               *[s["aliases"] for s in _OP_SPEC.values()]):
    for _a, _c in _table.items():
        _ALL_ALIASES.setdefault(_c, []).append(_a)


# --------------------------------------------------------------------------- #
# Diagnóstico (erro com endereço)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Issue:
    """Um erro de receita e onde ele mora."""

    path: tuple[Any, ...]
    message: str

    def render(self, lines: dict[tuple[Any, ...], int] | None = None) -> str:
        where = _where(self.path)
        line = _lookup_line(lines or {}, self.path)
        prefix = f"linha {line}, {where}" if line and where else (
            f"linha {line}" if line else where)
        return f"{prefix}: {self.message}" if prefix else self.message


def _where(path: Sequence[Any]) -> str:
    """Endereço legível de um campo. Operações são contadas a partir de 1."""
    if not path:
        return ""
    if path[0] == "operations" and len(path) >= 2 and isinstance(path[1], int):
        rest = ".".join(str(p) for p in path[2:])
        base = f"operação {path[1] + 1}"
        return f"{base}, campo '{rest}'" if rest else base
    return "campo '" + ".".join(str(p) for p in path) + "'"


def _lookup_line(lines: dict[tuple[Any, ...], int], path: Sequence[Any]) -> int | None:
    """Linha do campo no YAML, tolerando aliases e caindo para o pai."""
    p = tuple(path)
    while p:
        if p in lines:
            return lines[p]
        last = p[-1]
        if isinstance(last, str):
            for alias in _ALL_ALIASES.get(last, ()):
                cand = p[:-1] + (alias,)
                if cand in lines:
                    return lines[cand]
        p = p[:-1]
    return None


def _line_index(text: str) -> dict[tuple[Any, ...], int]:
    """Mapa caminho -> linha (1-based) do YAML original.

    ``yaml.safe_load`` joga fora a posição de cada nó; ``yaml.compose`` mantém.
    É isso que permite dizer "linha 12" em vez de "em algum lugar da receita".
    """
    try:
        root = yaml.compose(text)
    except yaml.YAMLError:
        return {}
    out: dict[tuple[Any, ...], int] = {}

    def walk(node: Any, path: tuple[Any, ...]) -> None:
        if isinstance(node, yaml.MappingNode):
            for key_node, val_node in node.value:
                key = getattr(key_node, "value", None)
                if not isinstance(key, str):
                    continue
                sub = path + (key,)
                out[sub] = key_node.start_mark.line + 1
                walk(val_node, sub)
        elif isinstance(node, yaml.SequenceNode):
            for i, item in enumerate(node.value):
                sub = path + (i,)
                out[sub] = item.start_mark.line + 1
                walk(item, sub)

    if root is not None:
        walk(root, ())
    return out


def _suggest(key: str, options: Iterable[str]) -> str:
    """' Você quis dizer 'find'?' — vazio quando não há palpite bom."""
    near = difflib.get_close_matches(str(key).lower(), sorted(options), n=1, cutoff=0.72)
    return f" Você quis dizer '{near[0]}'?" if near else ""


# --------------------------------------------------------------------------- #
# Normalização (aliases -> nomes canônicos)
# --------------------------------------------------------------------------- #
def _canon(d: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
    """Aplica a tabela de aliases. A chave canônica explícita sempre vence."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = str(k).strip()
        canon = aliases.get(key.lower(), key)
        if canon in out and key.lower() != canon:
            continue  # já veio com o nome canônico; ignora o apelido
        out[canon] = v
    return out


def _norm_color(value: Any) -> Any:
    """Nome de cor -> hex. Qualquer outra coisa passa intacta (validada depois)."""
    if isinstance(value, str):
        return NAMED_COLORS.get(value.strip().lower(), value)
    return value


def _norm_style(style: Any) -> Any:
    if not isinstance(style, dict):
        return style
    aliases = {
        "font": "family", "fonte": "family", "familia": "family", "família": "family",
        "size": "size_px", "tamanho": "size_px", "corpo": "size_px",
        "cor": "color", "peso": "weight", "italico": "italic", "itálico": "italic",
        "tracking": "letter_spacing", "spacing": "letter_spacing",
        "espacamento": "letter_spacing", "espaçamento": "letter_spacing",
        "leading": "line_height", "entrelinha": "line_height",
        "alinhamento": "align", "alinhamento_vertical": "valign",
        "maiuscula": "uppercase", "maiúscula": "uppercase", "caixa_alta": "uppercase",
        "contorno": "stroke_width", "stroke": "stroke_width",
        "cor_contorno": "stroke_color", "sombra": "shadow",
        "cor_sombra": "shadow_color", "opacidade": "opacity",
    }
    out = _canon(style, aliases)
    for key in ("color", "stroke_color", "shadow_color"):
        if key in out:
            out[key] = _norm_color(out[key])
    if isinstance(out.get("weight"), str):
        out["weight"] = out["weight"].strip().lower()
    for key in ("align", "valign"):
        if isinstance(out.get(key), str):
            out[key] = out[key].strip().lower()
    return out


def _norm_op(raw: Any) -> dict[str, Any]:
    """Dicionário de operação com chaves canônicas, pronto para EditOp.from_dict."""
    if not isinstance(raw, dict):
        return {}
    d = _canon(raw, _OP_COMMON_ALIASES)
    kind = str(d.get("type") or "").strip().lower()
    spec = _OP_SPEC.get(kind)
    if spec:
        common = {k: v for k, v in d.items() if k in _OP_COMMON}
        rest = {k: v for k, v in d.items() if k not in _OP_COMMON}
        d = {**common, **_canon(rest, spec["aliases"])}
    if "type" in d:
        d["type"] = kind
    if "engine" in d and isinstance(d["engine"], str):
        d["engine"] = d["engine"].strip().lower()
    if "role" in d and isinstance(d["role"], str):
        d["role"] = d["role"].strip().lower()
    if "match" in d and isinstance(d["match"], str):
        d["match"] = d["match"].strip().lower()
    if "style" in d:
        d["style"] = _norm_style(d["style"])
    for key in ("from", "to"):
        if kind == "replace_color" and key in d:
            d[key] = _norm_color(d[key])
    if "scope" in d:
        d["scope"] = _norm_scope(d["scope"])
    return d


def _norm_scope(scope: Any) -> str:
    """Aceita string, número ou lista; devolve sempre a forma canônica em string."""
    if scope is None:
        return "all"
    if isinstance(scope, (list, tuple)):
        return ",".join(str(s).strip() for s in scope if str(s).strip())
    if isinstance(scope, bool):
        return "all"
    return str(scope).strip() or "all"


def _norm_top(d: dict[str, Any]) -> dict[str, Any]:
    out = _canon(d, _TOP_ALIASES)
    if isinstance(out.get("engine"), str):
        out["engine"] = out["engine"].strip().lower()
    if isinstance(out.get("reframe_mode"), str):
        out["reframe_mode"] = out["reframe_mode"].strip().lower()
    if isinstance(out.get("deliver"), dict):
        out["deliver"] = _canon(out["deliver"], _DELIVER_ALIASES)
    if isinstance(out.get("variations"), dict):
        out["variations"] = _canon(out["variations"], _VARIATIONS_ALIASES)
    ops = out.get("operations")
    if isinstance(ops, list):
        out["operations"] = [_norm_op(o) if isinstance(o, dict) else o for o in ops]
    return out


# --------------------------------------------------------------------------- #
# Validadores de tipo
# --------------------------------------------------------------------------- #
def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_str(v: Any, path: tuple, issues: list[_Issue], *, allow_empty: bool = False) -> bool:
    if not isinstance(v, str):
        issues.append(_Issue(path, f"esperava um texto, veio {_typename(v)}."))
        return False
    if not allow_empty and not v.strip():
        issues.append(_Issue(path, "não pode ficar vazio."))
        return False
    return True


def _check_bool(v: Any, path: tuple, issues: list[_Issue]) -> bool:
    if not isinstance(v, bool):
        issues.append(_Issue(path, f"esperava true ou false, veio {_typename(v)}."))
        return False
    return True


def _check_num(v: Any, path: tuple, issues: list[_Issue], *,
               lo: float | None = None, hi: float | None = None) -> bool:
    if not _is_num(v):
        issues.append(_Issue(path, f"esperava um número, veio {_typename(v)}."))
        return False
    if lo is not None and float(v) < lo:
        issues.append(_Issue(path, f"precisa ser >= {lo} (veio {v})."))
        return False
    if hi is not None and float(v) > hi:
        issues.append(_Issue(path, f"precisa ser <= {hi} (veio {v})."))
        return False
    return True


def _typename(v: Any) -> str:
    return {
        type(None): "nada (nulo)", bool: "true/false", int: "número",
        float: "número", str: "texto", list: "lista", dict: "mapa",
    }.get(type(v), type(v).__name__)


def _check_color(v: Any, path: tuple, issues: list[_Issue]) -> bool:
    if isinstance(v, (list, tuple)):
        if len(v) < 3 or not all(_is_num(c) and 0 <= float(c) <= 255 for c in list(v)[:3]):
            issues.append(_Issue(path, "cor em lista precisa ser [R, G, B] de 0 a 255."))
            return False
        return True
    if isinstance(v, str):
        s = v.strip()
        if s.lower() in NAMED_COLORS or _RE_HEX.match(s):
            return True
        issues.append(_Issue(
            path, f"cor inválida: {v!r}. Use hexadecimal ('#ffffff') ou um nome "
                  f"conhecido ({', '.join(sorted(list(NAMED_COLORS)[:6]))}...)."))
        return False
    issues.append(_Issue(path, f"cor inválida: esperava texto ou [R,G,B], veio {_typename(v)}."))
    return False


def _check_box(v: Any, path: tuple, issues: list[_Issue]) -> bool:
    """Caixa em pixels ou normalizada. Só recusa o que Box.from_any não salvaria."""
    raw = v
    if isinstance(raw, (list, tuple)):
        if len(raw) != 4:
            issues.append(_Issue(path, "caixa em lista precisa ter 4 valores: [x, y, w, h]."))
            return False
        raw = {"x": raw[0], "y": raw[1], "w": raw[2], "h": raw[3]}
    if not isinstance(raw, dict):
        issues.append(_Issue(
            path, "caixa inválida: use {x: 0.1, y: 0.8, w: 0.8, h: 0.1, norm: true} "
                  "ou [x, y, w, h] em pixels."))
        return False
    faltando = [k for k in ("x", "y", "w", "h") if k not in raw]
    if faltando:
        issues.append(_Issue(path, f"caixa sem {', '.join(faltando)}. "
                                   "Precisa de x, y, w e h."))
        return False
    ok = True
    for k in ("x", "y", "w", "h"):
        if not _is_num(raw[k]):
            issues.append(_Issue(path + (k,), f"esperava um número, veio {_typename(raw[k])}."))
            ok = False
    if "norm" in raw and not isinstance(raw["norm"], bool):
        issues.append(_Issue(path + ("norm",), "norm precisa ser true ou false."))
        ok = False
    if not ok:
        return False
    if raw["w"] <= 0 or raw["h"] <= 0:
        issues.append(_Issue(path, "a caixa precisa de largura e altura maiores que zero."))
        return False
    valores = [float(raw[k]) for k in ("x", "y", "w", "h")]
    normalizada = raw.get("norm") is True or (
        raw.get("norm") is not False and all(-0.001 <= v <= 1.001 for v in valores))
    if raw.get("norm") is True and any(v > 1.001 or v < -0.001 for v in valores):
        issues.append(_Issue(path, "com 'norm: true' os valores vão de 0 a 1 "
                                   "(fração da imagem). Remova o norm para usar pixels."))
        return False
    if normalizada and (valores[0] + valores[2] > 1.05 or valores[1] + valores[3] > 1.05):
        issues.append(_Issue(path, "a caixa normalizada sai da imagem: "
                                   "x+w e y+h precisam caber em 1.0."))
        return False
    return True


def _check_scope(v: Any, path: tuple, issues: list[_Issue]) -> bool:
    scope = _norm_scope(v)
    for tok in _scope_tokens(scope):
        body = tok[1:].strip() if tok.startswith("!") else tok
        if not body:
            issues.append(_Issue(path, f"escopo com item vazio em {scope!r}. "
                                       "Use 'all', '*.png', '1,3,5' ou '1-10'."))
            return False
        rng = _RE_RANGE.match(body)
        if rng and int(rng.group(1)) > int(rng.group(2)):
            issues.append(_Issue(path, f"intervalo invertido em {tok!r}: "
                                       "escreva do menor para o maior (ex.: '1-10')."))
            return False
        if _RE_IDX.match(body) and int(body) < 1:
            issues.append(_Issue(path, "os índices do escopo começam em 1 "
                                       "(a primeira imagem é a 1, não a 0)."))
            return False
    return True


def _check_style(style: Any, path: tuple, issues: list[_Issue]) -> None:
    if not isinstance(style, dict):
        issues.append(_Issue(path, f"'style' precisa ser um mapa, veio {_typename(style)}."))
        return
    conhecidas = {
        "family", "weight", "italic", "size_px", "color", "letter_spacing",
        "line_height", "align", "valign", "uppercase", "stroke_width",
        "stroke_color", "shadow", "shadow_color", "shadow_offset",
        "shadow_blur", "opacity",
    }
    for k, v in style.items():
        p = path + (k,)
        if k not in conhecidas:
            sug = _suggest(k, conhecidas)
            if sug:
                issues.append(_Issue(p, f"estilo não tem o campo '{k}'.{sug}"))
            continue
        if k == "family":
            _check_str(v, p, issues)
        elif k == "weight":
            if _is_num(v):
                _check_num(v, p, issues, lo=1, hi=1000)
            elif _check_str(v, p, issues) and v.strip().lower() not in _WEIGHTS:
                issues.append(_Issue(p, f"peso desconhecido: {v!r}. Use um de: "
                                        "thin, light, regular, medium, semibold, bold, black."))
        elif k in ("italic", "uppercase", "shadow"):
            _check_bool(v, p, issues)
        elif k == "size_px":
            _check_num(v, p, issues, lo=1, hi=2000)
        elif k in ("color", "stroke_color", "shadow_color"):
            _check_color(v, p, issues)
        elif k == "letter_spacing":
            _check_num(v, p, issues, lo=-200, hi=200)
        elif k == "line_height":
            _check_num(v, p, issues, lo=0.5, hi=5)
        elif k == "align":
            if _check_str(v, p, issues) and v.strip().lower() not in _ALIGNS:
                issues.append(_Issue(p, f"alinhamento inválido: {v!r} (left|center|right)."))
        elif k == "valign":
            if _check_str(v, p, issues) and v.strip().lower() not in _VALIGNS:
                issues.append(_Issue(p, f"alinhamento vertical inválido: {v!r} (top|middle|bottom)."))
        elif k == "stroke_width":
            _check_num(v, p, issues, lo=0, hi=100)
        elif k == "shadow_blur":
            _check_num(v, p, issues, lo=0, hi=200)
        elif k == "shadow_offset":
            if not (isinstance(v, (list, tuple)) and len(v) == 2 and all(_is_num(c) for c in v)):
                issues.append(_Issue(p, "shadow_offset precisa ser [dx, dy] em pixels."))
        elif k == "opacity":
            _check_num(v, p, issues, lo=0, hi=1)


# --------------------------------------------------------------------------- #
# Validação da receita inteira
# --------------------------------------------------------------------------- #
def _validate_op(op: Any, i: int, issues: list[_Issue]) -> None:
    base = ("operations", i)
    if not isinstance(op, dict):
        issues.append(_Issue(base, f"cada operação precisa ser um mapa com 'type:', "
                                   f"veio {_typename(op)}."))
        return

    kind = op.get("type")
    if kind is None:
        issues.append(_Issue(base, "falta 'type:'. Use um de: "
                                   + ", ".join(k.value for k in OpKind) + "."))
        return
    if not isinstance(kind, str) or not kind.strip():
        issues.append(_Issue(base + ("type",), "'type' precisa ser um texto, ex.: replace_text."))
        return
    kind = kind.strip().lower()
    validos = [k.value for k in OpKind]
    if kind not in validos:
        issues.append(_Issue(base + ("type",),
                             f"operação desconhecida: {kind!r}.{_suggest(kind, validos)} "
                             f"Disponíveis: {', '.join(validos)}."))
        return

    if "engine" in op:
        eng = op["engine"]
        if _check_str(eng, base + ("engine",), issues) and eng.strip().lower() not in {
                e.value for e in Engine}:
            issues.append(_Issue(base + ("engine",),
                                 f"engine inválida: {eng!r} (deterministic|ai|auto)."))
    if "scope" in op:
        _check_scope(op["scope"], base + ("scope",), issues)
    if "enabled" in op:
        _check_bool(op["enabled"], base + ("enabled",), issues)

    spec = _OP_SPEC[kind]

    for campo in spec["requires"]:
        if op.get(campo) is None or (isinstance(op.get(campo), str) and not op[campo].strip()):
            issues.append(_Issue(base, f"{kind} precisa do campo '{campo}'."))
    for campos, msg in spec["requires_any"]:
        if not any(op.get(c) not in (None, "") for c in campos):
            issues.append(_Issue(base, f"{kind} {msg}."))

    conhecidas = set(spec["known"]) | _OP_COMMON
    for k in op:
        if k not in conhecidas:
            sug = _suggest(k, conhecidas)
            if sug:
                issues.append(_Issue(base + (k,), f"{kind} não tem o campo '{k}'.{sug}"))

    # -- campos com formato próprio -------------------------------------- #
    if "box" in op:
        _check_box(op["box"], base + ("box",), issues)
    if "style" in op:
        _check_style(op["style"], base + ("style",), issues)
    if "find" in op:
        _check_str(op["find"], base + ("find",), issues)
    if "replace" in op:
        _check_str(op["replace"], base + ("replace",), issues, allow_empty=True)
    if "text" in op:
        _check_str(op["text"], base + ("text",), issues, allow_empty=True)
    if "prompt" in op:
        _check_str(op["prompt"], base + ("prompt",), issues)
    if "role" in op:
        from .models import TextRole  # local: evita custo no import do módulo
        papeis = [r.value for r in TextRole]
        v = op["role"]
        if _check_str(v, base + ("role",), issues) and v.strip().lower() not in papeis:
            issues.append(_Issue(base + ("role",),
                                 f"papel desconhecido: {v!r}.{_suggest(v, papeis)} "
                                 f"Disponíveis: {', '.join(papeis)}."))
    if "match" in op:
        v = op["match"]
        if _check_str(v, base + ("match",), issues) and v.strip().lower() not in MATCH_MODES:
            issues.append(_Issue(base + ("match",),
                                 f"match inválido: {v!r} (fuzzy|exact)."))
    if "max_lines" in op:
        _check_num(op["max_lines"], base + ("max_lines",), issues, lo=1, hi=20)
    for flag in ("autofit", "grow_box", "keep_aspect"):
        if flag in op:
            _check_bool(op[flag], base + (flag,), issues)
    if kind == "replace_color":
        for k in ("from", "to"):
            if k in op:
                _check_color(op[k], base + (k,), issues)
        if "tolerance" in op:
            _check_num(op["tolerance"], base + ("tolerance",), issues, lo=0, hi=255)
    if kind == "reframe":
        if "target" in op and _check_str(op["target"], base + ("target",), issues):
            try:
                AspectSpec.parse(op["target"])
            except (ValueError, ZeroDivisionError) as exc:
                issues.append(_Issue(base + ("target",), str(exc)))
        if "mode" in op:
            v = op["mode"]
            if _check_str(v, base + ("mode",), issues) and v.strip().lower() not in REFRAME_MODES:
                issues.append(_Issue(base + ("mode",),
                                     f"modo inválido: {v!r} ({'|'.join(REFRAME_MODES)})."))
    if kind == "overlay" and "image" in op:
        _check_str(op["image"], base + ("image",), issues)
    if kind == "resize":
        for k in ("width", "height", "long_edge"):
            if k in op:
                _check_num(op[k], base + (k,), issues, lo=1, hi=20000)
        if "scale" in op:
            _check_num(op["scale"], base + ("scale",), issues, lo=0.01, hi=20)
    if kind == "export":
        if "format" in op:
            v = op["format"]
            if _check_str(v, base + ("format",), issues) and v.strip().lower().lstrip(".") \
                    not in DELIVER_FORMATS:
                issues.append(_Issue(base + ("format",),
                                     f"formato inválido: {v!r} ({'|'.join(DELIVER_FORMATS)})."))
        if "quality" in op:
            _check_num(op["quality"], base + ("quality",), issues, lo=1, hi=100)

    # A IA nunca é obrigatória, mas pedir 'deterministic' onde ela é o único
    # caminho é um engano do usuário que só apareceria na metade do lote.
    engine = str(op.get("engine") or "").strip().lower()
    if kind in ("replace_region",) and engine == "deterministic":
        issues.append(_Issue(base + ("engine",),
                             "replace_region só existe na trilha de IA. Use "
                             "engine: ai (ou auto) nesta operação."))


def _validate(d: Any) -> list[_Issue]:
    """Coração da validação: devolve erros estruturados (com caminho)."""
    issues: list[_Issue] = []
    if d is None:
        return [_Issue((), "receita vazia. Comece com 'job:', 'input:' e 'operations:'.")]
    if not isinstance(d, dict):
        return [_Issue((), f"a receita precisa ser um mapa YAML (chave: valor), "
                           f"veio {_typename(d)}.")]

    d = _norm_top(d)

    for k in d:
        if k not in _TOP_KNOWN and not str(k).startswith(("_", "x-")):
            issues.append(_Issue((k,), f"campo desconhecido no topo da receita: "
                                       f"'{k}'.{_suggest(k, _TOP_KNOWN)}"))

    if "job" in d:
        _check_str(d["job"], ("job",), issues)
    if "notes" in d and not isinstance(d["notes"], (str, list)):
        issues.append(_Issue(("notes",), "'notes' aceita um texto ou uma lista de textos."))

    if d.get("input") is None:
        issues.append(_Issue((), "falta 'input:' — a pasta com as imagens de entrada "
                                 "(ex.: input: inbox/campanha-agosto)."))
    else:
        _check_str(d["input"], ("input",), issues)
    if "output" in d and d["output"] is not None:
        _check_str(d["output"], ("output",), issues)

    if "engine" in d:
        eng = d["engine"]
        if _check_str(eng, ("engine",), issues) and eng not in {e.value for e in Engine}:
            issues.append(_Issue(("engine",),
                                 f"engine inválida: {eng!r}. Use deterministic "
                                 "(offline, zero drift), ai ou auto."))

    if "target" in d and d["target"] is not None:
        alvo = d["target"]
        if isinstance(alvo, (list, tuple)) and len(alvo) == 2 and all(_is_num(v) for v in alvo):
            pass
        elif _check_str(alvo, ("target",), issues):
            try:
                AspectSpec.parse(alvo)
            except (ValueError, ZeroDivisionError):
                issues.append(_Issue(("target",),
                                     f"formato inválido: {alvo!r}. Use '16:9', "
                                     "'1080x1920' ou '9:16@1080'."))

    if "reframe_mode" in d:
        modo = d["reframe_mode"]
        if _check_str(modo, ("reframe_mode",), issues) and modo not in REFRAME_MODES:
            issues.append(_Issue(("reframe_mode",),
                                 f"modo de reenquadramento inválido: {modo!r} "
                                 f"({'|'.join(REFRAME_MODES)})."))
        if d.get("target") is None and "reframe_mode" in d:
            issues.append(_Issue(("reframe_mode",),
                                 "'reframe_mode' só faz sentido junto de 'target:'. "
                                 "Adicione o formato de saída (ex.: target: \"16:9\")."))
    if "long_edge" in d:
        _check_num(d["long_edge"], ("long_edge",), issues, lo=64, hi=20000)
    if "recursive" in d:
        _check_bool(d["recursive"], ("recursive",), issues)
    if "quality" in d:
        q = d["quality"]
        if _check_str(q, ("quality",), issues) and q.strip().lower() not in (
                "low", "medium", "high", "auto"):
            issues.append(_Issue(("quality",),
                                 f"qualidade inválida: {q!r} (low|medium|high|auto)."))

    # -- operações --------------------------------------------------------- #
    ops = d.get("operations")
    if ops is not None:
        if not isinstance(ops, list):
            issues.append(_Issue(("operations",),
                                 f"'operations' precisa ser uma lista de operações "
                                 f"(cada item começa com '- type:'), veio {_typename(ops)}."))
            ops = None
        else:
            for i, op in enumerate(ops):
                _validate_op(op, i, issues)

    # -- entrega ----------------------------------------------------------- #
    dl = d.get("deliver")
    if dl is not None:
        if not isinstance(dl, dict):
            issues.append(_Issue(("deliver",),
                                 f"'deliver' precisa ser um mapa (zip: true, report: true), "
                                 f"veio {_typename(dl)}."))
        else:
            for k, v in dl.items():
                p = ("deliver", k)
                if k not in _DELIVER_KNOWN:
                    sug = _suggest(k, _DELIVER_KNOWN)
                    if sug:
                        issues.append(_Issue(p, f"'deliver' não tem o campo '{k}'.{sug}"))
                    continue
                if k in ("zip", "report", "contact_sheet"):
                    _check_bool(v, p, issues)
                elif k == "format":
                    if _check_str(v, p, issues) and v.strip().lower().lstrip(".") \
                            not in DELIVER_FORMATS:
                        issues.append(_Issue(p, f"formato de entrega inválido: {v!r} "
                                                f"({'|'.join(DELIVER_FORMATS)})."))
                elif k == "quality":
                    _check_num(v, p, issues, lo=1, hi=100)
                else:
                    _check_str(v, p, issues, allow_empty=True)

    # -- variações --------------------------------------------------------- #
    var = d.get("variations")
    if var is not None:
        if isinstance(var, int) and not isinstance(var, bool):
            var = {"n": var}
        if not isinstance(var, dict):
            issues.append(_Issue(("variations",),
                                 f"'variations' precisa ser um mapa (n: 30, mode: generative) "
                                 f"ou só o número, veio {_typename(var)}."))
        else:
            for k, v in var.items():
                p = ("variations", k)
                if k not in _VARIATIONS_KNOWN:
                    sug = _suggest(k, _VARIATIONS_KNOWN)
                    if sug:
                        issues.append(_Issue(p, f"'variations' não tem o campo '{k}'.{sug}"))
                    continue
                if k in ("n", "count"):
                    _check_num(v, p, issues, lo=1, hi=500)
                elif k == "mode":
                    if _check_str(v, p, issues) and v.strip().lower() not in VARIATION_MODES:
                        issues.append(_Issue(p, f"modo de variação inválido: {v!r} "
                                                f"({'|'.join(VARIATION_MODES)})."))
                elif k == "aspect":
                    if _check_str(v, p, issues):
                        try:
                            AspectSpec.parse(v)
                        except (ValueError, ZeroDivisionError):
                            issues.append(_Issue(p, f"formato inválido: {v!r}. "
                                                    "Use '16:9', '1080x1920' ou '9:16@1080'."))
                elif k == "copy":
                    if not isinstance(v, list):
                        issues.append(_Issue(p, "'copy' precisa ser uma lista de textos "
                                                "ou de mapas {headline, subhead, cta}."))
                elif k == "prompt":
                    _check_str(v, p, issues)
            if var.get("n") is None and var.get("count") is None:
                issues.append(_Issue(("variations",),
                                     "falta 'n:' — quantas variações gerar (ex.: n: 30)."))

    # -- a receita precisa fazer alguma coisa ------------------------------ #
    tem_ops = bool(ops)
    if not tem_ops and d.get("target") is None and d.get("variations") is None:
        issues.append(_Issue((), "a receita não faz nada: defina 'operations:', "
                                 "'target:' (reenquadrar) ou 'variations:' (gerar novos)."))
    if isinstance(ops, list) and ops and all(
            isinstance(o, dict) and o.get("enabled") is False for o in ops):
        issues.append(_Issue(("operations",),
                             "todas as operações estão com 'enabled: false' — "
                             "o lote sairia idêntico à entrada."))
    return issues


def validate_recipe(d: Any) -> list[str]:
    """Erros da receita (já parseada) em português. Lista vazia = pode rodar.

    Recebe o dicionário do YAML, não o arquivo — assim a interface web valida
    um formulário com a mesma função que valida o arquivo do CLI.
    """
    return [issue.render() for issue in _validate(d)]


# --------------------------------------------------------------------------- #
# Escopo
# --------------------------------------------------------------------------- #
_RE_IDX = re.compile(r"^\d+$")
_RE_RANGE = re.compile(r"^(\d+)\s*-\s*(\d+)$")
_RE_FROM = re.compile(r"^(\d+)\s*-$")
_RE_TO = re.compile(r"^-\s*(\d+)$")
_GLOB_CHARS = set("*?[")


def _scope_tokens(scope: str) -> list[str]:
    return [t.strip() for t in str(scope).split(",") if t.strip()]


def _token_matches(token: str, name: str, posix: str, stem: str,
                   human: int, total: int) -> bool:
    """Um item de escopo casa com este arquivo?"""
    tok = token.strip()
    if tok in ("all", "*", "todas", "todos", "tudo"):
        return True

    if _RE_IDX.match(tok):
        return human == int(tok)
    m = _RE_RANGE.match(tok)
    if m:
        return int(m.group(1)) <= human <= int(m.group(2))
    m = _RE_FROM.match(tok)
    if m:
        return human >= int(m.group(1))
    m = _RE_TO.match(tok)
    if m:
        return human <= int(m.group(1))

    low = tok.lower()
    if any(c in _GLOB_CHARS for c in tok):
        return (fnmatch.fnmatch(name, low) or fnmatch.fnmatch(posix, low)
                or fnmatch.fnmatch(stem, low))
    # Sem curinga: nome ou nome-sem-extensão, exato.
    return low in (name, stem) or posix.endswith("/" + low)


def matches_scope(scope: Any, path: Any, index: int, total: int,
                  *, one_based: bool = False) -> bool:
    """Esta imagem entra no escopo da operação?

    ``scope`` aceita, separados por vírgula e combináveis:

    * ``all`` (ou ausente) — todas;
    * glob de nome de arquivo — ``*.png``, ``campanha-*``, ``**/final/*.jpg``;
    * índices — ``1,3,5``;
    * intervalos — ``1-10``, ``5-`` (da 5ª ao fim), ``-3`` (até a 3ª);
    * exclusões com ``!`` — ``!*.jpg`` ou ``all,!1-5``.

    Os índices da receita são **1-based** porque quem escreve é humano: "1" é a
    primeira imagem. O parâmetro ``index``, porém, é a posição na lista como sai
    de ``enumerate(paths)`` — ou seja, **0-based**. Quem já numera a partir de 1
    passa ``one_based=True`` e a conversão é feita aqui.
    """
    tokens = _scope_tokens(_norm_scope(scope))
    if not tokens:
        return True

    p = Path(str(path))
    name = p.name.lower()
    stem = p.stem.lower()
    posix = p.as_posix().lower()
    human = int(index) + (0 if one_based else 1)
    total = int(total or 0)

    incluir = [t for t in tokens if not t.startswith("!")]
    excluir = [t[1:].strip() for t in tokens if t.startswith("!") and t[1:].strip()]

    # Só exclusões => a base é "todas".
    ok = True if not incluir else any(
        _token_matches(t, name, posix, stem, human, total) for t in incluir)
    if ok and excluir:
        ok = not any(_token_matches(t, name, posix, stem, human, total) for t in excluir)
    return ok


# --------------------------------------------------------------------------- #
# Recipe
# --------------------------------------------------------------------------- #
def _default_deliver() -> dict[str, Any]:
    return {"zip": True, "report": True, "contact_sheet": False,
            "format": "png", "quality": 95, "suffix": "", "prefix": ""}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).strip().lower(), flags=re.ASCII)
    return s.strip("-") or "lote"


def _resolve_dir(raw: Any, root: Path) -> Path:
    """Caminho da receita -> caminho absoluto, ancorado em ``settings.root``."""
    p = Path(str(raw)).expanduser()
    if not p.is_absolute():
        p = Path(root) / p
    # resolve(strict=False) normaliza ".." sem exigir que exista.
    return p.resolve()


@dataclass
class Recipe:
    """Uma receita já validada, com caminhos resolvidos e prontos para uso.

    Os campos depois de ``raw`` são conveniências (todos com default): não
    fazem parte do contrato mínimo, mas evitam que o pipeline tenha que
    reinterpretar o YAML por conta própria.
    """

    job: str
    input_dir: Path
    output_dir: Path
    engine: Engine = Engine.AUTO
    operations: list[EditOp] = field(default_factory=list)
    deliver: dict[str, Any] = field(default_factory=_default_deliver)
    target: AspectSpec | None = None
    variations: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    # -- extras ------------------------------------------------------------ #
    reframe_mode: str = "pad"
    reframe_fill: Any = "blur"
    reframe_prompt: str | None = None
    # None = deriva do maior lado de cada imagem de origem. Um 1080x1920 vira
    # 1920x1080 em 16:9, em vez de encolher para um 1440x810 arbitrário.
    long_edge: int | None = None
    recursive: bool = False
    quality: str | None = None
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    path: Path | None = None

    # -- conveniências ----------------------------------------------------- #
    @property
    def recipe_path(self) -> str:
        """Origem da receita, no formato que ``JobManifest.recipe_path`` espera."""
        return str(self.path) if self.path else ""

    @property
    def has_operations(self) -> bool:
        return any(op.enabled for op in self.operations)

    def ops_for(self, path: Any, index: int, total: int,
                *, one_based: bool = False) -> list[EditOp]:
        """Operações habilitadas que se aplicam a esta imagem, na ordem escrita."""
        return [op for op in self.operations
                if op.enabled and matches_scope(op.scope, path, index, total,
                                                one_based=one_based)]

    def summary(self) -> str:
        """Uma linha por decisão da receita — o que o CLI mostra antes de rodar."""
        linhas = [f"lote: {self.job}",
                  f"entrada: {self.input_dir}",
                  f"saída: {self.output_dir}",
                  f"motor: {self.engine.value}"]
        for i, op in enumerate(self.operations, 1):
            estado = "" if op.enabled else " [desligada]"
            escopo = "" if op.scope in ("all", "") else f" escopo={op.scope}"
            linhas.append(f"  {i}. {op.kind.value} ({op.engine.value}){escopo}{estado}")
        if self.target is not None:
            if self.long_edge or (self.target.width and self.target.height):
                w, h = self.target.resolve(self.long_edge or 1440)
                tamanho = f" ({w}x{h})"
            else:
                tamanho = " (tamanho derivado de cada origem)"
            linhas.append(f"reenquadrar: {self.target.label}{tamanho} modo={self.reframe_mode}")
        if self.variations:
            linhas.append(f"variações: {self.variations.get('n')} "
                          f"({self.variations.get('mode')})")
        entregas = [k for k in ("zip", "report", "contact_sheet") if self.deliver.get(k)]
        linhas.append("entrega: " + (", ".join(entregas) if entregas else "só os arquivos"))
        for w_ in self.warnings:
            linhas.append(f"aviso: {w_}")
        return "\n".join(linhas)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job": self.job,
            "input": str(self.input_dir),
            "output": str(self.output_dir),
            "engine": self.engine.value,
            "operations": [op.to_dict() for op in self.operations],
            "target": self.target.label if self.target else None,
            "reframe_mode": self.reframe_mode,
            "long_edge": self.long_edge,
            "deliver": dict(self.deliver),
            "variations": dict(self.variations) if self.variations else None,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
            "recipe_path": self.recipe_path,
        }

    # -- construção -------------------------------------------------------- #
    @classmethod
    def from_dict(cls, data: Any, settings: Any = None, *,
                  path: Any = None, text: str | None = None,
                  check_paths: bool = True) -> "Recipe":
        """Valida e materializa uma receita já parseada.

        ``text`` é o YAML original: quando presente, os erros ganham o número da
        linha. ``check_paths=False`` desliga a checagem de existência da pasta de
        entrada (útil para a interface web, que monta a receita antes de o
        usuário subir os arquivos).
        """
        if settings is None:
            from .config import load_settings  # local: evita import circular no topo
            settings = load_settings()

        issues = _validate(data)
        if issues:
            lines = _line_index(text) if text else {}
            raise RecipeError(_format_issues(issues, lines, path))

        d = _norm_top(dict(data))
        root = Path(getattr(settings, "root", Path.cwd()))

        p = Path(path) if path else None
        job = str(d.get("job") or (p.stem if p else "") or "lote").strip()

        input_dir = _resolve_dir(d["input"], root)
        if "output" in d and d["output"]:
            output_dir = _resolve_dir(d["output"], root)
        else:
            outbox = Path(getattr(settings, "outbox", root / "outbox"))
            output_dir = _resolve_dir(outbox / _slug(job), root)

        warnings: list[str] = []
        if check_paths:
            if not input_dir.exists():
                raise RecipeError(
                    f"A pasta de entrada não existe: {input_dir}\n"
                    f"  Crie a pasta e coloque as imagens nela, ou corrija o campo "
                    f"'input:' da receita (caminhos relativos partem de {root}).")
            if not input_dir.is_dir():
                raise RecipeError(
                    f"'input:' aponta para um arquivo, não para uma pasta: {input_dir}\n"
                    f"  Aponte para a PASTA que contém as imagens do lote.")
        if output_dir == input_dir:
            raise RecipeError(
                "A pasta de saída é a mesma da entrada. Isso sobrescreveria os "
                "originais — escolha outra pasta em 'output:'.")

        engine = Engine(str(d.get("engine") or "auto").strip().lower())

        operations: list[EditOp] = []
        for raw_op in (d.get("operations") or []):
            op_d = dict(raw_op)
            # Herança: quem não declara 'engine' herda a do topo. Sem isso, um
            # "engine: deterministic" no topo não garantiria nada.
            op_d.setdefault("engine", engine.value)
            op_d.pop("note", None)
            operations.append(EditOp.from_dict(op_d))

        target: AspectSpec | None = None
        alvo = d.get("target")
        if alvo is not None:
            if isinstance(alvo, (list, tuple)) and len(alvo) == 2:
                target = AspectSpec.parse(f"{int(alvo[0])}x{int(alvo[1])}")
            else:
                target = AspectSpec.parse(str(alvo))

        deliver = _default_deliver()
        deliver.update({k: v for k, v in (d.get("deliver") or {}).items()})
        fmt = str(deliver.get("format") or "png").strip().lower().lstrip(".")
        deliver["format"] = fmt
        if fmt in ("jpg", "jpeg"):
            warnings.append(
                "entregável em JPEG: a recodificação é com perdas e altera pixels "
                "fora das caixas editadas. A garantia de zero drift é verificada no "
                "master PNG antes de gerar o derivado.")

        variations: dict[str, Any] | None = None
        raw_var = d.get("variations")
        if isinstance(raw_var, int) and not isinstance(raw_var, bool):
            raw_var = {"n": raw_var}
        if isinstance(raw_var, dict):
            variations = dict(raw_var)
            variations["n"] = int(variations.get("n") or variations.get("count") or 0)
            variations.pop("count", None)
            variations["mode"] = str(variations.get("mode") or "generative").strip().lower()

        reframe_mode = str(d.get("reframe_mode") or "pad").strip().lower()
        if target is not None and reframe_mode == "outpaint" and not getattr(
                settings, "openai_api_key", None):
            warnings.append(
                "reframe_mode: outpaint exige a chave da OpenAI, que não foi "
                "encontrada — o lote vai cair no modo 'pad' (offline).")

        notes_raw = d.get("notes")
        notes = ([str(notes_raw)] if isinstance(notes_raw, str)
                 else [str(n) for n in (notes_raw or [])])

        return cls(
            job=job,
            input_dir=input_dir,
            output_dir=output_dir,
            engine=engine,
            operations=operations,
            deliver=deliver,
            target=target,
            variations=variations,
            raw=dict(data),
            reframe_mode=reframe_mode,
            reframe_fill=d.get("reframe_fill", "blur"),
            reframe_prompt=d.get("reframe_prompt"),
            long_edge=int(d.get("long_edge") or 1440),
            recursive=bool(d.get("recursive", False)),
            quality=(str(d["quality"]).strip().lower() if d.get("quality") else None),
            notes=notes,
            warnings=warnings,
            path=p,
        )


def _format_issues(issues: Sequence[_Issue], lines: dict[tuple[Any, ...], int],
                   path: Any = None) -> str:
    """Erro de receita como o usuário quer ler: numerado, sem traceback."""
    onde = f" ({path})" if path else ""
    cab = (f"Receita inválida{onde}: {len(issues)} problema"
           f"{'s' if len(issues) > 1 else ''} encontrado"
           f"{'s' if len(issues) > 1 else ''}.")
    corpo = "\n".join(f"  {i}. {iss.render(lines)}" for i, iss in enumerate(issues, 1))
    return (f"{cab}\n{corpo}\n"
            "  Dica: rode 's7editor init' para gerar uma receita de exemplo válida.")


# --------------------------------------------------------------------------- #
# Carregamento
# --------------------------------------------------------------------------- #
def _find_recipe_file(path: Any, root: Path) -> Path:
    """Aceita 'trocar-cta', 'trocar-cta.yaml' ou um caminho completo."""
    p = Path(str(path)).expanduser()
    candidatos: list[Path] = []
    bases = [p] if p.is_absolute() else [p, root / p, root / "recipes" / p]
    for b in bases:
        candidatos.append(b)
        if not b.suffix:
            candidatos += [b.with_suffix(".yaml"), b.with_suffix(".yml"),
                           b.with_suffix(".json")]
    for c in candidatos:
        if c.is_file():
            return c.resolve()
    exemplos = ", ".join(sorted(EXAMPLE_RECIPES))
    raise RecipeError(
        f"Receita não encontrada: {path}\n"
        f"  Procurei em: {', '.join(str(c) for c in candidatos[:4])}\n"
        f"  Para criar uma pronta: s7editor init --recipe <{exemplos}>")


def load_recipe(path: Any, settings: Any = None) -> Recipe:
    """Lê, valida e resolve uma receita YAML (ou JSON).

    Caminhos relativos dentro da receita partem de ``settings.root``, nunca do
    diretório de onde o comando foi chamado.

    Levanta :class:`RecipeError` com uma mensagem pronta para o usuário —
    nenhum traceback deve chegar ao terminal por receita malformada.
    """
    if settings is None:
        from .config import load_settings
        settings = load_settings()
    root = Path(getattr(settings, "root", Path.cwd()))

    p = _find_recipe_file(path, root)
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = p.read_text(encoding="latin-1")
        except OSError as exc:
            raise RecipeError(f"Não consegui ler a receita {p}: {exc}") from exc
    except OSError as exc:
        raise RecipeError(f"Não consegui ler a receita {p}: {exc}") from exc

    if not text.strip():
        raise RecipeError(
            f"A receita {p} está vazia.\n"
            "  Rode 's7editor init' para gerar um exemplo comentado.")

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        onde = (f" (linha {mark.line + 1}, coluna {mark.column + 1})"
                if mark is not None else "")
        problema = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        raise RecipeError(
            f"Erro de sintaxe no YAML{onde} de {p.name}: {problema}.\n"
            "  Causas comuns: indentação com TAB (use espaços), dois-pontos sem "
            "espaço depois, ou aspas não fechadas.") from exc

    return Recipe.from_dict(data, settings, path=p, text=text)


# --------------------------------------------------------------------------- #
# Exemplos (usados por `s7editor init`)
# --------------------------------------------------------------------------- #
EXAMPLE_RECIPES: dict[str, str] = {
    "trocar-cta": """\
# Trocar o CTA de um lote inteiro SEM MEXER EM MAIS NADA.
#
# engine: deterministic => 100% offline, sem chave de API, e os pixels fora da
# caixa do texto ficam idênticos aos do original (verificado pixel a pixel).
job: trocar-cta-setembro
input: inbox/campanha-agosto        # relativo à raiz do projeto
output: outbox/campanha-setembro
engine: deterministic

operations:
  # 1) Acha pelo texto atual. 'match: fuzzy' ignora acento, caixa e pontuação.
  - type: replace_text
    find: "GARANTA O SEU"
    replace: "ULTIMAS VAGAS"
    match: fuzzy

  # 2) Acha pelo papel do bloco (headline, subhead, cta, price, badge, legal...).
  #    'scope' limita a operação a alguns arquivos do lote.
  - type: replace_text
    role: cta
    replace: "COMPRE AGORA"
    scope: "*.png"

  # 3) Acha pela posição. Com 'norm: true' os valores são fração da imagem,
  #    então a mesma caixa serve para criativos de tamanhos diferentes.
  - type: replace_text
    box: {x: 0.1, y: 0.82, w: 0.8, h: 0.07, norm: true}
    replace: "FRETE GRATIS"
    style: {color: "#ffffff", weight: bold, uppercase: true}

deliver:
  zip: true
  report: true
""",
    "reframe-16x9": """\
# Converter um lote de 9:16 para 16:9 sem distorcer nada.
#
# 'relayout' apaga o texto, estende o fundo e redesenha o texto no novo
# enquadramento — o conteúdo não é esticado, só reposicionado.
# Modos: pad (borrão nas laterais, offline) | crop | relayout | outpaint (IA).
job: campanha-agosto-16x9
input: inbox/campanha-agosto
output: outbox/campanha-agosto-16x9
engine: auto

target: "16:9"          # aceita também "1920x1080" ou "16:9@1920"
reframe_mode: relayout
reframe_fill: blur      # sobra das laterais no modo pad/relayout
long_edge: 1920

deliver:
  zip: true
  report: true
  contact_sheet: true
""",
    "variacoes-30": """\
# Mandar criativos de referência e receber outros parecidos, com variações.
#
# O lote lê o "DNA" das referências (paleta, tipografia, arquétipo de layout,
# padrões de copy) e gera novos criativos no mesmo espírito.
# Precisa da OPENAI_API_KEY configurada.
job: variacoes-setembro
input: inbox/referencias
output: outbox/variacoes-setembro
engine: ai

variations:
  n: 30
  mode: generative      # generative | remix | copy | hybrid
  aspect: "9:16"

deliver:
  zip: true
  report: true
  contact_sheet: true
""",
}


def write_example(name: str, dest: Any) -> Path:
    """Grava uma receita de exemplo em ``dest`` (arquivo ou pasta)."""
    if name not in EXAMPLE_RECIPES:
        raise RecipeError(
            f"Não conheço a receita de exemplo {name!r}. "
            f"Disponíveis: {', '.join(sorted(EXAMPLE_RECIPES))}.")
    p = Path(str(dest)).expanduser()
    if p.is_dir() or not p.suffix:
        p = p / f"{name}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(EXAMPLE_RECIPES[name], encoding="utf-8")
    return p
