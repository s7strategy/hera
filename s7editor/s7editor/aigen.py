"""Cliente da API de imagens da OpenAI (gpt-image-*).

Este é o ÚNICO módulo do S7 Editor que fala com a rede. Todo o resto do
projeto é offline. Três regras moldam o desenho daqui:

1. **A IA nunca é dona do resultado final.** Estas funções devolvem *matéria
   prima*. Quem compõe o entregável é ``protect.protected_composite``, que cola
   apenas a região mascarada sobre o ORIGINAL. Por isso ``outpaint`` recola o
   centro nativo por conta própria (ver docstring): o modelo re-sintetiza o
   canvas inteiro, inclusive fora da máscara, e sem a recolagem a garantia de
   integridade do conteúdo original simplesmente não existe.

2. **Nada de rede no import.** O client é construído dentro de cada chamada,
   com a chave vinda de ``config.require_openai``. Importar ``aigen`` num
   ambiente sem ``OPENAI_API_KEY`` é barato e não levanta nada.

3. **``settings.dry_run`` tem que percorrer o pipeline inteiro.** Em dry-run
   devolvemos uma imagem-placeholder do tamanho certo, escrita "PREVIEW — sem
   chamada de IA", sem gastar um centavo. É assim que se testa o lote todo.

Semântica da máscara (é o inverso da intuição de quase todo mundo)
------------------------------------------------------------------
A API define a região editável como **alpha == 0**. Pixel TRANSPARENTE = pode
mudar; pixel OPACO = preservado. Só o canal alfa importa, o RGB é ignorado.
Como ``protect.build_mask`` usa a convenção oposta (máscara "L", 255 = pode
mudar), :func:`edit` aceita as duas formas e converte — ver ``_mask_to_api``.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .config import Settings, price_per_image, require_openai
from .imageio_util import from_png_bytes, load_image, to_png_bytes

__all__ = [
    "ImageAPIError",
    "generate",
    "edit",
    "outpaint",
    "estimate_cost",
    # extras públicos, úteis para reframe.py / pipeline.py
    "GPT_IMAGE_SIZES",
    "pick_api_size",
    "normalize_size",
    "supports_input_fidelity",
    "make_placeholder",
    "MAX_EDIT_IMAGES",
    "MAX_PROMPT_CHARS",
]

log = logging.getLogger("s7editor.aigen")


# --------------------------------------------------------------------------- #
# Constantes da API (confirmadas na spec OpenAPI oficial)
# --------------------------------------------------------------------------- #
#: Os ÚNICOS tamanhos que gpt-image-1 / -mini / -1.5 aceitam. Note que não
#: existe 9:16 nem 16:9 nativo: o mais alto é 2:3 e o mais largo é 3:2.
GPT_IMAGE_SIZES: tuple[str, ...] = ("1024x1024", "1536x1024", "1024x1536")

#: dall-e-2 / dall-e-3 têm outra tabela; mantida só para não quebrar quem pedir.
DALLE_SIZES: tuple[str, ...] = ("256x256", "512x512", "1024x1024", "1792x1024", "1024x1792")

#: gpt-image-2 aceita "LARGURAxALTURA" arbitrário — ambos divisíveis por 16,
#: razão entre 1:3 e 3:1. Detalhe fatal: 1080 NÃO é divisível por 16, então
#: "1080x1920" é rejeitado até nele. Use 1088x1920.
ARBITRARY_SIZE_PREFIXES: tuple[str, ...] = ("gpt-image-2",)

MAX_EDIT_IMAGES = 16          # spec: array de image tem maxItems 16
MAX_PROMPT_CHARS = 32_000     # limite dos modelos gpt-image
MAX_MASK_BYTES = 4 * 1024 * 1024      # spec: máscara PNG < 4 MB
MAX_INPUT_BYTES = 50 * 1024 * 1024    # spec: cada imagem de entrada < 50 MB

#: Backoff pedido no projeto: 2s, 4s, 8s, 16s (4 novas tentativas, 5 no total).
RETRY_DELAYS: tuple[float, ...] = (2.0, 4.0, 8.0, 16.0)

#: Geração de imagem é lenta; o default de 10 min do SDK é curto demais em lote.
DEFAULT_TIMEOUT_S = float(os.environ.get("S7EDITOR_IMAGE_TIMEOUT", "180"))

#: Faixa de mistura marcada como editável PARA DENTRO do original no outpaint.
#: Sem ela o modelo bate numa parede na junção e a costura fica visível.
SEAM_INSET_FRAC = 0.02
SEAM_INSET_RANGE = (4, 24)

_QUALITY_GPT = ("low", "medium", "high", "auto")
_ANCHORS: dict[str, tuple[float, float]] = {
    "center": (0.5, 0.5), "centro": (0.5, 0.5),
    "left": (0.0, 0.5), "esquerda": (0.0, 0.5),
    "right": (1.0, 0.5), "direita": (1.0, 0.5),
    "top": (0.5, 0.0), "topo": (0.5, 0.0),
    "bottom": (0.5, 1.0), "baixo": (0.5, 1.0),
    "top-left": (0.0, 0.0), "top-right": (1.0, 0.0),
    "bottom-left": (0.0, 1.0), "bottom-right": (1.0, 1.0),
}


class ImageAPIError(Exception):
    """Falha ao falar com a API de imagens, já traduzida para português.

    Carrega ``status_code`` e ``code`` quando a API os informou, para que o
    pipeline possa decidir entre pular a imagem e abortar o lote.
    """

    def __init__(self, message: str, *, status_code: int | None = None,
                 code: str | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.retryable = retryable


# --------------------------------------------------------------------------- #
# Modelo: o que cada família aceita
# --------------------------------------------------------------------------- #
def _model_name(settings: Settings | None, override: str | None = None) -> str:
    if override:
        return str(override).strip()
    name = getattr(settings, "image_model", None) if settings else None
    return str(name or "gpt-image-1").strip()


def _is_gpt_image(model: str) -> bool:
    return model.lower().startswith("gpt-image") or model.lower().startswith("chatgpt-image")


def _is_arbitrary_size_model(model: str) -> bool:
    m = model.lower()
    return any(m.startswith(p) for p in ARBITRARY_SIZE_PREFIXES)


def supports_input_fidelity(model: str) -> bool:
    """``input_fidelity`` existe em gpt-image-1 e 1.5+, NÃO no ``-mini``.

    Mandar o parâmetro para o mini é erro 400, então quem chama precisa saber.
    """
    m = model.lower()
    if "mini" in m:
        return False
    return _is_gpt_image(m)


def _allowed_sizes(model: str) -> tuple[str, ...]:
    if _is_gpt_image(model):
        return GPT_IMAGE_SIZES
    return DALLE_SIZES


def _parse_size(size: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"\s*(\d{2,5})\s*[xX×]\s*(\d{2,5})\s*", str(size or ""))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _round16(v: int) -> int:
    return max(16, int(round(v / 16.0)) * 16)


def pick_api_size(model: str, target_w: int, target_h: int, *,
                  long_edge_cap: int = 1536) -> str:
    """Escolhe o ``size`` ACEITO pela API cuja razão é a mais próxima do alvo.

    O alvo do usuário (ex.: 1920x1080) quase nunca é um tamanho válido: para
    gpt-image-1 só existem 1:1, 3:2 e 2:3. Escolhemos pela razão — e não pelo
    número de pixels — porque distorcer a proporção é o único erro realmente
    irrecuperável; resolução se conserta com um LANCZOS depois.
    """
    if target_w <= 0 or target_h <= 0:
        raise ImageAPIError("alvo inválido: largura e altura precisam ser positivas")
    ratio = target_w / target_h

    if _is_arbitrary_size_model(model):
        # gpt-image-2: resolução livre, mas divisível por 16 e razão em [1:3, 3:1].
        r = min(3.0, max(1 / 3.0, ratio))
        if r >= 1.0:
            w = _round16(min(target_w, long_edge_cap))
            h = _round16(w / r)
        else:
            h = _round16(min(target_h, long_edge_cap))
            w = _round16(h * r)
        return f"{w}x{h}"

    best, best_err = _allowed_sizes(model)[0], float("inf")
    for s in _allowed_sizes(model):
        wh = _parse_size(s)
        if not wh:
            continue
        err = abs(np.log((wh[0] / wh[1]) / ratio))
        if err < best_err:
            best, best_err = s, err
    return best


def normalize_size(model: str, size: str | None) -> str:
    """Valida/ajusta um ``size`` pedido, avisando no log quando precisa mudar."""
    s = str(size or "auto").strip().lower().replace(" ", "")
    if s in ("", "auto"):
        return "auto"
    if s in _allowed_sizes(model):
        return s
    wh = _parse_size(s)
    if wh is None:
        raise ImageAPIError(
            f"tamanho inválido: {size!r}. Use 'auto' ou um de: "
            f"{', '.join(_allowed_sizes(model))}."
        )
    if _is_arbitrary_size_model(model):
        w, h = _round16(wh[0]), _round16(wh[1])
        if (w, h) != wh:
            log.warning("tamanho %s ajustado para %dx%d (o modelo exige múltiplos de 16)", s, w, h)
        return f"{w}x{h}"
    snapped = pick_api_size(model, wh[0], wh[1])
    log.warning(
        "o modelo %s não aceita %s; usando %s (razão mais próxima). "
        "Reescale para o tamanho final fora da API.", model, s, snapped,
    )
    return snapped


def _normalize_quality(model: str, quality: str | None, settings: Settings | None) -> str:
    q = str(quality or getattr(settings, "quality", None) or "auto").strip().lower()
    if _is_gpt_image(model):
        return q if q in _QUALITY_GPT else "medium"
    # dall-e: standard | hd
    return {"low": "standard", "medium": "standard", "high": "hd"}.get(q, "standard")


def _resolved_pixels(size: str, fallback: tuple[int, int]) -> tuple[int, int]:
    return _parse_size(size) or fallback


# --------------------------------------------------------------------------- #
# Custo
# --------------------------------------------------------------------------- #
def estimate_cost(model: str, size: str | None = None,
                  quality: str | None = None, n: int = 1) -> float:
    """Custo estimado em USD, consultando a tabela de ``config.PRICING``.

    Tolerante a modelo/tamanho desconhecido: ``config.price_per_image`` cai num
    chute conservador em vez de estourar. Lembre que em ``edits`` as imagens de
    ENTRADA também são cobradas (image input tokens), então isto é um piso —
    a verdade em runtime está em ``response.usage``, que guardamos em
    ``img.info["s7_usage"]``.
    """
    return float(price_per_image(model, size, quality, n))


# --------------------------------------------------------------------------- #
# Cliente + retry
# --------------------------------------------------------------------------- #
def _client(settings: Settings) -> Any:
    """Instancia o client do SDK. NUNCA no import — a chave é lida aqui."""
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - dependência declarada
        raise ImageAPIError(
            "o pacote 'openai' não está instalado neste interpretador.\n"
            "  Instale com: pip install openai"
        ) from exc
    key = require_openai(settings)   # levanta MissingAPIKeyError explicando tudo
    # max_retries=0: o backoff é nosso, para não somar duas políticas de retry.
    return OpenAI(api_key=key, timeout=DEFAULT_TIMEOUT_S, max_retries=0)


_MODERATION_HINTS = (
    "content_policy", "moderation", "safety system", "safety_violation",
    "rejected as a result of our safety", "request was rejected",
)


def _api_message(exc: Exception) -> str:
    """Extrai a mensagem útil de um erro do SDK (o body vem em JSON)."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if body.get("message"):
            return str(body["message"])
    msg = str(exc)
    return msg.strip() or exc.__class__.__name__


def _api_code(exc: Exception) -> str | None:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return err.get("code") or err.get("type")
    return getattr(exc, "code", None)


def _translate(exc: Exception, *, contexto: str) -> ImageAPIError:
    """Converte um erro do SDK num :class:`ImageAPIError` em português."""
    status = getattr(exc, "status_code", None)
    code = _api_code(exc)
    detail = _api_message(exc)
    low = f"{code or ''} {detail}".lower()

    if any(h in low for h in _MODERATION_HINTS):
        return ImageAPIError(
            f"A OpenAI recusou o pedido por política de conteúdo ({contexto}).\n"
            f"  Resposta da API: {detail}\n"
            "  Como resolver: reescreva o prompt sem menção a pessoas reais, marcas\n"
            "  de terceiros, violência ou conteúdo adulto. Este erro NÃO é tentado\n"
            "  de novo — repetir daria a mesma recusa.",
            status_code=status, code=code or "moderation_blocked",
        )
    if status == 400:
        return ImageAPIError(
            f"Pedido inválido para a API de imagens ({contexto}).\n"
            f"  Resposta da API: {detail}\n"
            "  Verifique tamanho, formato dos arquivos (png/webp/jpg) e se a máscara\n"
            "  tem exatamente as mesmas dimensões da imagem.",
            status_code=400, code=code,
        )
    if status == 401:
        return ImageAPIError(
            "Chave da OpenAI recusada (401).\n"
            f"  Resposta da API: {detail}\n"
            "  Confira o valor de OPENAI_API_KEY — rode 's7editor doctor' para ver\n"
            "  de qual arquivo a chave foi lida.",
            status_code=401, code=code,
        )
    if status == 403:
        return ImageAPIError(
            "Acesso negado (403): sua organização pode não ter liberação para este modelo.\n"
            f"  Resposta da API: {detail}\n"
            "  Verifique a verificação da organização no painel da OpenAI.",
            status_code=403, code=code,
        )
    if status == 404:
        return ImageAPIError(
            f"Modelo ou endpoint não encontrado (404): {detail}\n"
            "  Confira o nome do modelo em image_model (ex.: gpt-image-1).",
            status_code=404, code=code,
        )
    if status == 429:
        return ImageAPIError(
            "Limite de uso da OpenAI atingido (429) e as tentativas se esgotaram.\n"
            f"  Resposta da API: {detail}\n"
            "  Reduza max_concurrency, espere alguns minutos ou suba o tier da conta.",
            status_code=429, code=code, retryable=True,
        )
    if status and status >= 500:
        return ImageAPIError(
            f"A API de imagens está indisponível ({status}) e as tentativas se esgotaram.\n"
            f"  Resposta da API: {detail}\n"
            "  Isso costuma ser temporário — tente de novo em alguns minutos.",
            status_code=status, code=code, retryable=True,
        )
    return ImageAPIError(
        f"Falha ao chamar a API de imagens ({contexto}): {detail}",
        status_code=status, code=code,
    )


def _retry_after(exc: Exception) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    try:
        return max(0.0, min(60.0, float(raw)))
    except (TypeError, ValueError):
        return None


def _call_with_retry(fn, *, contexto: str) -> Any:
    """Executa ``fn`` com backoff exponencial 2s/4s/8s/16s.

    Só 429, 5xx e falhas de conexão são repetidas. 400, 401, 403, 404 e recusa
    de moderação são definitivos: repetir daria exatamente o mesmo resultado e
    só queimaria tempo do usuário.
    """
    import openai as _oa

    last: Exception | None = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            return fn()
        except (_oa.BadRequestError, _oa.AuthenticationError,
                _oa.PermissionDeniedError, _oa.NotFoundError,
                _oa.UnprocessableEntityError) as exc:
            raise _translate(exc, contexto=contexto) from exc
        except (_oa.RateLimitError, _oa.InternalServerError,
                _oa.APIConnectionError, _oa.APITimeoutError) as exc:
            last = exc
        except _oa.APIStatusError as exc:
            status = getattr(exc, "status_code", 0) or 0
            if status < 500 and status != 429:
                raise _translate(exc, contexto=contexto) from exc
            last = exc
        except ImageAPIError:
            raise
        except Exception as exc:  # erro fora do SDK: não repete às cegas
            raise _translate(exc, contexto=contexto) from exc

        if attempt >= len(RETRY_DELAYS):
            break
        delay = _retry_after(last) or RETRY_DELAYS[attempt]
        delay += random.uniform(0, 0.4)   # jitter: evita sincronizar o lote todo
        log.warning("tentativa %d/%d falhou (%s); repetindo em %.1fs",
                    attempt + 1, len(RETRY_DELAYS) + 1, type(last).__name__, delay)
        time.sleep(delay)

    assert last is not None
    raise _translate(last, contexto=contexto) from last


# --------------------------------------------------------------------------- #
# Decodificação da resposta
# --------------------------------------------------------------------------- #
def _download(url: str) -> Image.Image:
    """Baixa uma imagem por URL.

    Os modelos gpt-image SEMPRE devolvem b64_json, nunca url — mas dall-e-2 usa
    url por padrão e a API pode mudar. Custa cinco linhas cobrir os dois casos.

    O nome do módulo HTTP varia conforme a versão do SDK (``httpx2`` nas novas,
    ``httpx`` nas antigas); ``urllib`` da stdlib fecha o cerco.
    """
    data: bytes | None = None
    erros: list[str] = []
    for mod_name in ("httpx2", "httpx"):
        try:
            mod = __import__(mod_name)
            resp = mod.get(url, timeout=DEFAULT_TIMEOUT_S, follow_redirects=True)
            resp.raise_for_status()
            data = resp.content
            break
        except ImportError:
            continue
        except Exception as exc:
            erros.append(f"{mod_name}: {exc}")
            break
    if data is None and not erros:
        try:
            from urllib.request import urlopen
            with urlopen(url, timeout=DEFAULT_TIMEOUT_S) as fh:   # noqa: S310 (URL da própria API)
                data = fh.read()
        except Exception as exc:
            erros.append(f"urllib: {exc}")
    if data is None:
        raise ImageAPIError("não consegui baixar a imagem gerada: " + "; ".join(erros))
    img = Image.open(io.BytesIO(data))
    img.load()
    return img.convert("RGBA") if img.mode not in ("RGB", "RGBA") else img


def _usage_dict(resp: Any) -> dict[str, Any]:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return {}
    try:
        return usage.model_dump()          # pydantic v2
    except Exception:
        return {k: getattr(usage, k) for k in ("input_tokens", "output_tokens", "total_tokens")
                if getattr(usage, k, None) is not None}


def _decode(resp: Any, *, model: str, size: str, quality: str,
            contexto: str) -> list[Image.Image]:
    data = getattr(resp, "data", None) or []
    out: list[Image.Image] = []
    for item in data:
        b64 = getattr(item, "b64_json", None)
        if b64:
            out.append(from_png_bytes(base64.b64decode(b64)))
            continue
        url = getattr(item, "url", None)
        if url:
            out.append(_download(url))
    if not out:
        raise ImageAPIError(
            f"A API respondeu sem nenhuma imagem ({contexto}). "
            "Isso costuma indicar recusa silenciosa do filtro de conteúdo — "
            "reescreva o prompt e tente de novo."
        )
    usage = _usage_dict(resp)
    cost = estimate_cost(model, size, quality, len(out))
    for img in out:
        # Metadados carregados no próprio objeto: o pipeline lê daqui para
        # preencher ImageResult.cost_usd sem precisar de canal paralelo.
        img.info["s7_engine"] = "ai"
        img.info["s7_model"] = model
        img.info["s7_size"] = getattr(resp, "size", None) or size
        img.info["s7_cost_usd"] = cost / len(out)
        if usage:
            img.info["s7_usage"] = usage
    return out


# --------------------------------------------------------------------------- #
# Placeholder de dry-run
# --------------------------------------------------------------------------- #
def _placeholder_font(size_px: int):
    try:
        from .fonts import resolve_font
        return resolve_font("Inter", "bold", False, size_px)
    except Exception:
        from PIL import ImageFont
        try:
            return ImageFont.load_default(size=size_px)
        except TypeError:                      # Pillow antigo: sem parâmetro size
            return ImageFont.load_default()


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_w: int, start_px: int):
    """Maior corpo (a partir de ``start_px``) em que ``text`` cabe em ``max_w``."""
    px = max(10, int(start_px))
    for _ in range(24):
        font = _placeholder_font(px)
        bb = draw.textbbox((0, 0), text, font=font)
        if bb[2] - bb[0] <= max_w or px <= 10:
            return font
        px = max(10, int(px * min(0.92, max_w / max(1, bb[2] - bb[0]))))
    return _placeholder_font(px)


def _stamp_label(img: Image.Image, text: str, avoid: tuple[int, int, int, int]) -> bool:
    """Carimba uma tarja com o aviso FORA do retângulo ``avoid``.

    No dry-run do :func:`outpaint` o original é colado por cima do placeholder e
    cobriria o texto central. A tarja vai para a faixa gerada — e nunca por cima
    do original, para que ``s7_original_box`` continue verdadeiro até no preview.
    Devolve ``False`` quando não há espaço livre (aí sobra a moldura listrada).
    """
    w, h = img.size
    ax, ay, aw, ah = avoid
    # As quatro faixas livres ao redor do original; fica na de maior área.
    cands = [(0, 0, w, ay), (0, ay + ah, w, h - ay - ah),
             (0, 0, ax, h), (ax + aw, 0, w - ax - aw, h)]
    fx, fy, fw, fh = max(cands, key=lambda r: max(0, r[2]) * max(0, r[3]))
    if fw < 40 or fh < 20:
        return False

    d = ImageDraw.Draw(img)
    pad = max(3, int(min(w, h) * 0.008))
    alvo = min(int(min(w, h) * 0.045), max(10, fh - 4 * pad))
    font = _fit_font(d, text, int(fw * 0.92), alvo)
    bb = d.textbbox((0, 0), text, font=font)
    bw, bh = bb[2] - bb[0] + 2 * pad, bb[3] - bb[1] + 2 * pad
    if bh > fh or bw > fw:
        return False
    x0 = fx + (fw - bw) // 2
    y0 = fy + (fh - bh) // 2
    d.rectangle([x0, y0, x0 + bw, y0 + bh], fill=(24, 26, 32), outline=(255, 176, 32), width=2)
    d.text((x0 + pad - bb[0], y0 + pad - bb[1]), text, font=font, fill=(255, 176, 32))
    return True


def make_placeholder(width: int, height: int, *, prompt: str = "",
                     index: int = 0, label: str = "PREVIEW — sem chamada de IA") -> Image.Image:
    """Imagem de teste para ``settings.dry_run``: nada de rede, custo zero.

    Listrada na diagonal de propósito — se um placeholder vazar para a entrega,
    ninguém confunde com criativo de verdade.
    """
    width, height = max(8, int(width)), max(8, int(height))
    img = Image.new("RGB", (width, height), (24, 26, 32))
    d = ImageDraw.Draw(img)
    step = max(16, min(width, height) // 18)
    for i in range(-height, width, step * 2):
        d.polygon([(i, 0), (i + step, 0), (i + step + height, height), (i + height, height)],
                  fill=(34, 37, 46))
    d.rectangle([0, 0, width - 1, height - 1], outline=(255, 176, 32), width=max(2, step // 8))

    max_w = int(width * 0.88)
    linhas = [
        (label, int(min(width, height) * 0.075), (255, 176, 32)),
        (f"{width}x{height}" + (f"  #{index + 1}" if index else ""),
         int(min(width, height) * 0.035), (200, 205, 215)),
    ]
    if prompt:
        corte = prompt.strip().replace("\n", " ")
        linhas.append((corte[:70] + ("…" if len(corte) > 70 else ""),
                       int(min(width, height) * 0.030), (140, 146, 160)))

    # Encolhe cada linha até caber: o placeholder de um 9:16 estreito não pode
    # sair com o aviso cortado justamente na palavra "PREVIEW".
    prontas = [(t, _fit_font(d, t, max_w, px), cor) for t, px, cor in linhas if t]
    if not prontas:
        img.info["s7_preview"] = True
        img.info["s7_engine"] = "dry_run"
        img.info["s7_cost_usd"] = 0.0
        return img
    caixas = [d.textbbox((0, 0), t, font=f) for t, f, _ in prontas]
    total = sum(bb[3] - bb[1] for bb in caixas) + step * (len(prontas) - 1)
    y = (height - total) // 2
    for (texto, font, cor), bb in zip(prontas, caixas):
        d.text(((width - (bb[2] - bb[0])) // 2 - bb[0], y - bb[1]), texto, font=font, fill=cor)
        y += (bb[3] - bb[1]) + step
    img.info["s7_preview"] = True
    img.info["s7_engine"] = "dry_run"
    img.info["s7_cost_usd"] = 0.0
    return img


# --------------------------------------------------------------------------- #
# Normalização de entrada
# --------------------------------------------------------------------------- #
def _as_image(src: Any) -> Image.Image:
    if isinstance(src, Image.Image):
        return src
    if isinstance(src, (str, Path)):
        return load_image(src)
    if isinstance(src, (bytes, bytearray)):
        return from_png_bytes(bytes(src))
    raise ImageAPIError(
        f"não sei transformar {type(src).__name__} em imagem. "
        "Passe um PIL.Image, um caminho de arquivo ou bytes de PNG."
    )


def _to_upload(img: Image.Image, name: str) -> tuple[str, io.BytesIO, str]:
    """Empacota a imagem como PNG em memória, com nome e mime explícitos.

    O SDK deduz o mime do atributo ``.name`` do file object; sem ele o multipart
    sai como ``application/octet-stream`` e a API recusa. Setamos ``.name`` E
    mandamos a tupla de três, que é a forma inequívoca.
    """
    data = to_png_bytes(img)
    if len(data) > MAX_INPUT_BYTES:
        raise ImageAPIError(
            f"a imagem {name} tem {len(data) / 1e6:.1f} MB e o limite da API é 50 MB. "
            "Reduza a resolução antes de enviar."
        )
    buf = io.BytesIO(data)
    buf.name = name          # noqa: attribute defined outside __init__ (é BytesIO)
    buf.seek(0)
    return (name, buf, "image/png")


def _mask_to_api(mask: Any, size: tuple[int, int]) -> tuple[str, io.BytesIO, str]:
    """Converte e VALIDA a máscara para a convenção da API (alpha 0 = editar).

    Aceita duas convenções, porque o resto do projeto usa a oposta:

    * **RGBA** — já na convenção da API: alpha 0 = pode mudar, 255 = preservar.
    * **"L" / "1"** — convenção do S7 (``protect.build_mask``): 255 = pode mudar.
      Invertemos para o alfa antes de enviar.

    O RGB é zerado de propósito: a API ignora as cores e um PNG preto puro com
    alfa binário fica com poucos KB, longe do teto de 4 MB da máscara.
    """
    m = _as_image(mask)
    if m.size != size:
        raise ImageAPIError(
            f"a máscara tem {m.size[0]}x{m.size[1]} e a imagem tem {size[0]}x{size[1]}.\n"
            "  A API exige dimensões IDÊNTICAS. Redimensione a máscara com "
            "Image.NEAREST (nunca interpole uma máscara) antes de chamar edit()."
        )
    if m.mode == "RGBA":
        alpha = np.asarray(m.split()[-1], dtype=np.uint8)
    elif m.mode in ("L", "1", "P"):
        gray = np.asarray(m.convert("L"), dtype=np.uint8)
        alpha = 255 - gray          # convenção S7 -> convenção da API
    else:
        raise ImageAPIError(
            f"máscara em modo {m.mode!r} não serve. Use RGBA (alpha 0 = região a editar) "
            "ou uma máscara 'L' no padrão do S7 (255 = pode mudar)."
        )
    # Alfa binário: a doc fala em "fully transparent areas"; gradiente é ambíguo.
    alpha = np.where(alpha >= 128, 255, 0).astype(np.uint8)
    if not (alpha == 0).any():
        raise ImageAPIError(
            "a máscara não tem NENHUM pixel editável. Na API, pixel transparente "
            "(alpha=0) é o que pode mudar — o seu está todo opaco, então a edição "
            "não teria efeito. Confira se a convenção não está invertida."
        )
    if (alpha == 0).all():
        log.warning("máscara totalmente transparente: a imagem inteira pode ser regenerada")

    rgb = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    canonical = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
    data = to_png_bytes(canonical)
    if len(data) > MAX_MASK_BYTES:
        raise ImageAPIError(
            f"a máscara ficou com {len(data) / 1e6:.1f} MB e o limite é 4 MB. "
            "Reduza a resolução da imagem antes de editar."
        )
    buf = io.BytesIO(data)
    buf.name = "mask.png"
    buf.seek(0)
    return ("mask.png", buf, "image/png")


def _check_prompt(prompt: str) -> str:
    p = str(prompt or "").strip()
    if not p:
        raise ImageAPIError("o prompt está vazio — descreva o que a IA deve fazer.")
    if len(p) > MAX_PROMPT_CHARS:
        raise ImageAPIError(
            f"o prompt tem {len(p)} caracteres e o limite é {MAX_PROMPT_CHARS}. "
            "Resuma a instrução."
        )
    return p


def _check_n(n: int) -> int:
    n = int(n)
    if n < 1 or n > 10:
        raise ImageAPIError(f"n={n} fora da faixa aceita pela API (1 a 10).")
    return n


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def generate(prompt: str, *, settings: Settings, size: str = "1024x1536",
             n: int = 1, quality: str | None = None,
             model: str | None = None, background: str | None = None) -> list[Image.Image]:
    """Gera ``n`` imagens novas a partir de texto (``POST /v1/images/generations``).

    ``size`` é ajustado para um valor aceito pelo modelo: gpt-image-1 só conhece
    1024x1024, 1536x1024 e 1024x1536 (ou "auto"). Não existe 9:16 nem 16:9
    nativo — para chegar em 1080x1920 gere em 1024x1536 e reenquadre depois.
    """
    prompt = _check_prompt(prompt)
    n = _check_n(n)
    mdl = _model_name(settings, model)
    size_api = normalize_size(mdl, size)
    qual = _normalize_quality(mdl, quality, settings)

    if getattr(settings, "dry_run", False):
        w, h = _resolved_pixels(size_api, (1024, 1536))
        log.info("dry-run: gerando %d placeholder(s) %dx%d em vez de chamar a IA", n, w, h)
        return [make_placeholder(w, h, prompt=prompt, index=i) for i in range(n)]

    client = _client(settings)
    kwargs: dict[str, Any] = {"model": mdl, "prompt": prompt, "n": n, "quality": qual}
    if size_api != "auto" or _is_gpt_image(mdl):
        kwargs["size"] = size_api
    if _is_gpt_image(mdl):
        # response_format NÃO é suportado nos modelos gpt-image (sempre b64).
        kwargs["output_format"] = "png"
        if background:
            kwargs["background"] = background

    resp = _call_with_retry(lambda: client.images.generate(**kwargs), contexto="geração")
    imgs = _decode(resp, model=mdl, size=size_api, quality=qual, contexto="geração")
    log.info("gerou %d imagem(ns) com %s (%s, %s)", len(imgs), mdl, size_api, qual)
    return imgs


def edit(images: Any, prompt: str, *, mask: Any = None, settings: Settings,
         size: str = "auto", n: int = 1, input_fidelity: str = "high",
         model: str | None = None, quality: str | None = None) -> list[Image.Image]:
    """Edita imagens existentes (``POST /v1/images/edits``).

    ``images`` aceita uma imagem só ou uma lista (até 16). Com várias, o modelo
    COMPÕE uma imagem nova usando todas como referência — não é lote de N
    edições. A ``mask``, quando existe, é aplicada apenas na PRIMEIRA imagem.

    ``input_fidelity="high"`` faz o modelo se esforçar para manter estilo e
    traços do input; é preservação perceptual, **não** pixel-perfect, e por isso
    não substitui a composição protegida de ``protect.protected_composite``.
    O parâmetro não existe no ``gpt-image-1-mini`` e é omitido automaticamente.
    """
    prompt = _check_prompt(prompt)
    n = _check_n(n)
    mdl = _model_name(settings, model)
    size_api = normalize_size(mdl, size)
    qual = _normalize_quality(mdl, quality, settings)

    raw = images if isinstance(images, (list, tuple)) else [images]
    if not raw:
        raise ImageAPIError("edit() precisa de pelo menos uma imagem de entrada.")
    if len(raw) > MAX_EDIT_IMAGES:
        raise ImageAPIError(
            f"você passou {len(raw)} imagens e a API aceita no máximo {MAX_EDIT_IMAGES} por edição."
        )
    pil = [_as_image(r) for r in raw]

    if getattr(settings, "dry_run", False):
        w, h = _resolved_pixels(size_api, pil[0].size)
        log.info("dry-run: devolvendo %d placeholder(s) %dx%d em vez de editar", n, w, h)
        return [make_placeholder(w, h, prompt=prompt, index=i) for i in range(n)]

    files = [_to_upload(im, f"input_{i}.png") for i, im in enumerate(pil)]
    kwargs: dict[str, Any] = {
        "model": mdl,
        "prompt": prompt,
        "image": files if len(files) > 1 else files[0],
        "n": n,
        "quality": qual,
    }
    if size_api != "auto" or _is_gpt_image(mdl):
        kwargs["size"] = size_api
    if _is_gpt_image(mdl):
        kwargs["output_format"] = "png"
    if mask is not None:
        kwargs["mask"] = _mask_to_api(mask, pil[0].size)
    if input_fidelity and supports_input_fidelity(mdl):
        fid = str(input_fidelity).strip().lower()
        if fid not in ("high", "low"):
            raise ImageAPIError(f"input_fidelity={input_fidelity!r} inválido (use 'high' ou 'low').")
        kwargs["input_fidelity"] = fid
    elif input_fidelity and input_fidelity != "low":
        log.info("o modelo %s não aceita input_fidelity; parâmetro omitido", mdl)

    client = _client(settings)

    def _do() -> Any:
        # Rebobina os buffers: depois de uma tentativa o BytesIO está no fim do
        # arquivo, e a tentativa seguinte enviaria zero byte — um 400 sem pé nem
        # cabeça. Por isso os uploads são reabertos a cada chamada.
        for key in ("image", "mask"):
            val = kwargs.get(key)
            for item in (val if isinstance(val, list) else [val]):
                if isinstance(item, tuple) and len(item) >= 2 and hasattr(item[1], "seek"):
                    item[1].seek(0)
        return client.images.edit(**kwargs)

    resp = _call_with_retry(_do, contexto="edição")
    imgs = _decode(resp, model=mdl, size=size_api, quality=qual, contexto="edição")
    log.info("editou com %s: %d resultado(s) (%s)", mdl, len(imgs), size_api)
    return imgs


# --------------------------------------------------------------------------- #
# Outpaint
# --------------------------------------------------------------------------- #
def _reflect_pad(arr: np.ndarray, top: int, bottom: int, left: int, right: int) -> np.ndarray:
    """Espelha as bordas até cobrir a extensão pedida (np.pad limita a dim-1)."""
    out = arr
    while top or bottom or left or right:
        h, w = out.shape[:2]
        t, b = min(top, h - 1), min(bottom, h - 1)
        l, r = min(left, w - 1), min(right, w - 1)
        if not (t or b or l or r):
            return np.pad(out, ((top, bottom), (left, right), (0, 0)), mode="edge")
        out = np.pad(out, ((t, b), (l, r), (0, 0)), mode="reflect")
        top -= t
        bottom -= b
        left -= l
        right -= r
    return out


def _seed_canvas(canvas_w: int, canvas_h: int, src: Image.Image,
                 rect: tuple[int, int, int, int], seed: int) -> Image.Image:
    """Semeia a região nova com uma continuação plausível do original.

    Nunca deixe a área nova preta/branca: o modelo lê isso como parte da cena e
    inventa um cenário diferente. Espelhamos as bordas do original, borramos e
    somamos ruído — assim a semente já está cromaticamente coerente, e como o
    original é recolado depois (ver :func:`outpaint`), qualquer vazamento da
    semente é inofensivo.
    """
    ox, oy, ow, oh = rect
    base = np.asarray(src.convert("RGB").resize((ow, oh), Image.Resampling.LANCZOS), dtype=np.uint8)
    padded = _reflect_pad(base, oy, canvas_h - oy - oh, ox, canvas_w - ox - ow)
    canvas = Image.fromarray(padded[:canvas_h, :canvas_w], "RGB")
    canvas = canvas.filter(ImageFilter.GaussianBlur(radius=12))
    rng = np.random.default_rng(seed)
    arr = np.asarray(canvas, dtype=np.float32) + rng.normal(0, 2.0, (canvas_h, canvas_w, 3))
    canvas = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    canvas.paste(Image.fromarray(base, "RGB"), (ox, oy))     # original nítido por cima
    return canvas


def _anchor(placement: str) -> tuple[float, float]:
    key = str(placement or "center").strip().lower()
    if key not in _ANCHORS:
        raise ImageAPIError(
            f"placement={placement!r} desconhecido. Use um de: "
            f"{', '.join(sorted(set(_ANCHORS) - {'centro', 'esquerda', 'direita', 'topo', 'baixo'}))}."
        )
    return _ANCHORS[key]


DEFAULT_OUTPAINT_PROMPT = (
    "Extend the photographic background of this image outward on all sides. "
    "Continue the existing lighting direction, color grade, film grain, depth of field "
    "and perspective. Do not add any people, faces, objects, logos, watermarks or text. "
    "Keep the central region unchanged."
)


def outpaint(img: Image.Image, target_w: int, target_h: int, prompt: str | None = None, *,
             settings: Settings, placement: str = "center",
             model: str | None = None, quality: str | None = None) -> Image.Image:
    """Estende a imagem até ``target_w x target_h`` sem distorcer o conteúdo.

    Por que existe um tamanho intermediário
    ---------------------------------------
    A API não aceita resolução arbitrária: gpt-image-1 só conhece 1024x1024,
    1536x1024 e 1024x1536. Um pedido de 1920x1080 (16:9 = 1,778) não tem
    correspondente — o mais largo é 3:2 = 1,5. Então:

    1. escolhemos o ``size`` VÁLIDO de razão mais próxima do alvo (1536x1024);
    2. dentro dele reservamos o maior retângulo com a razão EXATA do alvo
       (1536x864, centrado, sobrando duas faixas de 80 px que serão descartadas);
    3. posicionamos o original nesse retângulo, preservando a proporção dele;
    4. mascaramos tudo que não é original (mais 2% para dentro, na costura);
    5. recortamos o retângulo de razão exata e reescalamos para o alvo.

    O recorte é o que evita esticamento não uniforme: em nenhum momento a razão
    do conteúdo é alterada, só a resolução.

    Recolagem do centro (obrigatória)
    ---------------------------------
    ``gpt-image-1`` re-sintetiza o canvas inteiro, inclusive fora da máscara —
    os pixels "preservados" voltam com desvios de ±2 a ±15 por canal. Por isso o
    retângulo do original é recolado a partir do master nativo, com LANCZOS, ao
    final. As laterais ficam levemente mais suaves que o centro, que é
    exatamente o comportamento desejado: o sujeito continua sendo o foco.
    """
    if not isinstance(img, Image.Image):
        img = _as_image(img)
    target_w, target_h = int(target_w), int(target_h)
    if target_w <= 0 or target_h <= 0:
        raise ImageAPIError("alvo do outpaint inválido: largura e altura precisam ser positivas.")
    sw, sh = img.size
    if sw <= 0 or sh <= 0:
        raise ImageAPIError("imagem de origem com dimensão zero.")

    fx, fy = _anchor(placement)
    prompt = _check_prompt(prompt or DEFAULT_OUTPAINT_PROMPT)
    mdl = _model_name(settings, model)

    # -- 1) posição final do original DENTRO do alvo (contain: nunca distorce) --
    scale = min(target_w / sw, target_h / sh)
    ow_t = max(1, int(round(sw * scale)))
    oh_t = max(1, int(round(sh * scale)))
    ox_t = int(round((target_w - ow_t) * fx))
    oy_t = int(round((target_h - oh_t) * fy))
    ref = img.convert("RGB").resize((ow_t, oh_t), Image.Resampling.LANCZOS)

    # Nada a estender: só reescala. Evita gastar crédito à toa.
    if ow_t >= target_w and oh_t >= target_h:
        out = Image.new("RGB", (target_w, target_h))
        out.paste(ref, (ox_t, oy_t))
        out.info["s7_engine"] = "deterministic"
        out.info["s7_cost_usd"] = 0.0
        out.info["s7_original_box"] = (ox_t, oy_t, ow_t, oh_t)
        return out

    if getattr(settings, "dry_run", False):
        log.info("dry-run: outpaint devolve placeholder %dx%d com o original colado",
                 target_w, target_h)
        # Sem texto no centro: o original é colado por cima e sobraria um aviso
        # pela metade. O recado vai na tarja, dentro da faixa gerada.
        out = make_placeholder(target_w, target_h, label="")
        out.paste(ref, (ox_t, oy_t))
        _stamp_label(out, "PREVIEW — sem chamada de IA", (ox_t, oy_t, ow_t, oh_t))
        out.info["s7_preview"] = True
        out.info["s7_engine"] = "dry_run"
        out.info["s7_cost_usd"] = 0.0
        out.info["s7_original_box"] = (ox_t, oy_t, ow_t, oh_t)
        return out

    # -- 2) canvas da API + retângulo de razão exata do alvo -------------------
    size_api = pick_api_size(mdl, target_w, target_h)
    cw, ch = _resolved_pixels(size_api, (1536, 1024))
    cs = min(cw / target_w, ch / target_h)          # alvo -> canvas
    crop_w = max(1, min(cw, int(round(target_w * cs))))
    crop_h = max(1, min(ch, int(round(target_h * cs))))
    cx, cy = (cw - crop_w) // 2, (ch - crop_h) // 2

    ow_c = max(1, min(crop_w, int(round(ow_t * cs))))
    oh_c = max(1, min(crop_h, int(round(oh_t * cs))))
    ox_c = cx + max(0, min(crop_w - ow_c, int(round(ox_t * cs))))
    oy_c = cy + max(0, min(crop_h - oh_c, int(round(oy_t * cs))))

    canvas = _seed_canvas(cw, ch, img, (ox_c, oy_c, ow_c, oh_c),
                          seed=(sw * 73856093) ^ (sh * 19349663) ^ (target_w * 83492791) ^ target_h)

    # -- 3) máscara: opaco só no miolo do original (alpha 0 = pode mudar) ------
    inset = int(np.clip(round(SEAM_INSET_FRAC * min(ow_c, oh_c)), *SEAM_INSET_RANGE))
    inset = min(inset, max(0, min(ow_c, oh_c) // 2 - 1))
    alpha = np.zeros((ch, cw), dtype=np.uint8)
    alpha[oy_c + inset: oy_c + oh_c - inset, ox_c + inset: ox_c + ow_c - inset] = 255
    if not (alpha == 255).any():                      # original minúsculo: preserva o centro
        alpha[oy_c: oy_c + oh_c, ox_c: ox_c + ow_c] = 255
    mask = Image.fromarray(np.dstack([np.zeros((ch, cw, 3), np.uint8), alpha]), "RGBA")

    gen = edit(canvas, prompt, mask=mask, settings=settings, size=size_api, n=1,
               input_fidelity="high", model=mdl, quality=quality)[0]

    # -- 4) recorte da razão exata + reescala para o alvo ---------------------
    result = gen.convert("RGB")
    if result.size != (cw, ch):
        # A API devolveu outro tamanho: reescala o canvas todo antes de recortar,
        # senão o retângulo cairia no lugar errado.
        log.warning("a API devolveu %dx%d (pedi %dx%d); reescalando antes do recorte",
                    result.size[0], result.size[1], cw, ch)
        result = result.resize((cw, ch), Image.Resampling.LANCZOS)
    out = result.crop((cx, cy, cx + crop_w, cy + crop_h)).resize(
        (target_w, target_h), Image.Resampling.LANCZOS)

    # -- 5) recolagem do centro nativo (não negociável) -----------------------
    out.paste(ref, (ox_t, oy_t))
    if not np.array_equal(np.asarray(out)[oy_t:oy_t + oh_t, ox_t:ox_t + ow_t],
                          np.asarray(ref)):
        raise ImageAPIError("falha interna: o centro original não sobreviveu à recolagem.")

    out.info["s7_engine"] = "ai"
    out.info["s7_model"] = mdl
    out.info["s7_cost_usd"] = float(gen.info.get("s7_cost_usd", 0.0))
    out.info["s7_original_box"] = (ox_t, oy_t, ow_t, oh_t)
    if "s7_usage" in gen.info:
        out.info["s7_usage"] = gen.info["s7_usage"]
    return out
