"""Empacotamento e entrega do lote — o que o usuário efetivamente baixa.

Três saídas, nesta ordem de importância:

1. ``<saida>/<lote>.zip`` — imagens finais + ``manifest.json`` + relatório.
   É o único arquivo que o usuário precisa levar embora.
2. ``relatorio.html`` — página única, **autocontida**, com ANTES x DEPOIS lado a
   lado, o que mudou em cada imagem e o selo de verificação de zero drift.
3. ``contato.png`` — folha de contato para bater o olho nas 30 de uma vez.

Decisão sobre as imagens do relatório (documentada porque muda o resultado)
--------------------------------------------------------------------------
As miniaturas são **sempre embutidas como data URI**, nunca referenciadas. O
motivo é prático: o relatório vai dentro do ZIP, viaja por e-mail e é aberto
com dois cliques em outra máquina — qualquer referência relativa quebraria ou
exigiria carregar os PNGs de 5 MB do lote inteiro só para ver o preview.

Para isso caber, a miniatura é reduzida (lado maior entre 180 e 460 px,
conforme o tamanho do lote) e comprimida em JPEG. Existe um teto global
(:data:`REPORT_EMBED_BUDGET`, 16 MB de HTML); se o lote for grande a ponto de
estourá-lo, as imagens restantes aparecem **sem prévia**, com um link relativo
ao arquivo e um aviso explícito no rodapé. Nunca há CDN, fonte externa ou
``<script src=...>``: o relatório abre offline, em qualquer navegador.
"""
from __future__ import annotations

import base64
import html
import io
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageDraw, ImageFont

from .models import Box, ImageResult, JobManifest

__all__ = [
    "package",
    "build_report_html",
    "make_contact_sheet",
    "REPORT_EMBED_BUDGET",
    "REPORT_THUMB_MAX",
    "REPORT_NAME",
    "SHEET_NAME",
]

# --------------------------------------------------------------------------- #
# Constantes
# --------------------------------------------------------------------------- #
REPORT_THUMB_MAX = 460          # lado maior da miniatura, em px, para lotes pequenos
REPORT_THUMB_QUALITY = 72       # JPEG das miniaturas: ~35 KB por prévia a 460 px
REPORT_EMBED_BUDGET = 16 * 1024 * 1024   # teto de bytes embutidos no HTML
REPORT_NAME = "relatorio.html"
MANIFEST_NAME = "manifest.json"
SHEET_NAME = "contato.png"
ZIP_IMAGES_DIR = "imagens"

# Extensões já comprimidas: guardar sem deflate economiza tempo e não muda o tamanho.
_STORED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".zip", ".gz", ".mp4"}

_BOX_OUTLINE = (255, 46, 136)   # magenta da caixa editada, some com qualquer criativo


# --------------------------------------------------------------------------- #
# Utilidades pequenas
# --------------------------------------------------------------------------- #
def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _slug(text: str) -> str:
    """Nome de arquivo seguro, sem acento e sem espaço."""
    import re
    import unicodedata

    s = unicodedata.normalize("NFKD", str(text or "lote"))
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "lote"


def _fmt_usd(value: float) -> str:
    """Formata em dólar com vírgula decimal — o usuário é brasileiro."""
    v = float(value or 0.0)
    if v <= 0:
        return "US$ 0,00"
    txt = f"{v:,.4f}" if v < 0.01 else f"{v:,.2f}"
    return "US$ " + txt.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _fmt_dt(raw: str) -> str:
    if not raw:
        return "—"
    try:
        return datetime.fromisoformat(str(raw)).strftime("%d/%m/%Y às %H:%M:%S")
    except (TypeError, ValueError):
        return str(raw)


def _fmt_int(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


def _fmt_bytes(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024 or unit == "GB":
            return f"{f:.0f} {unit}" if unit == "B" else f"{f:.1f} {unit}".replace(".", ",")
        f /= 1024
    return f"{f:.1f} GB"


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _link_for(path: Path | None, base_dir: Path | None) -> str:
    """Link relativo quando o arquivo mora dentro da pasta do relatório."""
    if path is None:
        return ""
    p = Path(path)
    if base_dir is not None:
        try:
            return Path(os.path.relpath(p, base_dir)).as_posix()
        except (ValueError, OSError):
            pass
    try:
        return p.resolve().as_uri()
    except (ValueError, OSError):
        return p.as_posix()


# --------------------------------------------------------------------------- #
# Miniaturas
# --------------------------------------------------------------------------- #
def _thumb_max_for(n_images: int) -> int:
    """Lado da miniatura em função do tamanho do lote (ver docstring do módulo)."""
    if n_images <= 60:
        return REPORT_THUMB_MAX
    if n_images <= 150:
        return 340
    if n_images <= 400:
        return 240
    return 180


def _open_flat(path: Path) -> Image.Image:
    """Abre em RGB, achatando alfa sobre branco (miniatura não precisa de canal)."""
    from .imageio_util import load_image

    img = load_image(path)
    if img.mode == "RGBA":
        base = Image.new("RGB", img.size, (255, 255, 255))
        base.paste(img, mask=img.split()[-1])
        return base
    return img.convert("RGB") if img.mode != "RGB" else img


def _thumbnail(path: Path, max_side: int, boxes: Sequence[Box] = ()) -> tuple[Image.Image, float] | None:
    """Miniatura contida em ``max_side`` com as caixas editadas destacadas."""
    try:
        img = _open_flat(Path(path))
    except Exception:  # noqa: BLE001 - arquivo sumiu/corrompido não derruba o relatório
        return None
    w, h = img.size
    if not w or not h:
        return None
    scale = min(1.0, max_side / float(max(w, h)))
    if scale < 1.0:
        img = img.resize((max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                         Image.Resampling.LANCZOS)
    else:
        img = img.copy()
    if boxes:
        # Só anotamos as caixas que fazem sentido NESTA imagem. Num reframe, as
        # caixas alteradas vivem no canvas de destino (16:9) e não descrevem
        # nada no original 9:16 — desenhá-las lá seria mentira, além de estourar.
        cabem = [b for b in boxes
                 if getattr(b, "x", 0) >= 0 and getattr(b, "y", 0) >= 0
                 and getattr(b, "x1", 0) <= w and getattr(b, "y1", 0) <= h]
        _draw_boxes(img, cabem, scale)
    return img, scale


def _draw_boxes(thumb: Image.Image, boxes: Sequence[Box], scale: float) -> None:
    """Contorna, na miniatura, a região que a operação tinha licença de mudar."""
    if not boxes:
        return
    tw, th = thumb.size
    d = ImageDraw.Draw(thumb)
    lw = max(1, int(round(min(tw, th) / 220)) + 1)
    for b in boxes:
        try:
            x0 = max(0, min(tw - 1, int(round(b.x * scale))))
            y0 = max(0, min(th - 1, int(round(b.y * scale))))
            x1 = max(0, min(tw - 1, int(round(b.x1 * scale))))
            y1 = max(0, min(th - 1, int(round(b.y1 * scale))))
        except (AttributeError, TypeError, ValueError):
            continue
        if x1 <= x0 or y1 <= y0:
            continue
        d.rectangle((x0, y0, x1, y1), outline=_BOX_OUTLINE, width=lw)


def _data_uri(img: Image.Image, quality: int = REPORT_THUMB_QUALITY) -> tuple[str, int]:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    raw = buf.getvalue()
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii"), len(raw)


# --------------------------------------------------------------------------- #
# Relatório HTML
# --------------------------------------------------------------------------- #
_CSS = """
:root{
  --bg:#f4f5f7; --card:#ffffff; --ink:#14161a; --muted:#5d6470; --line:#e2e5ea;
  --ok:#0f7b41; --ok-bg:#e4f5ea; --bad:#b0202c; --bad-bg:#fdeaec;
  --warn:#8a5a00; --warn-bg:#fdf3dd; --accent:#ff2e88;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
a{color:#1550c8}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 64px}
header.top{background:#14161a;color:#fff;padding:26px 0 22px}
header.top .wrap{padding-bottom:0}
h1{margin:0 0 4px;font-size:24px;letter-spacing:-.01em}
.sub{color:#b6bcc7;font-size:14px;margin:0}
.seal{margin:18px 0 0;padding:14px 18px;border-radius:10px;font-weight:600;display:flex;
  gap:10px;align-items:center;flex-wrap:wrap}
.seal small{display:block;font-weight:400;opacity:.85;font-size:13px}
.seal.ok{background:var(--ok-bg);color:var(--ok);border:1px solid #bfe5cd}
.seal.bad{background:var(--bad-bg);color:var(--bad);border:1px solid #f3c4c9}
.seal.warn{background:var(--warn-bg);color:var(--warn);border:1px solid #ecd9a6}
.dot{width:11px;height:11px;border-radius:50%;background:currentColor;flex:0 0 auto}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0 8px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.stat b{display:block;font-size:22px;letter-spacing:-.02em}
.stat span{color:var(--muted);font-size:12.5px;text-transform:uppercase;letter-spacing:.04em}
.meta{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0}
.meta dl{display:grid;grid-template-columns:150px 1fr;gap:6px 14px;margin:0;font-size:13.5px}
.meta dt{color:var(--muted)}
.meta dd{margin:0;word-break:break-all}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:22px 0 12px}
.filters button{font:inherit;font-size:13.5px;padding:7px 13px;border-radius:999px;cursor:pointer;
  border:1px solid var(--line);background:var(--card);color:var(--ink)}
.filters button[aria-pressed="true"]{background:#14161a;color:#fff;border-color:#14161a}
.item{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px}
.item.falha{border-color:#f3c4c9}
.item h2{margin:0 0 2px;font-size:16px;word-break:break-all}
.item .path{color:var(--muted);font-size:12.5px;margin:0 0 12px;word-break:break-all}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:720px){.pair{grid-template-columns:1fr}.meta dl{grid-template-columns:1fr}}
.shot{background:repeating-conic-gradient(#eef0f3 0% 25%,#f8f9fa 0% 50%) 50%/16px 16px;
  border:1px solid var(--line);border-radius:8px;padding:8px;text-align:center}
.shot img{max-width:100%;height:auto;display:block;margin:0 auto;border-radius:4px}
.shot .cap{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;
  margin:0 0 7px;font-weight:600}
.shot .none{color:var(--muted);font-size:13px;padding:34px 8px}
.changes{margin:13px 0 0;padding:11px 13px;background:#fafbfc;border:1px solid var(--line);
  border-radius:8px;font-size:13.5px}
.changes ul{margin:6px 0 0;padding-left:20px}
.changes li{margin:2px 0}
.tag{display:inline-block;font-size:12px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);
  background:#f2f4f7;color:var(--muted);margin:0 6px 6px 0}
.tag.mag{border-color:#ffc6df;background:#fff0f7;color:#a3105a}
.badge{display:inline-flex;gap:8px;align-items:center;font-size:13px;font-weight:600;
  padding:7px 11px;border-radius:8px;margin-top:12px}
.badge.ok{background:var(--ok-bg);color:var(--ok)}
.badge.bad{background:var(--bad-bg);color:var(--bad)}
.badge.warn{background:var(--warn-bg);color:var(--warn)}
.aviso{margin-top:10px;font-size:13px;color:var(--warn);background:var(--warn-bg);
  border-radius:8px;padding:8px 11px}
.erro{margin-top:10px;font-size:13px;color:var(--bad);background:var(--bad-bg);
  border-radius:8px;padding:8px 11px}
footer{color:var(--muted);font-size:12.5px;margin-top:34px;border-top:1px solid var(--line);padding-top:16px}
.legend{font-size:12.5px;color:var(--muted);margin-top:6px}
.legend i{display:inline-block;width:22px;height:0;border-top:2px solid var(--accent);
  vertical-align:middle;margin-right:5px}
"""

_JS = """
(function(){
  var botoes = document.querySelectorAll('.filters button');
  function aplica(f){
    document.querySelectorAll('.item').forEach(function(el){
      el.style.display = (f === 'todos' || el.dataset.filtro.indexOf(f) >= 0) ? '' : 'none';
    });
    botoes.forEach(function(b){ b.setAttribute('aria-pressed', b.dataset.f === f ? 'true':'false'); });
  }
  botoes.forEach(function(b){ b.addEventListener('click', function(){ aplica(b.dataset.f); }); });
})();
"""


def _result_state(r: ImageResult) -> tuple[str, str, str]:
    """(classe, título, detalhe) do selo de drift de uma imagem."""
    if not r.ok:
        return ("bad", "Falhou", r.error or "erro não informado")
    if r.drift_pixels and r.drift_pixels > 0:
        return ("bad", f"{_fmt_int(r.drift_pixels)} pixels alterados fora da área editada",
                "o resultado NÃO tem garantia de zero drift")
    if r.untouched_pixels_verified is True:
        return ("ok", "0 pixels alterados fora da área editada",
                "verificado pixel a pixel no master, antes de codificar")
    if r.untouched_pixels_verified is None:
        return ("warn", "Verificação não aplicável",
                "operação que reescreve o quadro inteiro (reenquadrar/gerar) "
                "ou entregável com perdas")
    return ("warn", "Não verificado", "a operação não reportou a checagem de drift")


def _filters_for(r: ImageResult) -> str:
    tags = []
    if r.ok:
        tags.append("ok")
    else:
        tags.append("falha")
    if r.skipped:
        tags.append("pulado")
    if r.drift_pixels:
        tags.append("drift")
    if r.warnings:
        tags.append("aviso")
    return " ".join(tags)


def _op_labels(r: ImageResult) -> list[str]:
    """Descrição legível do que mudou nesta imagem."""
    linhas = [str(o) for o in (r.operations or []) if str(o).strip()]
    if not linhas:
        linhas = ["(nenhuma operação registrada)"]
    return linhas


def build_report_html(
    manifest: JobManifest,
    *,
    base_dir: Path | None = None,
    thumb_max: int | None = None,
    budget: int = REPORT_EMBED_BUDGET,
    extras: dict[str, Path] | None = None,
) -> str:
    """Relatório de uma página, autocontido, em português.

    ``base_dir`` só é usado para gerar links relativos ("abrir arquivo"); as
    prévias em si são embutidas (ver docstring do módulo). ``extras`` aceita
    ``{"zip": Path, "contact_sheet": Path}`` para linkar no cabeçalho.
    """
    results = list(manifest.results or [])
    total = len(results)
    ok = sum(1 for r in results if r.ok)
    falhas = sum(1 for r in results if not r.ok and not r.skipped)
    pulados = sum(1 for r in results if r.skipped)
    drift_total = sum(int(r.drift_pixels or 0) for r in results)
    custo = float(manifest.total_cost_usd or 0.0) or sum(float(r.cost_usd or 0.0) for r in results)

    verificados = [r for r in results if r.ok and r.untouched_pixels_verified is True]
    nao_aplicavel = [r for r in results if r.ok and r.untouched_pixels_verified is None]

    max_side = int(thumb_max or _thumb_max_for(total))
    usado = 0
    omitidas = 0

    p: list[str] = []
    add = p.append

    # ---- cabeçalho ------------------------------------------------------- #
    add("<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">")
    add("<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">")
    add(f"<title>S7 Editor — {_esc(manifest.job)}</title>")
    add(f"<style>{_CSS}</style></head><body>")
    add("<header class=\"top\"><div class=\"wrap\">")
    add(f"<h1>{_esc(manifest.job or 'lote sem nome')}</h1>")
    add(f"<p class=\"sub\">Relatório do lote &middot; {_esc(_fmt_dt(manifest.finished_at or manifest.started_at))}"
        f" &middot; {total} imagem(ns)</p>")
    add("</div></header><div class=\"wrap\">")

    # ---- selo global ----------------------------------------------------- #
    if falhas and drift_total:
        classe = "bad"
        titulo = (f"{_fmt_int(drift_total)} pixels alterados fora da área editada "
                  f"e {falhas} imagem(ns) com falha")
        detalhe = "A garantia de zero drift NÃO se aplica a este lote. Veja os cartões em vermelho."
    elif drift_total:
        classe = "bad"
        titulo = f"{_fmt_int(drift_total)} pixels alterados fora da área editada"
        detalhe = "A garantia de zero drift falhou em pelo menos uma imagem."
    elif falhas:
        classe = "warn"
        titulo = f"{falhas} imagem(ns) não foram processadas"
        detalhe = "As que passaram estão íntegras; veja o motivo em cada cartão."
    elif verificados and not nao_aplicavel:
        classe = "ok"
        titulo = "0 pixels alterados fora da área editada"
        detalhe = (f"Verificado pixel a pixel em {len(verificados)} de {total} imagens, "
                   "no master sem perdas e antes de codificar o arquivo.")
    elif verificados:
        classe = "ok"
        titulo = "0 pixels alterados fora da área editada"
        detalhe = (f"{len(verificados)} imagem(ns) verificadas pixel a pixel; "
                   f"{len(nao_aplicavel)} usaram operação que reescreve o quadro inteiro "
                   "(reenquadrar/gerar), onde a checagem não se aplica.")
    else:
        classe = "warn"
        titulo = "Sem verificação de drift neste lote"
        detalhe = ("Nenhuma operação reportou a checagem — normal em reenquadramento "
                   "e geração, onde a imagem inteira é nova.")
    add(f"<div class=\"seal {classe}\"><span class=\"dot\"></span><span>{_esc(titulo)}"
        f"<small>{_esc(detalhe)}</small></span></div>")

    # ---- números --------------------------------------------------------- #
    add("<div class=\"cards\">")
    for valor, rotulo in (
        (str(total), "imagens no lote"),
        (str(ok), "prontas"),
        (str(falhas), "com falha"),
        (str(pulados), "puladas"),
        (_fmt_usd(custo), "custo estimado"),
    ):
        add(f"<div class=\"stat\"><b>{_esc(valor)}</b><span>{_esc(rotulo)}</span></div>")
    add("</div>")

    # ---- metadados ------------------------------------------------------- #
    add("<div class=\"meta\"><dl>")
    linhas_meta = [
        ("Entrada", manifest.input_dir or "—"),
        ("Saída", manifest.output_dir or "—"),
        ("Receita", manifest.recipe_path or "(sem receita — comando direto)"),
        ("Início", _fmt_dt(manifest.started_at)),
        ("Fim", _fmt_dt(manifest.finished_at)),
    ]
    for rotulo, valor in linhas_meta:
        add(f"<dt>{_esc(rotulo)}</dt><dd>{_esc(valor)}</dd>")
    for nome, chave in (("Pacote ZIP", "zip"), ("Folha de contato", "contact_sheet")):
        alvo = (extras or {}).get(chave)
        if alvo:
            add(f"<dt>{_esc(nome)}</dt><dd><a href=\"{_esc(_link_for(Path(alvo), base_dir))}\">"
                f"{_esc(Path(alvo).name)}</a></dd>")
    add("</dl>")
    if manifest.notes:
        add("<div class=\"changes\"><b>Observações do lote</b><ul>"
            + "".join(f"<li>{_esc(n)}</li>" for n in manifest.notes) + "</ul></div>")
    add("</div>")

    # ---- filtros --------------------------------------------------------- #
    add("<div class=\"filters\">"
        "<button data-f=\"todos\" aria-pressed=\"true\">Todas</button>"
        "<button data-f=\"ok\" aria-pressed=\"false\">Prontas</button>"
        "<button data-f=\"falha\" aria-pressed=\"false\">Com falha</button>"
        "<button data-f=\"drift\" aria-pressed=\"false\">Com drift</button>"
        "<button data-f=\"aviso\" aria-pressed=\"false\">Com aviso</button>"
        "</div>")
    add("<p class=\"legend\"><i></i> contorno magenta = região que a operação tinha "
        "licença para alterar. Fora dela, os pixels são os do original.</p>")

    # ---- um cartão por imagem -------------------------------------------- #
    for r in results:
        boxes = list(r.changed_boxes or [])
        nome = Path(r.output).name if r.output else Path(r.source).name
        add(f"<div class=\"item{'' if r.ok else ' falha'}\" data-filtro=\"{_esc(_filters_for(r))}\">")
        add(f"<h2>{_esc(nome)}</h2>")
        add(f"<p class=\"path\">{_esc(r.source)}</p>")

        add("<div class=\"pair\">")
        for legenda, caminho, com_caixa in (("Antes", r.source, boxes),
                                            ("Depois", r.output, boxes)):
            add("<div class=\"shot\">")
            add(f"<p class=\"cap\">{legenda}</p>")
            if caminho is None:
                add("<div class=\"none\">não gerado</div>")
            elif usado >= budget:
                omitidas += 1
                href = _link_for(Path(caminho), base_dir)
                add(f"<div class=\"none\">prévia omitida (relatório no limite de tamanho)<br>"
                    f"<a href=\"{_esc(href)}\">abrir arquivo</a></div>")
            else:
                try:
                    feito = _thumbnail(Path(caminho), max_side, com_caixa)
                except Exception:  # noqa: BLE001 - prévia é enfeite, nunca causa de falha
                    feito = None
                if feito is None:
                    add("<div class=\"none\">não consegui abrir o arquivo</div>")
                else:
                    uri, nbytes = _data_uri(feito[0])
                    usado += nbytes
                    href = _link_for(Path(caminho), base_dir)
                    add(f"<a href=\"{_esc(href)}\"><img src=\"{uri}\" alt=\"{_esc(legenda)} — {_esc(nome)}\""
                        f" loading=\"lazy\"></a>")
            add("</div>")
        add("</div>")

        # o que mudou
        add("<div class=\"changes\"><b>O que mudou</b><ul>")
        for linha in _op_labels(r):
            add(f"<li>{_esc(linha)}</li>")
        add("</ul>")
        etiquetas: list[str] = []
        if r.engine_used:
            etiquetas.append(f"<span class=\"tag\">motor: {_esc(r.engine_used)}</span>")
        for b in boxes:
            etiquetas.append(f"<span class=\"tag mag\">caixa {b.w}&times;{b.h} em ({b.x},{b.y})</span>")
        if r.duration_s:
            etiquetas.append(f"<span class=\"tag\">{r.duration_s:.2f}s</span>".replace(".", ","))
        if r.cost_usd:
            etiquetas.append(f"<span class=\"tag\">{_esc(_fmt_usd(r.cost_usd))}</span>")
        if etiquetas:
            add("<div style=\"margin-top:9px\">" + "".join(etiquetas) + "</div>")
        add("</div>")

        classe, titulo, detalhe = _result_state(r)
        add(f"<div class=\"badge {classe}\"><span class=\"dot\"></span>{_esc(titulo)} "
            f"<span style=\"font-weight:400;opacity:.8\">— {_esc(detalhe)}</span></div>")
        for w in (r.warnings or []):
            add(f"<div class=\"aviso\">Aviso: {_esc(w)}</div>")
        if r.error:
            add(f"<div class=\"erro\">Erro: {_esc(r.error)}</div>")
        add("</div>")

    if not results:
        add("<div class=\"item\"><h2>Lote vazio</h2><p class=\"path\">Nenhuma imagem foi "
            "processada. Confira se a pasta de entrada tem arquivos .png/.jpg/.webp.</p></div>")

    # ---- rodapé ---------------------------------------------------------- #
    add("<footer>")
    add(f"<p>Miniaturas embutidas no próprio arquivo ({_fmt_bytes(usado)}), lado maior "
        f"{max_side}px — este relatório abre offline, sem internet e sem nenhum arquivo ao lado.</p>")
    if omitidas:
        add(f"<p><b>{omitidas} prévia(s) foram omitidas</b> porque o relatório chegou ao teto de "
            f"{_fmt_bytes(budget)}. Os arquivos continuam no ZIP; use os links para abri-los.</p>")
    add("<p>Garantia de zero drift: as imagens são comparadas pixel a pixel com o original "
        "<i>em memória</i>, antes de virar arquivo. Só vale no master sem perdas (PNG/WebP "
        "lossless); JPEG re-quantiza a imagem inteira e destrói a comparação.</p>")
    add("<p>Gerado por S7 Editor &middot; S7 Strategy.</p>")
    add("</footer></div>")
    add(f"<script>{_JS}</script></body></html>")
    return "".join(p)


# --------------------------------------------------------------------------- #
# Folha de contato
# --------------------------------------------------------------------------- #
def _sheet_font(size: int) -> Any:
    try:
        from .fonts import resolve_font

        return resolve_font("Inter", "regular", False, size)
    except Exception:  # noqa: BLE001 - sem fonte da marca, a default resolve
        try:
            return ImageFont.load_default(size)   # Pillow >= 10.1
        except Exception:  # noqa: BLE001
            return ImageFont.load_default()


def _elide(text: str, font: Any, max_w: int) -> str:
    """Corta o nome no meio ('campanha…-final.png') — o começo e o fim informam."""
    def largura(s: str) -> float:
        try:
            return font.getlength(s)
        except AttributeError:
            return len(s) * 6.0

    if largura(text) <= max_w:
        return text
    cabeca, cauda = text, ""
    if "." in text:
        cabeca, ext = text.rsplit(".", 1)
        cauda = "." + ext
    while cabeca and largura(cabeca + "…" + cauda) > max_w:
        cabeca = cabeca[:-1]
    return (cabeca + "…" + cauda) if cabeca else "…"


def make_contact_sheet(
    paths: Sequence[str | Path],
    out: str | Path,
    *,
    cols: int = 6,
    cell: int = 260,
    label: bool = True,
) -> Path:
    """Grade de miniaturas para conferir o lote inteiro de uma olhada.

    Cada célula é ``cell`` px de largura; a imagem entra contida (nunca
    distorcida) e o nome do arquivo aparece embaixo, cortado no meio quando não
    couber. Levanta ``ValueError`` em português se a lista vier vazia.
    """
    itens = [Path(p) for p in (paths or [])]
    if not itens:
        raise ValueError("Não dá para montar a folha de contato: a lista de imagens está vazia. "
                         "Confira se o lote gerou algum arquivo.")
    cols = max(1, int(cols))
    cell = max(80, int(cell))
    pad = max(6, cell // 26)
    rotulo_h = max(16, cell // 14) if label else 0
    img_h = int(cell * 1.15)
    cell_h = img_h + rotulo_h + pad
    rows = (len(itens) + cols - 1) // cols

    sheet = Image.new("RGB", (cols * (cell + pad) + pad, rows * (cell_h + pad) + pad),
                      (245, 246, 248))
    draw = ImageDraw.Draw(sheet)
    font = _sheet_font(max(10, rotulo_h - 4))

    for i, p in enumerate(itens):
        cx = pad + (i % cols) * (cell + pad)
        cy = pad + (i // cols) * (cell_h + pad)
        draw.rectangle((cx, cy, cx + cell - 1, cy + img_h - 1), fill=(255, 255, 255),
                       outline=(226, 229, 234))
        try:
            thumb = _open_flat(p)
            thumb.thumbnail((cell - 2 * pad, img_h - 2 * pad), Image.Resampling.LANCZOS)
            sheet.paste(thumb, (cx + (cell - thumb.width) // 2,
                                cy + (img_h - thumb.height) // 2))
        except Exception:  # noqa: BLE001 - uma imagem ruim não derruba a folha
            draw.text((cx + cell // 2, cy + img_h // 2), "?", fill=(170, 175, 182),
                      font=font, anchor="mm")
        if label:
            draw.text((cx + cell // 2, cy + img_h + rotulo_h // 2),
                      _elide(p.name, font, cell - 6), fill=(93, 100, 112),
                      font=font, anchor="mm")

    destino = Path(out)
    if destino.is_dir() or not destino.suffix:
        destino = destino / SHEET_NAME
    destino.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destino, "PNG", optimize=True)
    return destino


# --------------------------------------------------------------------------- #
# Empacotamento
# --------------------------------------------------------------------------- #
def _outputs(manifest: JobManifest) -> list[Path]:
    """Arquivos finais existentes, na ordem do manifesto e sem repetição."""
    vistos: set[str] = set()
    saida: list[Path] = []
    for r in manifest.results or []:
        if not r.output:
            continue
        p = Path(r.output)
        chave = str(p.resolve()) if p.exists() else str(p)
        if chave in vistos or not p.exists():
            continue
        vistos.add(chave)
        saida.append(p)
    return saida


def _zip_names(files: Sequence[Path]) -> list[tuple[Path, str]]:
    """Nomes dentro do ZIP, resolvendo colisão de nome entre pastas diferentes."""
    usados: set[str] = set()
    pares: list[tuple[Path, str]] = []
    for p in files:
        nome = p.name
        if nome.lower() in usados:
            i = 2
            while f"{p.stem}-{i}{p.suffix}".lower() in usados:
                i += 1
            nome = f"{p.stem}-{i}{p.suffix}"
        usados.add(nome.lower())
        pares.append((p, f"{ZIP_IMAGES_DIR}/{nome}"))
    return pares


def _write_zip(destino: Path, arquivos: Sequence[tuple[Path, str]],
               avulsos: Sequence[tuple[Path, str]]) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for origem, nome in list(arquivos) + list(avulsos):
            if origem.resolve() == destino.resolve() or not origem.exists():
                continue
            metodo = (zipfile.ZIP_STORED if origem.suffix.lower() in _STORED_EXT
                      else zipfile.ZIP_DEFLATED)
            z.write(origem, nome, compress_type=metodo)
    return destino


def package(
    manifest: JobManifest,
    out_dir: str | Path,
    *,
    make_zip: bool = True,
    make_report: bool = True,
    make_sheet: bool | None = None,
    sheet_cols: int = 6,
) -> dict[str, Any]:
    """Empacota o lote e devolve os caminhos do que foi gerado.

    ``make_sheet=None`` (padrão) monta a folha de contato quando o lote tem 4 ou
    mais imagens prontas — é barato e é o jeito de conferir 30 de uma vez.

    Retorna um dicionário com ``zip``, ``report``, ``manifest``,
    ``contact_sheet``, ``files``, ``count``, ``total_cost_usd``,
    ``drift_pixels`` e ``verified`` (``True`` só quando TODAS as imagens
    prontas foram verificadas e nenhuma acusou drift).
    """
    pasta = Path(out_dir).expanduser()
    pasta.mkdir(parents=True, exist_ok=True)

    if not manifest.output_dir:
        manifest.output_dir = str(pasta)

    finais = _outputs(manifest)
    if make_sheet is None:
        make_sheet = len(finais) >= 4

    resultado: dict[str, Any] = {
        "out_dir": pasta,
        "files": finais,
        "count": len(finais),
        "zip": None,
        "report": None,
        "contact_sheet": None,
        "manifest": None,
        "total_cost_usd": round(float(manifest.total_cost_usd or 0.0)
                                or sum(float(r.cost_usd or 0.0) for r in manifest.results), 4),
        "drift_pixels": sum(int(r.drift_pixels or 0) for r in manifest.results),
        "verified": None,
        "warnings": [],
    }

    prontas = [r for r in manifest.results if r.ok]
    if prontas and all(r.untouched_pixels_verified is True and not r.drift_pixels for r in prontas):
        resultado["verified"] = True
    elif any(r.drift_pixels for r in manifest.results):
        resultado["verified"] = False

    # 1) manifesto — sempre, é o registro do lote
    try:
        resultado["manifest"] = manifest.write(pasta / MANIFEST_NAME)
    except Exception as exc:  # noqa: BLE001 - lote pronto não morre por causa do anexo
        resultado["warnings"].append(f"não consegui gravar o manifesto: {exc}")

    # 2) folha de contato antes do relatório, para poder linká-la nele
    if make_sheet and finais:
        try:
            resultado["contact_sheet"] = make_contact_sheet(finais, pasta / SHEET_NAME,
                                                            cols=sheet_cols)
        except Exception as exc:  # noqa: BLE001
            resultado["warnings"].append(f"não consegui montar a folha de contato: {exc}")

    # 3) relatório
    if make_report:
        try:
            html_txt = build_report_html(
                manifest, base_dir=pasta,
                extras={"contact_sheet": resultado["contact_sheet"]} if resultado["contact_sheet"] else None,
            )
            alvo = pasta / REPORT_NAME
            alvo.write_text(html_txt, encoding="utf-8")
            resultado["report"] = alvo
        except Exception as exc:  # noqa: BLE001
            resultado["warnings"].append(f"não consegui gravar o relatório: {exc}")

    # 4) ZIP por último: leva tudo que foi gerado acima
    if make_zip:
        alvo = pasta / f"{_slug(manifest.job)}.zip"
        avulsos: list[tuple[Path, str]] = []
        for chave, nome in (("manifest", MANIFEST_NAME), ("report", REPORT_NAME),
                            ("contact_sheet", SHEET_NAME)):
            caminho = resultado.get(chave)
            if caminho:
                avulsos.append((Path(caminho), nome))
        try:
            resultado["zip"] = _write_zip(alvo, _zip_names(finais), avulsos)
            resultado["zip_bytes"] = _safe_size(alvo)
        except Exception as exc:  # noqa: BLE001
            resultado["warnings"].append(f"não consegui gravar o ZIP: {exc}")

    return resultado


# --------------------------------------------------------------------------- #
# Teste de fumaça
# --------------------------------------------------------------------------- #
def _smoke_test() -> int:  # pragma: no cover - roda na mão
    """Monta um lote falso em pasta temporária e empacota."""
    import tempfile

    from .models import Box, ImageResult, JobManifest

    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        entrada, saida = raiz / "in", raiz / "out"
        entrada.mkdir(); saida.mkdir()
        resultados = []
        for i in range(3):
            a = Image.new("RGB", (360, 640), (30 + i * 40, 60, 120))
            ImageDraw.Draw(a).rectangle((40, 500, 320, 560), fill=(255, 255, 255))
            pa = entrada / f"criativo-{i}.png"
            a.save(pa)
            b = a.copy()
            ImageDraw.Draw(b).rectangle((40, 500, 320, 560), fill=(255, 220, 0))
            pb = saida / f"criativo-{i}.png"
            b.save(pb)
            resultados.append(ImageResult(
                source=pa, output=pb, ok=True,
                operations=["replace_text: 'GARANTA O SEU' -> 'ULTIMAS VAGAS'"],
                engine_used="deterministic", changed_boxes=[Box(40, 500, 280, 60)],
                untouched_pixels_verified=True, drift_pixels=0, duration_s=0.31,
            ))
        resultados.append(ImageResult(source=entrada / "quebrada.png", ok=False,
                                      error="não achei o bloco de texto pedido"))
        m = JobManifest(job="Teste de Fumaça", input_dir=str(entrada), output_dir=str(saida),
                        started_at=datetime.now().isoformat(timespec="seconds"),
                        finished_at=datetime.now().isoformat(timespec="seconds"),
                        results=resultados, total_cost_usd=0.0)
        out = package(m, saida)
        print("zip:", out["zip"], _fmt_bytes(_safe_size(Path(out["zip"]))))
        print("relatorio:", out["report"], _fmt_bytes(_safe_size(Path(out["report"]))))
        print("contato:", out["contact_sheet"])
        print("verificado:", out["verified"])
        assert out["zip"] and Path(out["zip"]).exists()
        assert out["report"] and "0 pixels alterados" in Path(out["report"]).read_text("utf-8")
        with zipfile.ZipFile(out["zip"]) as z:
            print("conteúdo do zip:", z.namelist())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_smoke_test())
