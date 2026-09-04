"""Interface web local do S7 Editor.

Uma página só, servida em 127.0.0.1: o usuário arrasta as 30 imagens, escolhe a
ação, acompanha o andamento e baixa o ZIP. Nada de CDN — o HTML/CSS/JS vive em
``s7editor/static`` e é servido por :class:`StaticFiles`, então a interface roda
sem internet (assim como a trilha determinística).

Por que threads e não ``async``
-------------------------------
O pipeline é síncrono e pesado (PIL, numpy, cv2). Cada lote roda numa thread
própria, com um semáforo de 1 para não competir por CPU entre lotes; o event
loop do uvicorn continua livre para responder ``/api/job/{id}``. Os endpoints
que bloqueiam são declarados como ``def`` (não ``async def``) — o FastAPI já os
joga para o threadpool sozinho.

Segurança
---------
Servimos apenas o que está DENTRO de ``settings.inbox`` (uploads) e
``settings.outbox`` (resultados). Todo nome vindo do navegador passa por
:func:`_safe_name` + :func:`_safe_join`, que resolvem o caminho e recusam
qualquer coisa que escape da pasta base ("../", caminho absoluto, symlink).
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # pragma: no cover - o cli.py depende desta mensagem
    from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
    from fastapi.staticfiles import StaticFiles
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "a interface web precisa do FastAPI e do uvicorn. "
        "Instale com:  pip install fastapi uvicorn python-multipart"
    ) from _exc

from .config import Settings, load_settings
from .imageio_util import SUPPORTED_EXT, list_images
from .models import AspectSpec, JobManifest, TextRole

__all__ = [
    "create_app",
    "run_server",
    "STATIC_DIR",
    "MAX_FILES",
    "ACTIONS",
    "JobRecord",
    "JobStore",
]

log = logging.getLogger("s7editor.webui")

STATIC_DIR = Path(__file__).resolve().parent / "static"

# --------------------------------------------------------------------------- #
# Limites (todos ajustáveis por variável de ambiente)
# --------------------------------------------------------------------------- #
def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


MAX_FILES: int = _env_int("S7_WEB_MAX_FILES", 200)
MAX_FILE_MB: int = _env_int("S7_WEB_MAX_FILE_MB", 40)
MAX_TOTAL_MB: int = _env_int("S7_WEB_MAX_TOTAL_MB", 600)
MAX_JOBS_KEPT: int = _env_int("S7_WEB_MAX_JOBS", 60)

_CHUNK = 1 << 20  # 1 MiB por leitura no upload

# Nomes de ação aceitos em POST /api/job.
ACTIONS: tuple[str, ...] = ("trocar-texto", "formato", "variacoes")

# O que a rota de preview pode devolver (o resto é 404 mesmo existindo em disco).
_PREVIEW_EXT: frozenset[str] = frozenset(SUPPORTED_EXT) | {".html", ".json", ".zip"}
_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".bmp": "image/bmp", ".tif": "image/tiff",
    ".tiff": "image/tiff", ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".zip": "application/zip",
}

_ID_RE = re.compile(r"^[0-9a-f]{8,40}$")
_NAME_KEEP = re.compile(r"[^A-Za-z0-9._ -]+")


# --------------------------------------------------------------------------- #
# Helpers de caminho — a única porta de entrada de nome vindo do navegador
# --------------------------------------------------------------------------- #
def _safe_name(raw: Any) -> str:
    """Reduz um nome de arquivo a algo inofensivo, preservando a extensão.

    Tira diretórios, acentos e tudo que não seja ``[A-Za-z0-9._ -]``. Nomes que
    viram vazio ou que começam com ponto recebem um prefixo, para nunca gerar
    ``.htaccess`` e afins.
    """
    nome = Path(str(raw or "")).name.replace("\\", "/").split("/")[-1]
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    nome = _NAME_KEEP.sub("_", nome).strip(" .")
    if not nome:
        nome = "arquivo"
    return nome[:120]


def _safe_join(base: Path, *parts: str) -> Path:
    """Junta ``parts`` sob ``base`` e prova que o resultado não escapou.

    A prova é feita depois de ``resolve()`` — é isso que fecha a porta para
    ``..``, caminho absoluto e symlink apontando para fora.
    """
    raiz = Path(base).resolve()
    for p in parts:
        if not p or p in (".", "..") or "/" in p or "\\" in p or "\x00" in p:
            raise HTTPException(400, "nome de arquivo inválido.")
    alvo = raiz.joinpath(*parts).resolve()
    if alvo != raiz and not alvo.is_relative_to(raiz):
        raise HTTPException(400, "caminho fora da pasta permitida.")
    return alvo


def _check_id(value: Any, *, what: str = "identificador") -> str:
    ident = str(value or "").strip().lower()
    if not _ID_RE.match(ident):
        raise HTTPException(400, f"{what} inválido.")
    return ident


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Registro de lotes
# --------------------------------------------------------------------------- #
@dataclass
class JobRecord:
    """Estado de um lote disparado pela interface. Tudo em memória."""

    id: str
    session: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "fila"          # fila | rodando | pronto | erro
    total: int = 0
    done: int = 0
    message: str = "na fila"
    created_at: str = field(default_factory=_now_iso)
    finished_at: str = ""
    out_dir: Path | None = None
    zip_name: str = ""
    report_name: str = ""
    results: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    ok_count: int = 0
    fail_count: int = 0
    cost_usd: float = 0.0
    drift_pixels: int = 0
    verified: bool | None = None

    @property
    def percent(self) -> int:
        if self.status == "pronto":
            return 100
        if not self.total:
            return 0
        return int(min(99, round(100 * self.done / self.total)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "session": self.session,
            "action": self.action,
            "status": self.status,
            "percent": self.percent,
            "done": self.done,
            "total": self.total,
            "message": self.message,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "ok": self.ok_count,
            "failed": self.fail_count,
            "cost_usd": round(self.cost_usd, 4),
            "drift_pixels": self.drift_pixels,
            "verified": self.verified,
            "warnings": self.warnings[:20],
            "error": self.error,
            "download": f"/api/download/{self.id}" if self.zip_name else None,
            "report": (f"/api/preview/{self.id}/{self.report_name}"
                       if self.report_name else None),
            "results": self.results,
        }


class JobStore:
    """Dicionário de lotes com trava, teto de tamanho e um worker por vez."""

    def __init__(self, max_kept: int = MAX_JOBS_KEPT) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._max = max(4, int(max_kept))
        # Um lote de cada vez: 30 imagens já saturam a CPU da máquina do usuário.
        self.slot = threading.BoundedSemaphore(1)

    def add(self, job: JobRecord) -> JobRecord:
        with self._lock:
            self._jobs[job.id] = job
            if len(self._jobs) > self._max:
                antigos = sorted(self._jobs.values(), key=lambda j: j.created_at)
                for velho in antigos[: len(self._jobs) - self._max]:
                    if velho.status in ("pronto", "erro"):
                        self._jobs.pop(velho.id, None)
        return job

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kw: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for k, v in kw.items():
                setattr(job, k, v)


# --------------------------------------------------------------------------- #
# Miniaturas (cache pequeno em memória, para a grade de antes/depois)
# --------------------------------------------------------------------------- #
class _ThumbCache:
    """Cache LRU bobo de JPEGs redimensionados. Chave inclui mtime do arquivo."""

    def __init__(self, limit: int = 240) -> None:
        self._data: dict[tuple[str, float, int], bytes] = {}
        self._lock = threading.Lock()
        self._limit = limit

    def get(self, path: Path, width: int) -> bytes | None:
        from PIL import Image

        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        chave = (str(path), mtime, width)
        with self._lock:
            achou = self._data.get(chave)
        if achou is not None:
            return achou
        try:
            with Image.open(path) as im:
                im = im.convert("RGB")
                if im.width > width:
                    altura = max(1, round(im.height * width / im.width))
                    im = im.resize((width, altura), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=82, optimize=True)
                dados = buf.getvalue()
        except Exception:  # noqa: BLE001 - miniatura é enfeite; cai para o original
            log.debug("falha ao gerar miniatura de %s", path, exc_info=True)
            return None
        with self._lock:
            if len(self._data) >= self._limit:
                self._data.pop(next(iter(self._data)), None)
            self._data[chave] = dados
        return dados


# --------------------------------------------------------------------------- #
# Validação dos parâmetros de cada ação
# --------------------------------------------------------------------------- #
def _as_box(raw: Any) -> dict[str, float] | None:
    """Caixa vinda do navegador -> dict normalizado que o pipeline entende."""
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise HTTPException(400, "a caixa deve ser um objeto com x, y, w e h.")
    try:
        vals = {k: float(raw.get(k, 0)) for k in ("x", "y", "w", "h")}
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "a caixa precisa de x, y, w e h numéricos.") from exc
    if vals["w"] <= 0 or vals["h"] <= 0:
        raise HTTPException(400, "a caixa precisa ter largura e altura maiores que zero.")
    if all(0.0 <= v <= 1.001 for v in vals.values()):
        vals["norm"] = True  # type: ignore[assignment]
    return vals  # type: ignore[return-value]


def _validate(action: str, params: dict[str, Any]) -> dict[str, Any]:
    """Normaliza os parâmetros da ação ou levanta 400 com texto em português."""
    p = dict(params or {})
    if action == "trocar-texto":
        novo = str(p.get("replace") or "").strip()
        if not novo:
            raise HTTPException(400, "escreva o texto novo do CTA (campo “trocar por”).")
        achar = str(p.get("find") or "").strip() or None
        papel_raw = str(p.get("role") or "").strip().lower() or None
        papel = None
        if papel_raw and papel_raw not in ("", "auto", "qualquer"):
            try:
                papel = TextRole(papel_raw).value
            except ValueError as exc:
                validos = ", ".join(r.value for r in TextRole)
                raise HTTPException(400, f"papel desconhecido: {papel_raw!r}. Use um de: {validos}.") from exc
        caixa = _as_box(p.get("box"))
        if not (achar or papel or caixa):
            raise HTTPException(
                400,
                "diga QUAL texto trocar: informe o texto atual, escolha um papel "
                "(ex.: cta) ou desenhe a caixa na prévia.",
            )
        return {"find": achar, "replace": novo, "role": papel, "box": caixa}

    if action == "formato":
        alvo = str(p.get("target") or "").strip()
        if not alvo:
            raise HTTPException(400, "escolha o formato de saída (ex.: 16:9, 1:1, 1080x1920).")
        try:
            spec = AspectSpec.parse(alvo)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        from .reframe import MODES as REFRAME_MODES

        modo = str(p.get("mode") or "pad").strip().lower()
        if modo not in REFRAME_MODES:
            raise HTTPException(
                400, f"modo de reenquadramento inválido: {modo!r}. "
                     f"Use um de: {', '.join(REFRAME_MODES)}.")
        try:
            lado = int(p.get("long_edge") or 1440)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "o lado maior precisa ser um número inteiro.") from exc
        if not 256 <= lado <= 4096:
            raise HTTPException(400, "o lado maior deve ficar entre 256 e 4096 pixels.")
        return {"target": spec.label if not spec.width else f"{spec.width}x{spec.height}",
                "mode": modo, "long_edge": lado}

    if action == "variacoes":
        from .variations import MODES as VAR_MODES

        try:
            n = int(p.get("n") or 0)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "a quantidade de variações precisa ser um número.") from exc
        if not 1 <= n <= 200:
            raise HTTPException(400, "peça entre 1 e 200 variações.")
        modo = str(p.get("mode") or "generative").strip().lower()
        if modo not in VAR_MODES:
            raise HTTPException(
                400, f"modo de variação inválido: {modo!r}. Use um de: {', '.join(VAR_MODES)}.")
        aspecto = str(p.get("aspect") or "").strip() or None
        if aspecto:
            try:
                AspectSpec.parse(aspecto)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        return {"n": n, "mode": modo, "aspect": aspecto}

    raise HTTPException(400, f"ação desconhecida: {action!r}. Use uma de: {', '.join(ACTIONS)}.")


def _needs_key(action: str, params: dict[str, Any]) -> bool:
    """True quando a ação escolhida vai precisar da OPENAI_API_KEY."""
    if action == "variacoes":
        return str(params.get("mode")) in ("generative", "hybrid")
    if action == "formato":
        return str(params.get("mode")) in ("outpaint", "relayout")
    return False


# --------------------------------------------------------------------------- #
# Execução do lote
# --------------------------------------------------------------------------- #
def _result_entry(res: Any, job: JobRecord, upload_dir: Path, out_dir: Path) -> dict[str, Any]:
    """Uma linha da grade antes/depois, já com as URLs prontas para o front."""
    origem = Path(str(res.source)) if res.source else None
    saida = Path(str(res.output)) if res.output else None
    antes = None
    if origem is not None:
        try:
            if origem.resolve().is_relative_to(upload_dir.resolve()):
                antes = f"/api/preview/{job.session}/{origem.name}"
        except OSError:
            antes = None
    depois = None
    if saida is not None:
        try:
            if saida.resolve().is_relative_to(out_dir.resolve()):
                depois = f"/api/preview/{job.id}/{saida.name}"
        except OSError:
            depois = None
    return {
        "name": origem.name if origem else (saida.name if saida else "?"),
        "output_name": saida.name if saida else None,
        "ok": bool(res.ok),
        "skipped": bool(res.skipped),
        "before": antes,
        "after": depois,
        "engine": res.engine_used or "",
        "operations": list(res.operations or []),
        "verified": res.untouched_pixels_verified,
        "drift_pixels": int(res.drift_pixels or 0),
        "warnings": list(res.warnings or [])[:6],
        "error": res.error or "",
        "cost_usd": round(float(res.cost_usd or 0.0), 4),
        "duration_s": round(float(res.duration_s or 0.0), 2),
    }


def _run_job(job: JobRecord, store: JobStore, settings: Settings,
             paths: list[Path], upload_dir: Path) -> None:
    """Corpo da thread do lote. Nunca levanta: erro vira ``job.error``."""
    from . import deliver, pipeline

    store.update(job.id, status="fila", message="aguardando a vez na fila…")
    with store.slot:
        store.update(job.id, status="rodando", message="preparando…", done=0)
        out_dir = job.out_dir or (Path(settings.outbox) / "web" / job.id)
        out_dir.mkdir(parents=True, exist_ok=True)

        def progresso(i: int, total: int, msg: str) -> None:
            store.update(job.id, done=int(i), total=int(total) or job.total,
                         message=str(msg)[:160])

        inicio = time.time()
        manifesto: JobManifest | None = None
        try:
            acao, p = job.action, job.params
            if acao == "trocar-texto":
                manifesto = pipeline.run_replace_text_batch(
                    paths, p.get("find"), p["replace"], settings, out_dir,
                    role=p.get("role"), box=p.get("box"), progress=progresso)
            elif acao == "formato":
                manifesto = pipeline.run_reframe_batch(
                    paths, p["target"], settings, out_dir,
                    mode=p.get("mode", "pad"), progress=progresso,
                    long_edge=p.get("long_edge", 1440))
            elif acao == "variacoes":
                manifesto = pipeline.run_variations_batch(
                    paths, p["n"], settings, out_dir,
                    mode=p.get("mode", "generative"), progress=progresso,
                    aspect=p.get("aspect"))
            else:  # pragma: no cover - _validate já barrou
                raise RuntimeError(f"ação sem execução: {acao}")
        except Exception as exc:  # noqa: BLE001 - a UI precisa da mensagem, não do traceback
            log.warning("lote %s falhou: %s", job.id, exc, exc_info=settings.verbose)
            store.update(job.id, status="erro", error=str(exc) or exc.__class__.__name__,
                         message="falhou", finished_at=_now_iso())
            return

        # -- empacota (ZIP + relatório + folha de contato) ------------------ #
        store.update(job.id, message="empacotando o ZIP…")
        pacote: dict[str, Any] = {}
        avisos = list(manifesto.notes or []) if manifesto else []
        try:
            pacote = deliver.package(manifesto, out_dir, make_zip=True, make_report=True)
            avisos.extend(str(a) for a in (pacote.get("warnings") or []))
        except Exception as exc:  # noqa: BLE001
            log.warning("empacotamento do lote %s falhou: %s", job.id, exc, exc_info=True)
            avisos.append(f"não consegui montar o ZIP: {exc}")

        linhas = [_result_entry(r, job, upload_dir, out_dir) for r in (manifesto.results if manifesto else [])]
        zip_path = pacote.get("zip")
        report_path = pacote.get("report")
        store.update(
            job.id,
            status="pronto",
            done=len(linhas) or job.total,
            total=len(linhas) or job.total,
            message=f"{manifesto.ok_count} de {len(linhas)} prontas em {time.time() - inicio:.1f}s"
                    if manifesto else "concluído",
            finished_at=_now_iso(),
            results=linhas,
            warnings=avisos,
            ok_count=manifesto.ok_count if manifesto else 0,
            fail_count=manifesto.fail_count if manifesto else 0,
            cost_usd=float(pacote.get("total_cost_usd") or 0.0),
            drift_pixels=int(pacote.get("drift_pixels") or 0),
            verified=pacote.get("verified"),
            zip_name=Path(zip_path).name if zip_path else "",
            report_name=Path(report_path).name if report_path else "",
        )


# --------------------------------------------------------------------------- #
# Aplicação
# --------------------------------------------------------------------------- #
_FALLBACK_HTML = """<!doctype html><meta charset="utf-8">
<title>S7 Editor</title>
<body style="background:#0d0f13;color:#e8ecf2;font:15px system-ui;padding:40px">
<h1>S7 Editor</h1>
<p>Os arquivos da interface (<code>s7editor/static/index.html</code>) não foram
encontrados. Reinstale o pacote ou use a linha de comando:
<code>s7editor --help</code>.</p>"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Monta a aplicação FastAPI da interface local.

    ``settings`` guarda inbox/outbox — as duas únicas pastas que o servidor
    aceita ler ou escrever.
    """
    settings = (settings or load_settings()).ensure_dirs()
    upload_root = Path(settings.inbox).resolve() / "web"
    output_root = Path(settings.outbox).resolve() / "web"
    upload_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    store = JobStore()
    thumbs = _ThumbCache()

    app = FastAPI(title="S7 Editor", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.jobs = store

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # -- erros em português, sempre JSON ---------------------------------- #
    @app.exception_handler(HTTPException)
    async def _http_erro(_req: Request, exc: HTTPException) -> JSONResponse:
        detalhe = exc.detail if isinstance(exc.detail, str) else "requisição inválida."
        return JSONResponse({"erro": detalhe}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _erro_geral(_req: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        log.exception("erro inesperado na interface web")
        return JSONResponse(
            {"erro": f"erro inesperado no servidor: {exc}. Veja o terminal para detalhes."},
            status_code=500)

    # ------------------------------------------------------------------ #
    # Página
    # ------------------------------------------------------------------ #
    def _session_dir(sid: str, *, create: bool = False) -> Path:
        pasta = _safe_join(upload_root, sid)
        if create:
            pasta.mkdir(parents=True, exist_ok=True)
        elif not pasta.is_dir():
            raise HTTPException(404, "sessão não encontrada — envie as imagens de novo.")
        return pasta

    def _boot() -> dict[str, Any]:
        from .reframe import MODES as REFRAME_MODES
        from .variations import MODES as VAR_MODES

        return {
            "has_key": bool(settings.openai_api_key),
            "key_source": settings.key_source,
            "image_model": settings.image_model,
            "quality": settings.quality,
            "inbox": str(settings.inbox),
            "outbox": str(settings.outbox),
            "max_files": MAX_FILES,
            "max_file_mb": MAX_FILE_MB,
            "max_total_mb": MAX_TOTAL_MB,
            "extensions": list(SUPPORTED_EXT),
            "reframe_modes": list(REFRAME_MODES),
            "variation_modes": list(VAR_MODES),
            "roles": [r.value for r in TextRole],
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        """A página. A configuração vai injetada para evitar uma rota extra."""
        arquivo = STATIC_DIR / "index.html"
        if not arquivo.is_file():
            return HTMLResponse(_FALLBACK_HTML, status_code=200)
        html = arquivo.read_text(encoding="utf-8")
        boot = json.dumps(_boot(), ensure_ascii=False).replace("</", "<\\/")
        html = html.replace("<!--S7_BOOT-->", f"<script>window.S7_BOOT={boot};</script>")
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return Response(status_code=204)

    # ------------------------------------------------------------------ #
    # Upload
    # ------------------------------------------------------------------ #
    @app.post("/api/upload")
    async def api_upload(files: list[UploadFile] = File(default=[]),
                         session: str = Form(default="")) -> JSONResponse:
        """Recebe as imagens arrastadas e guarda em ``inbox/web/<sessão>``."""
        if not files:
            raise HTTPException(400, "nenhum arquivo veio no envio. Arraste as imagens para a área pontilhada.")
        sid = _check_id(session, what="sessão") if session else _new_id()
        pasta = _session_dir(sid, create=True)

        ja_tem = len(list_images(pasta))
        if ja_tem + len(files) > MAX_FILES:
            raise HTTPException(
                400, f"limite de {MAX_FILES} imagens por lote (a sessão já tem {ja_tem}). "
                     "Divida em lotes menores.")

        limite_arquivo = MAX_FILE_MB * 1024 * 1024
        limite_total = MAX_TOTAL_MB * 1024 * 1024
        try:
            total_bytes = sum(f.stat().st_size for f in pasta.iterdir() if f.is_file())
        except OSError:
            total_bytes = 0
        aceitos: list[dict[str, Any]] = []
        avisos: list[str] = []

        for up in files:
            nome = _safe_name(up.filename)
            if Path(nome).suffix.lower() not in SUPPORTED_EXT:
                avisos.append(f"{nome}: extensão não suportada (use {', '.join(SUPPORTED_EXT)}).")
                continue
            destino = _safe_join(pasta, nome)
            if destino.exists():  # não sobrescreve silenciosamente
                base, ext = destino.stem, destino.suffix
                destino = _safe_join(pasta, f"{base}-{_new_id()[:6]}{ext}")
            escrito = 0
            estourou = False
            try:
                with destino.open("wb") as saida:
                    while True:
                        pedaco = await up.read(_CHUNK)
                        if not pedaco:
                            break
                        escrito += len(pedaco)
                        if escrito > limite_arquivo or total_bytes + escrito > limite_total:
                            estourou = True
                            break
                        saida.write(pedaco)
            except OSError as exc:
                destino.unlink(missing_ok=True)
                avisos.append(f"{nome}: não consegui gravar ({exc}).")
                continue
            finally:
                await up.close()

            if estourou:
                destino.unlink(missing_ok=True)
                avisos.append(
                    f"{nome}: passou do limite ({MAX_FILE_MB} MB por arquivo, "
                    f"{MAX_TOTAL_MB} MB no total).")
                continue

            info = _probe(destino)
            if info is None:
                destino.unlink(missing_ok=True)
                avisos.append(f"{nome}: não parece uma imagem válida.")
                continue
            total_bytes += escrito
            aceitos.append({
                "name": destino.name,
                "size": escrito,
                "width": info[0],
                "height": info[1],
                "preview": f"/api/preview/{sid}/{destino.name}?w=420",
            })

        if not aceitos and avisos:
            raise HTTPException(400, "nenhuma imagem foi aceita. " + " ".join(avisos[:4]))

        return JSONResponse({
            "session": sid,
            "count": len(list_images(pasta)),
            "files": aceitos,
            "warnings": avisos,
        })

    # ------------------------------------------------------------------ #
    # Inspeção
    # ------------------------------------------------------------------ #
    @app.post("/api/inspect")
    def api_inspect(payload: dict[str, Any] | None = Body(default=None)) -> JSONResponse:
        """Analisa as primeiras imagens da sessão e devolve os blocos de texto.

        É o que alimenta o seletor de papel ("qual é o CTA?") e o desenho de
        caixa na prévia. Sem chave da OpenAI cai na análise heurística offline:
        acha ONDE está o texto, mas não O QUE está escrito.
        """
        dados = payload or {}
        sid = _check_id(dados.get("session"), what="sessão")
        pasta = _session_dir(sid)
        arquivos = list_images(pasta)
        if not arquivos:
            raise HTTPException(400, "a sessão está sem imagens. Envie os criativos primeiro.")
        try:
            limite = int(dados.get("limit") or 6)
        except (TypeError, ValueError):
            limite = 6
        limite = max(1, min(limite, 12))
        alvo = arquivos[:limite]

        from .vision import analyze_batch

        analises = analyze_batch(alvo, settings, max_workers=settings.max_concurrency)
        saida: list[dict[str, Any]] = []
        for caminho, an in zip(alvo, analises):
            blocos = []
            for bloco in an.text_blocks:
                cor = bloco.style.color if bloco.style else (255, 255, 255)
                blocos.append({
                    "role": bloco.role.value if hasattr(bloco.role, "value") else str(bloco.role),
                    "text": bloco.text,
                    "box": bloco.box.to_dict(),
                    "box_norm": bloco.box.to_norm(an.width or 1, an.height or 1),
                    "color": "#%02x%02x%02x" % tuple(int(c) for c in cor),
                    "size_px": int(bloco.style.size_px) if bloco.style else 0,
                    "on_solid_background": bool(bloco.on_solid_background),
                    "confidence": round(float(bloco.confidence or 0.0), 2),
                })
            saida.append({
                "name": caminho.name,
                "preview": f"/api/preview/{sid}/{caminho.name}?w=520",
                "width": an.width,
                "height": an.height,
                "background_kind": an.background_kind.value,
                "layout": an.layout_archetype,
                "palette": ["#%02x%02x%02x" % tuple(int(c) for c in p) for p in an.palette[:6]],
                "source": an.source,
                "notes": an.notes,
                "blocks": blocos,
            })
        return JSONResponse({
            "session": sid,
            "analyzed": len(saida),
            "total": len(arquivos),
            "offline": not bool(settings.openai_api_key),
            "images": saida,
        })

    # ------------------------------------------------------------------ #
    # Lote
    # ------------------------------------------------------------------ #
    @app.post("/api/job")
    def api_job(payload: dict[str, Any] | None = Body(default=None)) -> JSONResponse:
        """Dispara o lote numa thread e devolve o ``job_id`` na hora."""
        dados = payload or {}
        sid = _check_id(dados.get("session"), what="sessão")
        pasta = _session_dir(sid)
        arquivos = list_images(pasta)
        if not arquivos:
            raise HTTPException(400, "a sessão está sem imagens. Envie os criativos primeiro.")

        acao = str(dados.get("action") or "").strip().lower()
        if acao not in ACTIONS:
            raise HTTPException(400, f"ação desconhecida: {acao!r}. Use uma de: {', '.join(ACTIONS)}.")
        params = _validate(acao, dados.get("params") or {})

        if _needs_key(acao, params) and not settings.openai_api_key:
            raise HTTPException(
                400,
                "essa opção usa IA e não achei a OPENAI_API_KEY. Configure a chave "
                "(arquivo .env na raiz do projeto ou variável de ambiente) ou escolha "
                "um modo offline: “pad”/“crop” no formato, “template” nas variações.")

        job = JobRecord(id=_new_id(), session=sid, action=acao, params=params,
                        total=len(arquivos))
        job.out_dir = _safe_join(output_root, job.id)
        store.add(job)
        thread = threading.Thread(
            target=_run_job, args=(job, store, settings, arquivos, pasta),
            name=f"s7-job-{job.id}", daemon=True)
        thread.start()
        return JSONResponse({"job_id": job.id, "status": job.status, "total": job.total},
                            status_code=202)

    @app.get("/api/job/{job_id}")
    def api_job_status(job_id: str) -> JSONResponse:
        """Status + progresso do lote (o front faz polling a cada 700 ms)."""
        job = store.get(_check_id(job_id, what="lote"))
        if job is None:
            raise HTTPException(404, "lote não encontrado (o servidor pode ter sido reiniciado).")
        return JSONResponse(job.to_dict())

    # ------------------------------------------------------------------ #
    # Entrega
    # ------------------------------------------------------------------ #
    @app.get("/api/download/{job_id}")
    def api_download(job_id: str) -> FileResponse:
        """O ZIP com as imagens prontas, o manifesto e o relatório."""
        jid = _check_id(job_id, what="lote")
        job = store.get(jid)
        if job is None:
            raise HTTPException(404, "lote não encontrado (o servidor pode ter sido reiniciado).")
        if job.status != "pronto" or not job.zip_name:
            raise HTTPException(409, "o ZIP ainda não está pronto. Espere o lote terminar.")
        alvo = _safe_join(output_root, jid, job.zip_name)
        if not alvo.is_file():
            raise HTTPException(404, "o ZIP não está mais no disco. Rode o lote de novo.")
        return FileResponse(alvo, media_type="application/zip", filename=alvo.name)

    @app.get("/api/preview/{ident}/{arquivo}")
    def api_preview(ident: str, arquivo: str, w: int = 0) -> Response:
        """Serve uma imagem da sessão (antes) ou do lote (depois).

        ``?w=420`` devolve um JPEG reduzido — a grade de 30 antes/depois abre
        instantânea sem carregar 60 PNGs de 1080×1920.
        """
        ident = _check_id(ident, what="identificador")
        # O nome cru já é seguro: _safe_join recusa separador, "..", nulo e
        # qualquer coisa que escape da raiz. A versão saneada entra só como
        # segunda tentativa, para nomes com acento gravados por nós.
        nomes = [str(arquivo or "")]
        limpo = _safe_name(arquivo)
        if limpo != nomes[0]:
            nomes.append(limpo)
        if Path(nomes[0]).suffix.lower() not in _PREVIEW_EXT:
            raise HTTPException(404, "arquivo não disponível para visualização.")

        alvo: Path | None = None
        for raiz in (output_root, upload_root):
            for nome in nomes:
                candidato = _safe_join(raiz, ident, nome)
                if candidato.is_file():
                    alvo = candidato
                    break
            if alvo is not None:
                break
        if alvo is None:
            raise HTTPException(404, "arquivo não encontrado.")

        mime = _MIME.get(alvo.suffix.lower(), "application/octet-stream")
        if w and alvo.suffix.lower() in SUPPORTED_EXT:
            largura = max(64, min(int(w), 2048))
            dados = thumbs.get(alvo, largura)
            if dados is not None:
                return Response(dados, media_type="image/jpeg",
                                headers={"Cache-Control": "max-age=60"})
        return FileResponse(alvo, media_type=mime,
                            headers={"Cache-Control": "max-age=60"})

    return app


def _probe(path: Path) -> tuple[int, int] | None:
    """Confirma que o arquivo é imagem e devolve (largura, altura)."""
    from PIL import Image

    try:
        with Image.open(path) as im:
            tamanho = im.size
            im.verify()
        return (int(tamanho[0]), int(tamanho[1]))
    except Exception:  # noqa: BLE001 - arquivo do usuário; qualquer falha = rejeitar
        return None


# --------------------------------------------------------------------------- #
# Servidor
# --------------------------------------------------------------------------- #
def run_server(host: str = "127.0.0.1", port: int = 8770,
               settings: Settings | None = None) -> None:
    """Sobe o uvicorn com a interface. Bloqueia até o Ctrl+C."""
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "a interface web precisa do uvicorn. Instale com:  pip install uvicorn"
        ) from exc

    settings = settings or load_settings()
    app = create_app(settings)
    if host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("servindo em %s — a interface não tem autenticação; "
                    "só exponha em rede confiável.", host)
    uvicorn.run(app, host=host, port=int(port),
                log_level="info" if settings.verbose else "warning",
                access_log=bool(settings.verbose))


# --------------------------------------------------------------------------- #
# Teste de fumaça
# --------------------------------------------------------------------------- #
def _smoke_test() -> int:  # pragma: no cover - roda na mão
    """Exercita as rotas com o TestClient, sem subir servidor de verdade."""
    import tempfile

    from fastapi.testclient import TestClient
    from PIL import Image, ImageDraw

    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        cfg = load_settings(root=raiz, inbox=raiz / "inbox", outbox=raiz / "outbox",
                            cache_dir=raiz / ".cache", fonts_dir=raiz / "fonts")
        cliente = TestClient(create_app(cfg))

        assert cliente.get("/").status_code == 200, "página não abriu"

        buf = io.BytesIO()
        img = Image.new("RGB", (360, 640), (18, 22, 30))
        ImageDraw.Draw(img).rectangle((60, 480, 300, 540), fill=(240, 70, 40))
        img.save(buf, "PNG")

        r = cliente.post("/api/upload", files=[("files", ("teste.png", buf.getvalue(), "image/png"))])
        assert r.status_code == 200, r.text
        sid = r.json()["session"]
        print(f"  upload ok -> sessão {sid}")

        mau = cliente.get(f"/api/preview/{sid}/..%2F..%2Fetc%2Fpasswd")
        assert mau.status_code == 404, f"path traversal não barrado: {mau.status_code}"
        print("  path traversal barrado")

        assert cliente.get(f"/api/preview/{sid}/teste.png?w=200").status_code == 200

        r = cliente.post("/api/job", json={"session": sid, "action": "formato",
                                           "params": {"target": "16:9", "mode": "pad"}})
        assert r.status_code == 202, r.text
        jid = r.json()["job_id"]
        for _ in range(300):
            estado = cliente.get(f"/api/job/{jid}").json()
            if estado["status"] in ("pronto", "erro"):
                break
            time.sleep(0.1)
        print(f"  lote {jid}: {estado['status']} — {estado['message']}")
        if estado["status"] != "pronto":
            print(f"  ERRO: {estado['error']}")
            return 1
        z = cliente.get(f"/api/download/{jid}")
        assert z.status_code == 200 and z.content[:2] == b"PK", "ZIP inválido"
        print(f"  ZIP ok ({len(z.content)} bytes)")
    print("webui: OK")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_smoke_test())
