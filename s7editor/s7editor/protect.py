"""Garantia de zero drift do S7 Editor.

Este é o módulo mais importante do projeto, e o mais chato de propósito.

O cliente pede "troca só o CTA". A promessa que vendemos é literal: **os pixels
fora da caixa editada saem byte a byte iguais aos que entraram**. Não "quase
iguais", não "visualmente idênticos". Quem faz essa promessa valer é aqui:

* :func:`build_mask` transforma caixas em uma máscara "L" onde ``255`` marca o
  que *pode* mudar. Quando há ``feather``, a rampa cresce **para dentro** da
  caixa — nunca para fora —, então a região permitida continua sendo um
  subconjunto exato das caixas declaradas.
* :func:`protected_composite` monta o entregável partindo de uma **cópia do
  original** e só escreve onde a máscara autoriza. Pixel com máscara ``0``
  jamais é lido de volta nem recomposto: ele é o byte original. É isso que
  torna a garantia aritmética, não estatística.
* :func:`drift_report` e :func:`assert_untouched` são a auditoria: comparam
  arrays em memória e contam quantos pixels mudaram onde não podiam.

Três armadilhas que este módulo evita conscientemente
----------------------------------------------------
1. **Conversão de modo/espaço de cor no caminho.** ``img.convert("RGB")`` ida
   e volta, ``cvtColor`` global, ou um ``resize`` da imagem inteira já bastam
   para mexer em milhões de pixels. Aqui o *original* nunca é convertido nem
   reamostrado; quando há divergência de modo ou de tamanho, quem se ajusta é
   sempre a imagem *editada* (que é descartável).
2. **Filtro global.** O ``GaussianBlur`` do ``feather`` roda na máscara, não na
   imagem.
3. **Verificar depois de salvar em JPEG.** A checagem tem que rodar em memória,
   antes de codificar — a DCT em blocos 8×8 (16×16 com croma 4:2:0) espalha
   qualquer alteração para fora da caixa e a garantia vira lixo. Ver
   ``imageio_util.save_image``: o master é sempre PNG.

Convenção da máscara: ``"L"``, ``255`` = **pode mudar**, ``0`` = **protegido**.
É o inverso da máscara da API de imagens da OpenAI; a conversão fica em
``aigen``, não aqui.
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

import numpy as np
from PIL import Image, ImageFilter

from .models import Box

try:  # pragma: no cover - cv2 é dependência do projeto, mas não deve ser fatal aqui
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]

__all__ = [
    "build_mask",
    "protected_composite",
    "drift_report",
    "assert_untouched",
    "drift_details",
    "boxes_to_bool",
    "MaskLike",
    "BoxesLike",
]

# Tipos aceitos onde o contrato fala em "máscara" ou "caixas". Ser permissivo na
# entrada é o que evita que outro módulo faça a conversão errada por conta.
MaskLike = "Image.Image | np.ndarray | Sequence[Any] | Box | None"
BoxesLike = "Sequence[Any] | Box | Image.Image | np.ndarray | None"

# Modos de imagem em que aritmética de pixel faz sentido. "P" (paleta) fica de
# fora: misturar índices de paleta produz cor aleatória, não interpolação.
_ARITHMETIC_MODES = {"L", "LA", "RGB", "RGBA", "I;16", "F"}


# --------------------------------------------------------------------------- #
# Utilidades internas
# --------------------------------------------------------------------------- #
def _as_size(size: Any) -> tuple[int, int]:
    """Aceita ``(w, h)``, ``Image`` ou array ``(H, W, ...)`` e devolve ``(w, h)``."""
    if isinstance(size, Image.Image):
        return (int(size.width), int(size.height))
    if isinstance(size, np.ndarray):
        if size.ndim < 2:
            raise ValueError("array sem dimensão de imagem: esperado (H, W) ou (H, W, C)")
        return (int(size.shape[1]), int(size.shape[0]))
    if isinstance(size, (tuple, list)) and len(size) >= 2:
        w, h = int(size[0]), int(size[1])
        if w <= 0 or h <= 0:
            raise ValueError(f"tamanho inválido: {(w, h)!r} — largura e altura têm que ser > 0")
        return (w, h)
    raise ValueError(
        f"tamanho inválido: {size!r}. Use (largura, altura), uma imagem PIL ou um array numpy."
    )


def _iter_boxes(raw: Any, img_w: int, img_h: int) -> list[Box]:
    """Normaliza qualquer jeito razoável de escrever caixas para ``list[Box]``.

    Aceita ``Box``, dict (normalizado ou em pixels), ``[x, y, w, h]`` e listas
    de qualquer um deles. Delega a ambiguidade norm/pixel para ``Box.from_any``,
    que é o contrato congelado.
    """
    if raw is None:
        return []
    if isinstance(raw, (str, bytes)):
        # str é iterável: sem este atalho, "cta" viraria recursão sobre 'c','t','a'.
        raise ValueError(
            f"caixa inválida: {raw!r} — isto é texto, não uma caixa. "
            "Use Box(x, y, w, h), [x, y, w, h] ou {'x':..,'y':..,'w':..,'h':..}."
        )
    if isinstance(raw, Box):
        return [raw.clamp(img_w, img_h)]
    if isinstance(raw, dict):
        return [Box.from_any(raw, img_w, img_h)]
    if isinstance(raw, (tuple, list)):
        if len(raw) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in raw):
            return [Box.from_any(list(raw), img_w, img_h)]
        out: list[Box] = []
        for item in raw:
            out.extend(_iter_boxes(item, img_w, img_h))
        return out
    if isinstance(raw, Iterable):
        out = []
        for item in raw:
            out.extend(_iter_boxes(item, img_w, img_h))
        return out
    raise ValueError(f"caixa inválida: {raw!r} — use Box, [x, y, w, h] ou dict com x/y/w/h")


def boxes_to_bool(boxes: Any, img_w: int, img_h: int) -> np.ndarray:
    """Máscara booleana ``(H, W)`` com ``True`` dentro das caixas.

    Também aceita receber uma máscara pronta (imagem "L"/"1" ou array), caso em
    que ``> 0`` vira ``True``. É o que permite auditar tanto uma edição descrita
    por caixas quanto uma descrita por máscara arbitrária.
    """
    if isinstance(boxes, Image.Image):
        arr = np.asarray(boxes)
        if arr.ndim == 3:
            arr = arr[..., 0]
        return _match_shape(arr > 0, img_h, img_w)
    if isinstance(boxes, np.ndarray) and boxes.ndim >= 2 and boxes.shape[:2] == (img_h, img_w):
        arr = boxes if boxes.ndim == 2 else boxes[..., 0]
        return arr > 0

    allowed = np.zeros((img_h, img_w), dtype=bool)
    for b in _iter_boxes(boxes, img_w, img_h):
        if b.w <= 0 or b.h <= 0:
            continue
        allowed[b.y:b.y1, b.x:b.x1] = True
    return allowed


def _match_shape(mask: np.ndarray, img_h: int, img_w: int) -> np.ndarray:
    if mask.shape[:2] == (img_h, img_w):
        return mask
    raise ValueError(
        f"máscara {mask.shape[1]}x{mask.shape[0]} não bate com a imagem {img_w}x{img_h}. "
        "Gere a máscara com build_mask(imagem.size, caixas)."
    )


def _to_array(img: Any, *, name: str) -> np.ndarray:
    """``Image`` ou array -> ``np.ndarray`` uint8, **sem conversão de modo**."""
    if isinstance(img, np.ndarray):
        return img
    if isinstance(img, Image.Image):
        if img.mode == "P":
            raise ValueError(
                f"{name} está em modo paleta ('P'), onde comparar/compor pixels não faz sentido. "
                "Abra com imageio_util.load_image(), que já entrega RGB/RGBA."
            )
        return np.asarray(img)
    raise ValueError(f"{name} inválido: esperado imagem PIL ou array numpy, veio {type(img).__name__}")


def _erode(mask: np.ndarray, px: int) -> np.ndarray:
    """Erosão morfológica de uma máscara uint8 por um quadrado ``(2*px+1)``.

    Erosão de verdade na união das caixas, não encolhimento caixa a caixa: duas
    caixas encostadas continuam sendo uma região só, sem costura no meio.
    """
    if px <= 0:
        return mask
    if cv2 is not None:
        k = np.ones((2 * px + 1, 2 * px + 1), np.uint8)
        return cv2.erode(mask, k)
    # Sem cv2: MinFilter(3) repetido px vezes é exatamente a mesma erosão.
    img = Image.fromarray(mask, "L")
    for _ in range(px):
        img = img.filter(ImageFilter.MinFilter(3))
    return np.asarray(img)


# --------------------------------------------------------------------------- #
# Máscara
# --------------------------------------------------------------------------- #
def build_mask(
    size: Any,
    boxes: Any,
    *,
    feather: int = 0,
    invert: bool = False,
) -> Image.Image:
    """Máscara "L" do tamanho da imagem: ``255`` = pode mudar, ``0`` = protegido.

    Parâmetros
    ----------
    size:
        ``(largura, altura)`` na convenção do PIL. Também aceita uma imagem ou
        um array, para evitar que o chamador troque a ordem sem querer.
    boxes:
        ``Box``, ``[x, y, w, h]``, dict normalizado ou lista de qualquer um.
    feather:
        Suavização da borda, em pixels. **A rampa cresce para dentro**: a
        máscara é erodida em ``feather`` px e só então borrada, e o resultado é
        limitado pelo retângulo original (``min`` com a máscara dura). Isso
        garante que ``mask > 0`` continue contido nas caixas declaradas — se o
        feather vazasse para fora, ele destruiria a garantia de zero drift
        exatamente na borda, que é onde ninguém olha.
        Se uma caixa for fina demais para a rampa pedida, o feather é reduzido
        para o maior valor que ainda deixa um núcleo opaco de 1 px.
    invert:
        Inverte o resultado (``255`` fora das caixas). Útil para "mude tudo
        MENOS aqui" — por exemplo proteger logo e rosto num outpaint.
    """
    w, h = _as_size(size)
    box_list = _iter_boxes(boxes, w, h)

    hard = np.zeros((h, w), dtype=np.uint8)
    for b in box_list:
        if b.w > 0 and b.h > 0:
            hard[b.y:b.y1, b.x:b.x1] = 255

    feather = max(0, int(feather))
    if feather and box_list:
        # Não deixa o feather engolir a caixa inteira: sobra sempre 1 px de núcleo.
        min_side = min(min(b.w, b.h) for b in box_list if b.w > 0 and b.h > 0) if any(
            b.w > 0 and b.h > 0 for b in box_list
        ) else 0
        feather = min(feather, max(0, (min_side - 1) // 2))

    if feather and hard.any():
        soft_img = Image.fromarray(_erode(hard, feather), "L")
        # radius do PIL é o sigma; ~feather/2 põe a rampa quase toda dentro dos
        # `feather` px erodidos, e o clip abaixo cuida do resto.
        soft_img = soft_img.filter(ImageFilter.GaussianBlur(radius=feather / 2.0))
        mask = np.minimum(np.asarray(soft_img), hard)   # confinamento explícito
    else:
        mask = hard

    if invert:
        mask = 255 - mask
    return Image.fromarray(np.ascontiguousarray(mask), "L")


# --------------------------------------------------------------------------- #
# Composição protegida
# --------------------------------------------------------------------------- #
def protected_composite(original: Any, edited: Any, allow: Any) -> Image.Image:
    """Original com a região autorizada da versão editada colada por cima.

    Esta é a única função do projeto autorizada a produzir o entregável de uma
    edição por IA. O resultado **começa como cópia do original** e recebe
    escrita apenas onde ``allow > 0``:

    * ``allow == 0``   -> byte do original, copiado, nunca recomposto;
    * ``allow == 255`` -> byte do editado, sem blend (não há erro de arredondamento);
    * intermediário    -> blend linear ``orig + (edit - orig) * a/255``, arredondado.

    Com ``feather=0`` a máscara só tem 0 e 255, logo **fora das caixas o
    resultado é byte a byte idêntico ao original** — verificável com
    :func:`assert_untouched`.

    ``allow`` aceita máscara "L"/"1", array booleano/uint8 ou a própria lista de
    caixas (nesse caso vira máscara dura na hora).

    Risco do reescalonamento
    ------------------------
    Se ``edited`` tiver tamanho diferente do original, ele é reamostrado
    (LANCZOS) para o tamanho do original. Isso é conveniente — modelos de imagem
    devolvem 1024×1536 quando o master é 1080×1620 — mas **não é neutro**:
    a reamostragem desloca conteúdo em subpixel e amacia bordas, então o que
    entra na caixa não é exatamente o que o modelo gerou, e uma máscara
    calculada no espaço do editado deixa de casar com a do original. A garantia
    de zero drift *fora* das caixas continua intacta (o original nunca é
    reamostrado), mas *dentro* da caixa pode aparecer costura. O caminho certo é
    o chamador gerar/recortar no tamanho do master; o rescale aqui é rede de
    segurança, e emite ``UserWarning``.

    Metadados (``icc_profile``, EXIF) do original são preservados no resultado:
    PNG sem o ICC tem pixels idênticos e mesmo assim "parece diferente" no
    navegador.
    """
    if not isinstance(original, Image.Image):
        orig_img = None
        orig = _to_array(original, name="original")
        mode = None
    else:
        orig_img = original
        if original.mode not in _ARITHMETIC_MODES:
            raise ValueError(
                f"modo de imagem não suportado no original: {original.mode!r}. "
                "Abra com imageio_util.load_image(), que entrega RGB/RGBA."
            )
        orig = np.asarray(original)
        mode = original.mode

    h, w = orig.shape[:2]

    # -- alinha o EDITADO ao original (nunca o contrário) ------------------- #
    if isinstance(edited, Image.Image):
        ed_img = edited
        if ed_img.size != (w, h):
            import warnings

            warnings.warn(
                f"editado {ed_img.width}x{ed_img.height} != original {w}x{h}: "
                "reescalando o editado (LANCZOS). Pode aparecer costura dentro da caixa.",
                UserWarning,
                stacklevel=2,
            )
            ed_img = ed_img.resize((w, h), Image.Resampling.LANCZOS)
        if mode is not None and ed_img.mode != mode:
            ed_img = ed_img.convert(mode)   # converte o descartável, não o original
        ed = np.asarray(ed_img)
    else:
        ed = _to_array(edited, name="editado")
        if ed.shape[:2] != (h, w):
            import warnings

            warnings.warn(
                f"editado {ed.shape[1]}x{ed.shape[0]} != original {w}x{h}: "
                "reescalando o editado (LANCZOS). Pode aparecer costura dentro da caixa.",
                UserWarning,
                stacklevel=2,
            )
            tmp = Image.fromarray(np.ascontiguousarray(ed.astype(np.uint8)))
            ed = np.asarray(tmp.resize((w, h), Image.Resampling.LANCZOS))

    # Ajuste de nº de canais: de novo, quem cede é o editado.
    oc = 1 if orig.ndim == 2 else orig.shape[2]
    ec = 1 if ed.ndim == 2 else ed.shape[2]
    if ec != oc:
        if ec > oc:
            ed = ed[..., :oc] if oc > 1 else ed[..., 0]
        else:
            # Canal faltando num array cru é quase sempre o alfa: preenche opaco.
            # Repetir um canal de cor aqui produziria transparência aleatória.
            base = ed if ed.ndim == 3 else ed[..., None]
            pad = np.full(base.shape[:2] + (oc - ec,), 255, dtype=base.dtype)
            ed = np.concatenate([base, pad], axis=2)
    if ed.ndim != orig.ndim:
        ed = ed.reshape(orig.shape)

    # -- máscara ------------------------------------------------------------ #
    if isinstance(allow, Image.Image):
        a = np.asarray(allow if allow.mode in ("L", "1") else allow.convert("L"))
        if a.dtype == bool:
            a = a.astype(np.uint8) * 255
        a = _match_shape(a, h, w)
    elif isinstance(allow, np.ndarray):
        a = allow[..., 0] if allow.ndim == 3 else allow
        a = (a.astype(np.uint8) * 255) if a.dtype == bool else a.astype(np.uint8)
        a = _match_shape(a, h, w)
    else:
        a = (boxes_to_bool(allow, w, h)).astype(np.uint8) * 255

    # -- escrita ------------------------------------------------------------ #
    out = orig.copy()                      # cópia: o original em si é intocável
    full = a == 255
    if full.any():
        out[full] = ed[full]               # sem aritmética => sem arredondamento
    soft = (a > 0) & (a < 255)
    if soft.any():
        t = (a[soft].astype(np.float32) / 255.0)
        o = orig[soft].astype(np.float32)
        e = ed[soft].astype(np.float32)
        if o.ndim == 2:
            t = t[:, None]
        blended = o + (e - o) * t
        out[soft] = np.clip(np.rint(blended), 0, 255).astype(out.dtype)
    # pixels com a == 0 nunca foram tocados: continuam sendo os bytes do original.

    res = Image.fromarray(np.ascontiguousarray(out), mode) if mode else Image.fromarray(
        np.ascontiguousarray(out)
    )
    if orig_img is not None and orig_img.info:
        res.info.update(orig_img.info)     # icc_profile, exif, dpi...
    return res


# --------------------------------------------------------------------------- #
# Auditoria
# --------------------------------------------------------------------------- #
def _diff_mask(a: np.ndarray, b: np.ndarray, tol: int) -> np.ndarray:
    """``True`` onde os dois arrays diferem acima da tolerância por canal."""
    if a.shape != b.shape:
        raise ValueError(
            f"dimensões diferentes ({a.shape} vs {b.shape}): drift é indefinido. "
            "Compare sempre o master contra o resultado no mesmo tamanho."
        )
    if tol <= 0:
        d = a != b
        return d if d.ndim == 2 else np.any(d, axis=2)
    delta = np.abs(a.astype(np.int32) - b.astype(np.int32))
    delta = delta if delta.ndim == 2 else delta.max(axis=2)
    return delta > int(tol)


def _largest_bbox(mask: np.ndarray) -> Box | None:
    """Bbox da maior região divergente conexa (8-vizinhança).

    Sem cv2 cai para o bbox global de tudo que divergiu — menos informativo,
    mas nunca mentiroso: a região reportada sempre contém o problema.
    """
    if not mask.any():
        return None
    if cv2 is not None:
        n, _lbl, st, _cen = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
        if n > 1:
            i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
            x, y, w, h = (int(v) for v in st[i, :4])
            return Box(x, y, w, h)
    ys, xs = np.nonzero(mask)
    return Box.from_xyxy(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def drift_report(
    original: Any,
    result: Any,
    allow_boxes: Any,
    *,
    tol: int = 0,
) -> tuple[int, Box | None]:
    """Conta pixels alterados FORA das caixas permitidas.

    Devolve ``(quantidade, bbox)``, onde ``bbox`` é a caixa da maior mancha
    divergente conexa (``None`` quando não houve divergência). O valor vai
    direto para ``ImageResult.drift_pixels`` / ``changed_boxes``.

    ``tol`` é a tolerância **por canal**: ``0`` exige igualdade byte a byte
    (o normal, para master PNG); ``2`` é o que se usa quando o entregável é
    JPEG e a requantização global já contaminou a imagem inteira — nesse caso
    o resultado NÃO prova nada e ``ImageResult.untouched_pixels_verified`` deve
    ficar ``None``, nunca ``True``.

    Rode sempre **em memória, antes de salvar**. Depois de um round-trip JPEG a
    resposta é sempre "milhões de pixels", e corretamente.
    """
    a = _to_array(original, name="original")
    b = _to_array(result, name="resultado")
    diff = _diff_mask(a, b, tol)

    h, w = a.shape[:2]
    allowed = boxes_to_bool(allow_boxes, w, h)
    outside = diff & ~allowed
    n = int(np.count_nonzero(outside))
    return (n, _largest_bbox(outside) if n else None)


def drift_details(
    original: Any,
    result: Any,
    allow_boxes: Any,
    *,
    tol: int = 0,
) -> dict[str, Any]:
    """Versão verbosa de :func:`drift_report`, para diagnosticar bug de máscara.

    Além de ``drift_pixels``, devolve ``changed_inside``: se ele vier ``0``, a
    operação não fez nada (bug silencioso); se vier igual à área das caixas, a
    caixa inteira foi repintada em vez de só os pixels da máscara — os dois
    casos passam em ``assert_untouched`` e mesmo assim estão errados.
    """
    a = _to_array(original, name="original")
    b = _to_array(result, name="resultado")
    diff = _diff_mask(a, b, tol)

    h, w = a.shape[:2]
    allowed = boxes_to_bool(allow_boxes, w, h)
    outside = diff & ~allowed
    inside = diff & allowed
    n = int(np.count_nonzero(outside))
    bbox = _largest_bbox(outside) if n else None

    max_delta = 0
    if n:
        d = np.abs(a.astype(np.int32) - b.astype(np.int32))
        d = d if d.ndim == 2 else d.max(axis=2)
        max_delta = int(d[outside].max())

    allowed_area = int(np.count_nonzero(allowed))
    changed_inside = int(np.count_nonzero(inside))
    return {
        "drift_pixels": n,
        "drift_bbox": bbox.to_dict() if bbox else None,
        "max_delta_outside": max_delta,
        "sample": np.argwhere(outside)[:10].tolist(),
        "changed_inside": changed_inside,
        "allowed_area": allowed_area,
        "changed_inside_frac": (changed_inside / allowed_area) if allowed_area else 0.0,
        "tol": int(tol),
        "verified": n == 0,
    }


def assert_untouched(
    original: Any,
    result: Any,
    allow_boxes: Any,
    *,
    tol: int = 0,
    max_pixels: int = 0,
    raise_on_fail: bool = False,
) -> bool:
    """``True`` quando nada mudou fora das caixas permitidas.

    ``max_pixels`` (padrão ``0``) é um orçamento de pixels divergentes; deixe em
    zero. Ele existe só para o caso do entregável ser JPEG, em que a garantia já
    é tolerante por natureza — e aí o manifesto tem que registrar isso.

    Com ``raise_on_fail=True`` levanta ``AssertionError`` com mensagem em
    português em vez de devolver ``False``, para uso em teste.
    """
    n, bbox = drift_report(original, result, allow_boxes, tol=tol)
    ok = n <= max(0, int(max_pixels))
    if not ok and raise_on_fail:
        onde = f" (maior mancha em {bbox.to_dict()})" if bbox else ""
        raise AssertionError(
            f"drift detectado: {n} pixel(s) mudaram fora das caixas permitidas{onde}. "
            "Alguma etapa escreveu fora da máscara ou a imagem foi re-encodada com perdas."
        )
    return ok


# --------------------------------------------------------------------------- #
# Teste de fumaça — `python -m s7editor.protect`
# --------------------------------------------------------------------------- #
def _smoke_test() -> int:
    """Prova as duas afirmações do módulo: drift 0 real, e drift detectável."""
    rng = np.random.default_rng(7)
    w, h = 200, 120

    # Original: degradê + ruído, para nenhum pixel ser "por acaso" igual.
    yy, xx = np.mgrid[0:h, 0:w]
    base = np.stack([xx * 255 // (w - 1), yy * 255 // (h - 1), (xx + yy) % 256], -1)
    base = np.clip(base + rng.integers(-6, 7, (h, w, 3)), 0, 255).astype(np.uint8)
    original = Image.fromarray(base, "RGB")

    # Editado: a IA mexeu na imagem INTEIRA (é sempre isso que acontece).
    ed = np.clip(base.astype(np.int16) + 40, 0, 255).astype(np.uint8)
    ed[35:60, 45:95] = (255, 0, 68)
    edited = Image.fromarray(ed, "RGB")

    box = Box(40, 30, 60, 40)
    falhas: list[str] = []

    # (1) feather=0 => fora das caixas o drift é exatamente 0 ------------- #
    allow = build_mask((w, h), [box], feather=0)
    out = protected_composite(original, edited, allow)
    n, bbox = drift_report(original, out, [box])
    print(f"[1] composicao protegida: drift_pixels={n} bbox={bbox}")
    if n != 0 or bbox is not None:
        falhas.append("drift != 0 com feather=0")
    if not assert_untouched(original, out, [box]):
        falhas.append("assert_untouched devolveu False num caso limpo")

    a_out = np.asarray(out)
    if not np.array_equal(a_out[box.y:box.y1, box.x:box.x1], ed[box.y:box.y1, box.x:box.x1]):
        falhas.append("dentro da caixa nao ficou igual ao editado")
    det = drift_details(original, out, [box])
    print(f"    mudou dentro da caixa: {det['changed_inside']} px de {det['allowed_area']}")
    if det["changed_inside"] == 0:
        falhas.append("nada mudou dentro da caixa (operacao silenciosamente inerte)")

    # Prova byte a byte fora da caixa, sem passar pelo drift_report.
    fora = np.ones((h, w), bool)
    fora[box.y:box.y1, box.x:box.x1] = False
    if not np.array_equal(a_out[fora], base[fora]):
        falhas.append("bytes fora da caixa diferem do original")

    # (2) alteracao proposital fora da caixa E detectada ------------------ #
    tampered = a_out.copy()
    tampered[5, 5, 0] = (int(tampered[5, 5, 0]) + 1) % 256      # 1 pixel, delta 1
    tampered[100:105, 150:155] = 0                              # mancha 5x5
    n2, bbox2 = drift_report(original, Image.fromarray(tampered, "RGB"), [box])
    print(f"[2] sabotagem fora da caixa: drift_pixels={n2} bbox={bbox2}")
    if n2 < 26:
        falhas.append(f"sabotagem nao detectada por completo (esperado >= 26, veio {n2})")
    if bbox2 is None or bbox2.area < 25:
        falhas.append("bbox da maior mancha nao foi reportado")
    if assert_untouched(original, Image.fromarray(tampered, "RGB"), [box]):
        falhas.append("assert_untouched devolveu True com drift real")

    # Um delta de 1 sobrevive a tol=0 e some com tol=2 (politica JPEG).
    tampered2 = a_out.copy()
    tampered2[5, 5, 0] = (int(tampered2[5, 5, 0]) + 1) % 256
    n_t0, _ = drift_report(original, tampered2, [box], tol=0)
    n_t2, _ = drift_report(original, tampered2, [box], tol=2)
    print(f"    tolerancia: tol=0 -> {n_t0}, tol=2 -> {n_t2}")
    if n_t0 != 1 or n_t2 != 0:
        falhas.append("tolerancia por canal nao se comporta como esperado")

    # (3) feather nao vaza para fora da caixa ----------------------------- #
    soft = np.asarray(build_mask((w, h), [box], feather=4))
    if soft[fora].any():
        falhas.append("feather vazou para fora da caixa")
    out_f = protected_composite(original, edited, Image.fromarray(soft, "L"))
    n3, _ = drift_report(original, out_f, [box])
    print(f"[3] feather=4: drift_pixels={n3}, max da mascara={int(soft.max())}")
    if n3 != 0:
        falhas.append("drift != 0 com feather=4")
    if int(soft.max()) != 255:
        falhas.append("feather comeu o nucleo opaco da caixa")

    # (4) invert e caixa minuscula ---------------------------------------- #
    inv = np.asarray(build_mask((w, h), [box], invert=True))
    if inv[box.y:box.y1, box.x:box.x1].any() or not inv[fora].all():
        falhas.append("invert=True nao inverteu corretamente")
    tiny = np.asarray(build_mask((w, h), [Box(10, 10, 3, 3)], feather=6))
    print(f"[4] invert ok; caixa 3x3 com feather=6 -> max={int(tiny.max())}")
    if int(tiny.max()) == 0:
        falhas.append("feather engoliu uma caixa pequena")

    # (5) editado em outro tamanho: reescala e ainda assim nao vaza -------- #
    import warnings

    with warnings.catch_warnings(record=True) as ws:
        warnings.simplefilter("always")
        out_r = protected_composite(original, edited.resize((100, 60)), [box])
    n5, _ = drift_report(original, out_r, [box])
    print(f"[5] editado reescalado: drift_pixels={n5}, avisos={len(ws)}")
    if n5 != 0 or not ws:
        falhas.append("caminho de reescalonamento quebrou a garantia ou nao avisou")

    if falhas:
        print("\nFALHOU:")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("\nOK: garantia de zero drift verificada (composicao limpa e sabotagem detectada).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_smoke_test())
