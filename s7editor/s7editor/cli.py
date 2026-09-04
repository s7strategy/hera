"""Interface de linha de comando do S7 Editor.

    s7edit init                    prepara as pastas e as receitas de exemplo
    s7edit doctor                  diz exatamente o que está faltando
    s7edit inspect <pasta>         mostra o que existe em cada criativo
    s7edit run <receita>           executa uma receita
    s7edit reframe <pasta> --to 16:9
    s7edit vary <pasta> -n 30
    s7edit trocar-texto <pasta> --de "GARANTA O SEU" --para "ULTIMAS VAGAS"
    s7edit ui                      sobe a interface web

Regras que valem para todos os comandos:

* **Nada de traceback na cara do usuário.** Erro de uso vira mensagem em
  português com o caminho da correção; código de saída ``2``. Erro de execução
  vira mensagem + código ``1``. Só com ``--verbose`` o traceback aparece.
* **``--dry-run`` nunca escreve arquivo.** O plano é impresso e o comando
  termina — a checagem fica aqui, na CLI, para não depender de cada motor
  respeitar o flag.
* A barra de progresso vai para o **stderr**; ``stdout`` fica limpo para
  ``--json`` e para pipes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Sequence

from .config import load_settings, mask_key
from .models import AspectSpec, JobManifest

__all__ = ["main", "build_parser"]

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

PROG = "s7edit"


# --------------------------------------------------------------------------- #
# Saída no terminal
# --------------------------------------------------------------------------- #
def _no_color() -> bool:
    return bool(os.environ.get("NO_COLOR")) or not sys.stderr.isatty()


def _c(text: str, code: str) -> str:
    return text if _no_color() else f"\033[{code}m{text}\033[0m"


def bold(t: str) -> str:
    return _c(t, "1")


def green(t: str) -> str:
    return _c(t, "32")


def red(t: str) -> str:
    return _c(t, "31")


def yellow(t: str) -> str:
    return _c(t, "33")


def dim(t: str) -> str:
    return _c(t, "2")


def _unicode_ok() -> bool:
    """Alguns terminais Windows ainda são cp1252 — não vamos quebrar neles."""
    enc = getattr(sys.stderr, "encoding", None) or "ascii"
    try:
        "█░✓✗→".encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _sym(ok: str, nok: str) -> tuple[str, str]:
    return (ok, nok) if _unicode_ok() else ("ok", "x")


# --------------------------------------------------------------------------- #
# Barra de progresso (sem dependência nova)
# --------------------------------------------------------------------------- #
class Progress:
    """Barra simples no stderr, compatível com o callback ``(i, total, msg)``.

    Convenção do projeto: ``i`` é 1-based e a chamada acontece ANTES de
    processar o item, então a barra mostra o que está em andamento.
    """

    def __init__(self, label: str = "", *, total: int = 0, enabled: bool = True) -> None:
        self.label = label
        self.total = int(total or 0)
        self.enabled = bool(enabled) and not os.environ.get("S7EDITOR_NO_PROGRESS")
        self.tty = sys.stderr.isatty()
        self.cheio, self.vazio = ("█", "░") if _unicode_ok() else ("#", ".")
        self._last = 0.0
        self._last_i = -1
        self._open = False

    def __call__(self, i: int, total: int, msg: str = "") -> None:
        if not self.enabled:
            return
        total = int(total or self.total or 0)
        self.total = total or self.total
        agora = time.monotonic()
        # Sem tty (log, CI) escrevemos uma linha por item, no máximo 1x/segundo.
        if not self.tty:
            if i == self._last_i or (agora - self._last < 1.0 and i not in (1, total)):
                return
            self._last, self._last_i = agora, i
            err(f"  [{i}/{total}] {msg}")
            return
        if agora - self._last < 0.05 and i not in (1, total):
            return
        self._last = agora
        largura = max(20, min(shutil.get_terminal_size((90, 20)).columns, 110))
        frac = (i / total) if total else 0.0
        barra_w = max(10, min(28, largura // 4))
        cheias = int(round(barra_w * min(1.0, frac)))
        barra = self.cheio * cheias + self.vazio * (barra_w - cheias)
        cabeca = f"{self.label} " if self.label else ""
        prefixo = f"\r{cabeca}[{barra}] {i}/{total} {int(frac * 100):3d}%  "
        espaco = max(0, largura - len(prefixo) - 2)
        texto = msg if len(msg) <= espaco else ("…" + msg[-(espaco - 1):] if espaco > 2 else "")
        sys.stderr.write(prefixo + texto + " " * max(0, espaco - len(texto)))
        sys.stderr.flush()
        self._open = True

    def close(self, msg: str = "") -> None:
        if self._open and self.tty:
            sys.stderr.write("\r" + " " * max(20, min(shutil.get_terminal_size((90, 20)).columns, 110)) + "\r")
            sys.stderr.flush()
        self._open = False
        if msg:
            err(msg)


# --------------------------------------------------------------------------- #
# Erros de uso
# --------------------------------------------------------------------------- #
class UsageError(Exception):
    """Erro do usuário (argumento inválido, pasta vazia) — sai com código 2."""


class RunError(Exception):
    """Falha durante a execução — sai com código 1."""


_ARG_MSGS = [
    (r"^unrecognized arguments: (.*)$", "opção desconhecida: {0}"),
    (r"^the following arguments are required: (.*)$", "faltou informar: {0}"),
    (r"^argument (.+): expected one argument$", "a opção {0} precisa de um valor"),
    (r"^argument (.+): invalid choice: (.+) \(choose from (.+)\)$",
     "valor inválido para {0}: {1}. Use um destes: {2}"),
    (r"^argument (.+): invalid (\w+) value: (.+)$", "valor inválido para {0}: {2}"),
    (r"^invalid choice: (.+) \(choose from (.+)\)$", "comando inválido: {0}. Use um destes: {1}"),
]


def _traduz_argparse(msg: str) -> str:
    for padrao, molde in _ARG_MSGS:
        m = re.match(padrao, msg)
        if m:
            return molde.format(*m.groups())
    return msg


class _Parser(argparse.ArgumentParser):
    """ArgumentParser que fala português e sai com o código certo."""

    def error(self, message: str) -> Any:  # noqa: D102
        self.print_usage(sys.stderr)
        err(f"\n{red('erro de uso')}: {_traduz_argparse(message)}")
        err(f"Rode '{self.prog} --help' para ver as opções.")
        raise SystemExit(EXIT_USAGE)


# --------------------------------------------------------------------------- #
# Helpers de arquivo/pasta
# --------------------------------------------------------------------------- #
def _slug(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text or "lote")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "lote"


def _folder_or_die(raw: Any, settings: Any) -> Path:
    p = Path(str(raw)).expanduser()
    if not p.is_absolute():
        for base in (Path.cwd(), Path(settings.root)):
            if (base / p).exists():
                p = base / p
                break
    if not p.exists():
        raise UsageError(
            f"Não encontrei a pasta {p}.\n"
            f"  Coloque os criativos em uma pasta (ex.: {Path(settings.inbox) / 'minha-campanha'}) "
            "e passe o caminho dela.\n"
            f"  Se ainda não montou a estrutura, rode: {PROG} init")
    if not p.is_dir():
        raise UsageError(f"{p} é um arquivo, não uma pasta. Passe a pasta que contém os criativos.")
    return p


def _images_or_die(folder: Path, *, recursive: bool = False,
                   limite: int | None = None) -> list[Path]:
    from .imageio_util import SUPPORTED_EXT, list_images

    paths = list_images(folder, recursive=recursive)
    if not paths:
        extra = "" if recursive else "\n  Se as imagens estão em subpastas, use --recursive."
        raise UsageError(
            f"A pasta {folder} não tem nenhuma imagem que eu saiba ler.\n"
            f"  Formatos aceitos: {', '.join(SUPPORTED_EXT)}.{extra}")
    if limite and limite > 0 and len(paths) > limite:
        print(dim(f"--limite {limite}: usando {limite} de {len(paths)} imagem(ns) "
                  f"(prova antes de rodar o lote inteiro)."))
        paths = paths[:limite]
    return paths


def _guard_out_dir(path: Path, force: bool) -> Path:
    """Não sobrescreve trabalho anterior sem o usuário pedir."""
    if path.exists() and any(path.iterdir()) and not force:
        raise UsageError(
            f"A pasta de saída {path} já tem arquivos.\n"
            "  Use --force para sobrescrever, ou --out <outra-pasta> para separar as versões.")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _default_out(settings: Any, prefixo: str, origem: Path, out_override: Any = None) -> Path:
    if out_override:
        p = Path(str(out_override)).expanduser()
        return p if p.is_absolute() else (Path.cwd() / p)
    return Path(settings.outbox) / f"{prefixo}-{_slug(origem.name)}"


def _fmt_bytes(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024 or unit == "GB":
            return f"{f:.0f} {unit}" if unit == "B" else f"{f:.1f} {unit}".replace(".", ",")
        f /= 1024
    return f"{f:.1f} GB"


def _fmt_usd(value: float) -> str:
    """Dólar com vírgula decimal (o usuário é brasileiro)."""
    v = float(value or 0.0)
    if v <= 0:
        return "US$ 0,00"
    txt = f"{v:,.4f}" if v < 0.01 else f"{v:,.2f}"
    return "US$ " + txt.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


# --------------------------------------------------------------------------- #
# Encerramento padrão de um lote
# --------------------------------------------------------------------------- #
def _finish(manifest: JobManifest, out_dir: Path, *, deliver: dict[str, Any] | None = None) -> int:
    """Empacota, imprime o destaque com ZIP + relatório e devolve o código de saída."""
    from .deliver import package

    deliver = deliver or {}
    pacote = package(
        manifest, out_dir,
        make_zip=bool(deliver.get("zip", True)),
        make_report=bool(deliver.get("report", True)),
        make_sheet=deliver.get("contact_sheet"),
    )

    total = len(manifest.results)
    ok = manifest.ok_count
    falhas = manifest.fail_count
    # Uma imagem que passou por todas as operações sem nenhuma se aplicar saiu
    # apenas copiada. Isso conta como "ok" no manifesto e NÃO é sucesso do ponto
    # de vista de quem pediu a troca — dizer "30 de 30 pronto" aí seria mentira.
    vazias = [r for r in manifest.results
              if r.ok and not r.skipped and not r.operations]
    linha = "=" * 68

    aplicadas = ok - len(vazias)
    print()
    print(linha)
    if vazias and aplicadas == 0:
        cabeca = f"  NADA FOI ALTERADO — {total} imagem(ns) saíram iguais à entrada"
        print(bold(red(cabeca)))
    elif vazias:
        cabeca = f"  PARCIAL — {aplicadas} de {total} imagem(ns) alteradas"
        print(bold(yellow(cabeca)))
    else:
        cabeca = f"  PRONTO — {ok} de {total} imagem(ns)"
        print(bold(green(cabeca)) if not falhas else bold(yellow(cabeca)))
    print()
    if pacote.get("zip"):
        tam = f"  ({_fmt_bytes(pacote.get('zip_bytes') or 0)})"
        print("  " + bold("ZIP        ") + bold(str(pacote["zip"])) + dim(tam))
    if pacote.get("report"):
        print("  " + bold("Relatório  ") + bold(str(pacote["report"])))
    if pacote.get("contact_sheet"):
        print("  " + bold("Contato    ") + str(pacote["contact_sheet"]))
    if pacote.get("manifest"):
        print("  " + dim("Manifesto  " + str(pacote["manifest"])))
    print()

    if vazias:
        motivos: dict[str, int] = {}
        for r in vazias:
            for w in r.warnings:
                chave = w.split(";")[0].split("(")[0].strip()
                motivos[chave] = motivos.get(chave, 0) + 1
        print("  " + (red if aplicadas == 0 else yellow)(
            f"{len(vazias)} imagem(ns) não receberam nenhuma alteração:"))
        for motivo, n in sorted(motivos.items(), key=lambda kv: -kv[1])[:3]:
            print("    " + dim(f"{n}x  {motivo}"))
        print("    " + dim("Dicas: confira o texto em --de, ou selecione o bloco com "
                           "--papel cta / --caixa. Rode 'inspect' para ver o que foi detectado."))
        print()

    drift = int(pacote.get("drift_pixels") or 0)
    if drift:
        print("  " + red(f"ATENÇÃO: {drift} pixel(s) mudaram fora da área editada. "
                         "Veja o relatório."))
    elif pacote.get("verified") is True:
        print("  " + green("Zero drift verificado: 0 pixels alterados fora da área editada."))
    else:
        print("  " + dim("Sem verificação de drift neste lote (operação reescreve o quadro inteiro)."))

    custo = float(pacote.get("total_cost_usd") or 0.0)
    print("  " + ("Custo estimado: " + _fmt_usd(custo) if custo
                  else dim("Custo: US$ 0,00 (trilha determinística, sem IA).")))
    if falhas:
        print("  " + yellow(f"{falhas} imagem(ns) falharam — o motivo está no relatório."))
    for w in pacote.get("warnings") or []:
        print("  " + yellow("aviso: " + w))
    print(linha)
    # Sair 0 quando nada mudou faria um script de automação achar que deu certo.
    if falhas or (vazias and aplicadas == 0):
        return EXIT_FAIL
    return EXIT_OK


def _pipeline() -> Any:
    """Import tardio: só quem roda lote paga o custo (e a mensagem é clara se faltar)."""
    try:
        from . import pipeline
    except ImportError as exc:  # pragma: no cover
        raise RunError(
            f"Não consegui carregar o motor de execução (s7editor/pipeline.py): {exc}\n"
            f"  Rode '{PROG} doctor' para ver o que está faltando.") from exc
    return pipeline


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #
_ENV_EXAMPLE = """\
# ---------------------------------------------------------------------------
# S7 Editor — copie este arquivo para ".env" e preencha a chave.
#
# A chave SÓ é necessária para as operações com IA (outpaint, variações
# generativas, leitura de texto por visão). Trocar texto, apagar texto e
# reenquadrar em pad/crop funcionam 100% offline, sem chave nenhuma.
# ---------------------------------------------------------------------------
OPENAI_API_KEY=sua_chave_aqui

# Opcionais — descomente só se quiser mudar o padrão.
# S7EDITOR_QUALITY=medium          # low | medium | high (custo do gpt-image-1)
# S7EDITOR_CONCURRENCY=4           # imagens em paralelo
# S7EDITOR_IMAGE_MODEL=gpt-image-1
# S7EDITOR_VISION_MODEL=gpt-4.1-mini
# S7EDITOR_INBOX=./inbox
# S7EDITOR_OUTBOX=./outbox
# S7EDITOR_FONTS=./fonts
"""

_LEIAME = """\
COMO USAR O S7 EDITOR
=====================

1. Jogue os criativos numa pasta aqui dentro. Exemplo:
       inbox/campanha-agosto/  (30 arquivos .png ou .jpg)

2. O atalho mais pedido — trocar o CTA de todos sem mexer em mais nada:
       s7edit trocar-texto inbox/campanha-agosto --de "GARANTA O SEU" --para "ULTIMAS VAGAS"

3. Converter o lote de 9:16 para 16:9 sem distorcer nada:
       s7edit reframe inbox/campanha-agosto --to 16:9 --mode relayout

4. Gerar 30 criativos parecidos com as referências:
       s7edit vary inbox/campanha-agosto -n 30

5. Para algo mais elaborado, edite uma receita em recipes/ e rode:
       s7edit run recipes/trocar-cta.yaml

No fim de cada lote você recebe um ZIP e um relatório HTML mostrando
ANTES x DEPOIS e a prova de que nada fora da área editada mudou.

Dúvida sobre o que está configurado? Rode:  s7edit doctor
"""


def cmd_init(args: argparse.Namespace, settings: Any) -> int:
    from .recipe import EXAMPLE_RECIPES, write_example

    force = bool(getattr(args, "force", False))
    raiz = Path(settings.root)
    criados: list[str] = []
    pulados: list[str] = []

    for d in (settings.inbox, settings.outbox, settings.fonts_dir, settings.cache_dir,
              raiz / "recipes"):
        existia = Path(d).exists()
        Path(d).mkdir(parents=True, exist_ok=True)
        (criados if not existia else pulados).append(str(d))

    def escreve(destino: Path, conteudo: str) -> None:
        if destino.exists() and not force:
            pulados.append(str(destino))
            return
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")
        criados.append(str(destino))

    escreve(raiz / ".env.example", _ENV_EXAMPLE)
    escreve(Path(settings.inbox) / "COMO-USAR.txt", _LEIAME)

    for nome in sorted(EXAMPLE_RECIPES):
        alvo = raiz / "recipes" / f"{nome}.yaml"
        if alvo.exists() and not force:
            pulados.append(str(alvo))
            continue
        write_example(nome, alvo)
        criados.append(str(alvo))

    ok, _ = _sym("✓", "ok")
    print(bold("S7 Editor — estrutura pronta.\n"))
    for c in criados:
        print(f"  {green(ok)} criado    {c}")
    for s in pulados:
        print(f"  {dim('·')} {dim('já existia ' + s)}")
    if pulados and not force:
        print(dim("\n  (use --force para sobrescrever o que já existia)"))

    print(f"""
{bold('Próximos passos')}

  1. Copie {raiz / '.env.example'} para {raiz / '.env'} e ponha a chave
     — só se for usar IA. O modo determinístico não precisa.
  2. Jogue seus criativos em {Path(settings.inbox) / 'minha-campanha'}
  3. Rode o atalho mais pedido:

     {bold(PROG + ' trocar-texto ' + str(Path(settings.inbox) / 'minha-campanha') + ' --de "GARANTA O SEU" --para "ULTIMAS VAGAS"')}

  Para conferir o ambiente:  {bold(PROG + ' doctor')}
""")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
_DEPS = [
    ("PIL", "Pillow", "obrigatória — abrir, desenhar e salvar imagem", True),
    ("numpy", "numpy", "obrigatória — toda a matemática de pixel", True),
    ("cv2", "opencv-python-headless", "inpaint, segmentação de glifo e detecção de rosto", False),
    ("yaml", "pyyaml", "ler receitas .yaml", False),
    ("openai", "openai", "operações com IA (gpt-image-1 e visão)", False),
    ("fastapi", "fastapi", "interface web (s7edit ui)", False),
    ("uvicorn", "uvicorn", "servidor da interface web", False),
]


def _versao(mod: Any) -> str:
    for attr in ("__version__", "VERSION", "version"):
        v = getattr(mod, attr, None)
        if isinstance(v, str):
            return v
    return "?"


def cmd_doctor(args: argparse.Namespace, settings: Any) -> int:
    import importlib
    import platform

    ok_s, no_s = _sym("✓", "x")
    aviso_s = "!" if not _unicode_ok() else "!"
    problemas: list[str] = []
    bloqueios: list[str] = []

    print(bold("S7 Editor — diagnóstico\n"))
    print(f"  Python {platform.python_version()} em {platform.system()} "
          f"({platform.machine()})")
    print(f"  Raiz do projeto: {settings.root}\n")

    # -- dependências ------------------------------------------------------ #
    print(bold("Dependências"))
    for nome, pacote, para_que, obrigatoria in _DEPS:
        try:
            mod = importlib.import_module(nome)
            print(f"  {green(ok_s)} {pacote:<24} {_versao(mod):<10} {dim(para_que)}")
        except ImportError:
            marca = red(no_s) if obrigatoria else yellow(aviso_s)
            print(f"  {marca} {pacote:<24} {'ausente':<10} {para_que}")
            (bloqueios if obrigatoria else problemas).append(
                f"instale {pacote}:  pip install {pacote}")

    # -- fontes ------------------------------------------------------------ #
    print("\n" + bold("Fontes"))
    try:
        from .fonts import list_available_families

        familias = list_available_families()
    except Exception as exc:  # noqa: BLE001
        familias = []
        problemas.append(f"não consegui indexar as fontes: {exc}")
    print(f"  pasta da marca: {settings.fonts_dir}"
          f"{'' if Path(settings.fonts_dir).exists() else dim('  (ainda não existe)')}")
    if familias:
        mostra = ", ".join(familias[:8])
        resto = f" (+{len(familias) - 8})" if len(familias) > 8 else ""
        print(f"  {green(ok_s)} {len(familias)} família(s) disponíveis: {mostra}{resto}")
    else:
        print(f"  {red(no_s)} nenhuma fonte encontrada — o texto redesenhado sairia errado")
        problemas.append(
            f"copie os .ttf/.otf da marca para {settings.fonts_dir} "
            "(ex.: Inter-Bold.ttf, Inter-Regular.ttf)")

    # -- OCR ----------------------------------------------------------------- #
    print("\n" + bold("OCR (ler o texto sem chave de API)"))
    from . import ocr as _ocr

    if _ocr.ocr_available():
        idiomas = _ocr.tesseract_langs()
        tem_pt = "por" in idiomas
        print("  " + green("OK") + f"  Tesseract encontrado — idiomas: "
              f"{', '.join(idiomas) if idiomas else 'desconhecidos'}")
        if not tem_pt:
            print("  " + yellow("!") + "  sem o pacote de português; acentos podem sair errados")
            print("     " + dim("Ubuntu: sudo apt install tesseract-ocr-por"))
        else:
            print("  " + dim("Dá para usar --de \"TEXTO ATUAL\" sem gastar API."))
    else:
        print("  " + yellow("!") + "  não encontrado — sem ele, o casamento por texto (--de) "
              "só funciona com chave da OpenAI")
        for linha in _ocr.OCR_INSTALL_HINT.splitlines()[1:]:
            print("     " + dim(linha.strip()))

    # -- chave da OpenAI --------------------------------------------------- #
    print("\n" + bold("Chave da OpenAI"))
    if settings.openai_api_key:
        print(f"  {green(ok_s)} encontrada: {mask_key(settings.openai_api_key)} "
              f"{dim('(origem: ' + str(settings.key_source) + ')')}")
        print(f"  modelo de imagem: {settings.image_model} · visão: {settings.vision_model} "
              f"· qualidade: {settings.quality}")
    else:
        print(f"  {yellow(aviso_s)} não encontrada — {bold('a trilha determinística continua funcionando')}")
        print(dim("     (trocar texto, apagar texto, reframe pad/crop e variações template)"))
        problemas.append(
            f"para usar IA, crie {Path(settings.root) / '.env'} com a linha "
            "OPENAI_API_KEY=sk-sua-chave")

    # -- pastas ------------------------------------------------------------ #
    print("\n" + bold("Pastas"))
    for rotulo, caminho in (("entrada", settings.inbox), ("saída", settings.outbox),
                            ("cache", settings.cache_dir), ("fontes", settings.fonts_dir)):
        p = Path(caminho)
        existe = p.exists()
        gravavel = os.access(p if existe else p.parent, os.W_OK)
        marca = green(ok_s) if existe and gravavel else yellow(aviso_s)
        estado = "ok" if existe and gravavel else ("não existe" if not existe else "sem permissão de escrita")
        print(f"  {marca} {rotulo:<8} {p}  {dim(estado)}")
        if not existe:
            problemas.append(f"rode '{PROG} init' para criar {p}")
        elif not gravavel:
            bloqueios.append(f"sem permissão de escrita em {p}")

    # -- conteúdo ---------------------------------------------------------- #
    print("\n" + bold("Conteúdo"))
    try:
        from .imageio_util import list_images

        imagens = list_images(settings.inbox, recursive=True)
    except Exception:  # noqa: BLE001
        imagens = []
    receitas = sorted((Path(settings.root) / "recipes").glob("*.y*ml")) \
        if (Path(settings.root) / "recipes").exists() else []
    print(f"  {len(imagens)} imagem(ns) em {settings.inbox} (contando subpastas)")
    print(f"  {len(receitas)} receita(s) em {Path(settings.root) / 'recipes'}")
    if not imagens:
        problemas.append(f"jogue seus criativos em {Path(settings.inbox) / 'minha-campanha'}")

    # -- veredito ---------------------------------------------------------- #
    print("\n" + bold("Veredito"))
    if bloqueios:
        print(f"  {red(no_s)} {red('O editor NÃO vai rodar até resolver:')}")
        for b in dict.fromkeys(bloqueios):
            print(f"      - {b}")
    else:
        print(f"  {green(ok_s)} {green('Trilha determinística pronta')} — trocar texto, apagar "
              "texto e reenquadrar funcionam offline, com garantia de zero drift.")
        if settings.openai_api_key:
            print(f"  {green(ok_s)} {green('Trilha com IA pronta')} — outpaint e variações "
                  "generativas disponíveis.")
        else:
            print(f"  {yellow(aviso_s)} Trilha com IA indisponível (falta a chave).")
    if problemas:
        print("\n  " + bold("O que dá para melhorar:"))
        for p_ in dict.fromkeys(problemas):
            print(f"      - {p_}")
    print()
    return EXIT_FAIL if bloqueios else EXIT_OK


# --------------------------------------------------------------------------- #
# inspect
# --------------------------------------------------------------------------- #
def _corta(texto: str, n: int) -> str:
    t = " ".join(str(texto or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def cmd_inspect(args: argparse.Namespace, settings: Any) -> int:
    from .imageio_util import load_image
    from .vision import analyze_batch, analyze_creative

    pasta = _folder_or_die(args.pasta, settings)
    paths = _images_or_die(pasta, recursive=bool(getattr(args, "recursive", False)),
                           limite=getattr(args, "limite", None))
    como_json = bool(getattr(args, "json", False))

    if settings.openai_api_key and not getattr(args, "offline", False):
        err(dim(f"analisando {len(paths)} imagem(ns) com {settings.vision_model}…"))
        analises = analyze_batch(paths, settings, max_workers=settings.max_concurrency)
    else:
        if not settings.openai_api_key:
            err(dim("sem chave da OpenAI: usando a detecção offline (caixas por pixel, "
                    "sem ler o texto)."))
        bar = Progress("analisando", total=len(paths))   # stderr: não suja o --json
        analises = []
        for i, p in enumerate(paths, 1):
            bar(i, len(paths), p.name)
            analises.append(analyze_creative(p, settings))
        bar.close()

    if como_json:
        print(json.dumps([a.to_dict() for a in analises], ensure_ascii=False, indent=2))
        return EXIT_OK

    largura_nome = min(40, max(10, max(len(p.name) for p in paths)))
    cab = f"{'#':>3}  {'arquivo':<{largura_nome}}  {'tamanho':>11}  {'fmt':<5}  {'blocos':>6}"
    print(bold(cab))
    print(dim("-" * len(cab)))
    total_blocos = 0
    notas_vistas: set[str] = set()
    for i, (p, a) in enumerate(zip(paths, analises), 1):
        try:
            fmt = (load_image(p).info.get("s7_source_format") or p.suffix.lstrip(".")).upper()
        except Exception:  # noqa: BLE001
            fmt = p.suffix.lstrip(".").upper()
        n = len(a.text_blocks)
        total_blocos += n
        tam = f"{a.width}x{a.height}"
        print(f"{i:>3}  {_corta(p.name, largura_nome):<{largura_nome}}  "
              f"{tam:>11}  {fmt:<5}  {n:>6}")
        for b in a.text_blocks:
            papel = b.role.value if hasattr(b.role, "value") else str(b.role)
            texto = _corta(b.text, 46)
            celula = f"{texto:<46}" if texto else dim(f"{'(texto não lido — só a caixa)':<46}")
            cx = f"({b.box.x},{b.box.y} {b.box.w}x{b.box.h})"
            print(f"       {dim('·')} {papel:<9} {celula} {dim(cx)}")
        if a.notes and a.notes not in notas_vistas:
            notas_vistas.add(a.notes)
            print(f"       {yellow('!')} {dim(_corta(a.notes, 96))}")

    print(dim("-" * len(cab)))
    print(f"{len(paths)} imagem(ns), {total_blocos} bloco(s) de texto. "
          f"Fonte da análise: {analises[0].source if analises else '—'}.")
    if total_blocos:
        exemplo = next((b.text for a in analises for b in a.text_blocks if b.text), None)
        if exemplo:
            print(dim(f"\nPara trocar um deles em todo o lote:\n"
                      f"  {PROG} trocar-texto {pasta} --de \"{_corta(exemplo, 30)}\" "
                      f"--para \"NOVO TEXTO\""))
    return EXIT_OK


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def cmd_run(args: argparse.Namespace, settings: Any) -> int:
    from .recipe import RecipeError, load_recipe

    try:
        receita = load_recipe(args.receita, settings)
    except RecipeError as exc:
        raise UsageError(str(exc)) from exc

    if getattr(args, "out", None):
        receita.output_dir = _default_out(settings, "", Path(receita.job), args.out)

    print(bold("Receita carregada:"))
    print("  " + receita.summary().replace("\n", "\n  "))
    print()

    if not receita.input_dir.exists():
        raise UsageError(
            f"A pasta de entrada da receita não existe: {receita.input_dir}\n"
            "  Corrija o campo 'input:' da receita ou crie a pasta.")
    paths = _images_or_die(receita.input_dir, recursive=receita.recursive,
                           limite=getattr(args, "limite", None))

    if getattr(args, "dry_run", False):
        print(yellow(f"--dry-run: nada foi escrito. {len(paths)} imagem(ns) seriam processadas:"))
        for p in paths[:20]:
            print(f"  · {p.name}")
        if len(paths) > 20:
            print(dim(f"  … e mais {len(paths) - 20}"))
        print(f"\n  Saída iria para: {bold(str(receita.output_dir))}")
        return EXIT_OK

    _guard_out_dir(Path(receita.output_dir), bool(getattr(args, "force", False)))

    bar = Progress("editando", total=len(paths))
    try:
        manifesto = _pipeline().run_recipe(receita, settings, progress=bar,
                                           force=bool(getattr(args, "force", False)))
    finally:
        bar.close()
    return _finish(manifesto, Path(receita.output_dir), deliver=receita.deliver)


# --------------------------------------------------------------------------- #
# reframe
# --------------------------------------------------------------------------- #
def cmd_reframe(args: argparse.Namespace, settings: Any) -> int:
    pasta = _folder_or_die(args.pasta, settings)
    paths = _images_or_die(pasta, recursive=bool(getattr(args, "recursive", False)),
                           limite=getattr(args, "limite", None))

    try:
        alvo = AspectSpec.parse(args.to)
    except (ValueError, TypeError) as exc:
        # AspectSpec.parse pode estourar no int() antes da mensagem dela; a nossa
        # é sempre a mesma e sempre útil, então não repassamos a original.
        raise UsageError(
            f"Não entendi o formato {args.to!r} em --to.\n"
            "  Use um destes:\n"
            "    --to 16:9         proporção (o tamanho sai da própria imagem)\n"
            "    --to 1920x1080    tamanho exato em pixels\n"
            "    --to 9:16@1080    proporção com o lado maior fixo") from exc
    if getattr(args, "long_edge", None) and not (alvo.width and alvo.height):
        w, h = alvo.resolve(int(args.long_edge))
        alvo = AspectSpec(alvo.ratio_w, alvo.ratio_h, w, h)

    modo = args.mode
    if modo == "outpaint" and not settings.openai_api_key:
        raise UsageError(
            "O modo 'outpaint' usa IA e não achei a OPENAI_API_KEY.\n"
            f"  Rode '{PROG} doctor' para ver onde colocá-la, ou use um modo offline:\n"
            "    --mode pad       fundo borrado nas laterais (sempre funciona)\n"
            "    --mode crop      corta preservando o assunto\n"
            "    --mode relayout  reposiciona os textos no novo formato")

    saida = _default_out(settings, f"reframe-{alvo.label.replace(':', 'x')}", pasta,
                         getattr(args, "out", None))
    if alvo.width and alvo.height:
        tamanho = f" ({alvo.width}x{alvo.height})"
    else:
        tamanho = " (tamanho vindo de cada imagem)"
    print(f"Reenquadrando {len(paths)} imagem(ns) para {bold(alvo.label)}{tamanho}, "
          f"modo {bold(modo)}.")

    if getattr(args, "dry_run", False):
        print(yellow(f"--dry-run: nada foi escrito. Saída iria para {saida}"))
        return EXIT_OK

    _guard_out_dir(saida, bool(getattr(args, "force", False)))
    bar = Progress("reenquadrando", total=len(paths))
    try:
        manifesto = _pipeline().run_reframe_batch(
            paths, alvo, settings, saida, mode=modo, progress=bar,
            long_edge=(int(args.long_edge) if getattr(args, "long_edge", None) else None),
            force=bool(getattr(args, "force", False)))
    finally:
        bar.close()
    return _finish(manifesto, saida, deliver={"contact_sheet": True})


# --------------------------------------------------------------------------- #
# vary
# --------------------------------------------------------------------------- #
def cmd_vary(args: argparse.Namespace, settings: Any) -> int:
    pasta = _folder_or_die(args.pasta, settings)
    paths = _images_or_die(pasta, recursive=bool(getattr(args, "recursive", False)),
                           limite=getattr(args, "limite", None))
    n = int(args.n)
    if n < 1 or n > 500:
        raise UsageError("A quantidade (-n) tem que ficar entre 1 e 500.")

    modo = args.mode
    if modo in ("generative", "hybrid") and not settings.openai_api_key:
        raise UsageError(
            f"O modo '{modo}' gera imagem nova com IA e não achei a OPENAI_API_KEY.\n"
            f"  Rode '{PROG} doctor' para ver onde colocá-la, ou use o modo offline:\n"
            "    --mode template   monta as variações a partir das suas referências, "
            "sem chamar a IA")

    saida = _default_out(settings, "variacoes", pasta, getattr(args, "out", None))
    print(f"Lendo o DNA de {len(paths)} referência(s) e gerando {bold(str(n))} variação(ões), "
          f"modo {bold(modo)}.")
    if modo in ("generative", "hybrid"):
        from .config import price_per_image

        estimado = price_per_image(settings.image_model, "1024x1536", settings.quality, n)
        print(yellow(f"  Custo estimado: até {_fmt_usd(estimado)} "
                     f"({n} imagens, qualidade {settings.quality})."))

    if getattr(args, "dry_run", False):
        print(yellow(f"--dry-run: nada foi escrito. Saída iria para {saida}"))
        return EXIT_OK

    _guard_out_dir(saida, bool(getattr(args, "force", False)))
    bar = Progress("gerando", total=n)
    try:
        manifesto = _pipeline().run_variations_batch(
            paths, n, settings, saida, mode=modo, progress=bar,
            force=bool(getattr(args, "force", False)))
    finally:
        bar.close()
    return _finish(manifesto, saida, deliver={"contact_sheet": True})


# --------------------------------------------------------------------------- #
# trocar-texto
# --------------------------------------------------------------------------- #
def _parse_caixa(raw: str | None) -> Any:
    """Aceita 'x,y,w,h' em pixels ou em fração (0–1). Devolve dict para Box.from_any."""
    if not raw:
        return None
    partes = [p.strip() for p in str(raw).replace(";", ",").split(",") if p.strip()]
    if len(partes) != 4:
        raise UsageError("A caixa precisa de 4 números: --caixa x,y,w,h "
                         "(pixels ou fração de 0 a 1, ex.: 0.1,0.82,0.8,0.07)")
    try:
        vals = [float(p) for p in partes]
    except ValueError as exc:
        raise UsageError(f"Valor não numérico em --caixa {raw!r}.") from exc
    norm = all(0.0 <= v <= 1.0 for v in vals)
    return {"x": vals[0], "y": vals[1], "w": vals[2], "h": vals[3], "norm": norm}


def cmd_trocar_texto(args: argparse.Namespace, settings: Any) -> int:
    pasta = _folder_or_die(args.pasta, settings)
    paths = _images_or_die(pasta, recursive=bool(getattr(args, "recursive", False)),
                           limite=getattr(args, "limite", None))

    de = getattr(args, "de", None)
    papel = getattr(args, "papel", None)
    caixa = _parse_caixa(getattr(args, "caixa", None))
    if not (de or papel or caixa):
        raise UsageError(
            "Preciso saber QUAL texto trocar. Use pelo menos um destes:\n"
            "    --de \"GARANTA O SEU\"       acha pelo texto atual (ignora acento e caixa)\n"
            "    --papel cta                acha pelo papel do bloco\n"
            "    --caixa 0.1,0.82,0.8,0.07  acha pela posição (fração da imagem)\n"
            f"\n  Não sabe o que tem nos criativos? Rode: {PROG} inspect {pasta}")

    saida = _default_out(settings, "texto", pasta, getattr(args, "out", None))
    alvo = de and f"“{de}”" or (papel and f"papel {papel}") or "a caixa informada"
    print(f"Trocando {bold(str(alvo))} por {bold('“' + args.para + '”')} em "
          f"{len(paths)} imagem(ns).")
    print(dim("  Motor determinístico: os pixels fora da caixa do texto ficam idênticos "
              "aos do original."))

    if getattr(args, "dry_run", False):
        print(yellow(f"--dry-run: nada foi escrito. Saída iria para {saida}"))
        return EXIT_OK

    _guard_out_dir(saida, bool(getattr(args, "force", False)))
    bar = Progress("trocando", total=len(paths))
    try:
        senao = None
        ancora = getattr(args, "senao_abaixo_de", None)
        if ancora:
            senao = {"ancora": str(ancora), "posicao": "abaixo", "texto": args.para}
        manifesto = _pipeline().run_replace_text_batch(
            paths, de, args.para, settings, saida,
            role=papel, box=caixa, progress=bar, senao_adicionar=senao,
            force=bool(getattr(args, "force", False)))
    finally:
        bar.close()
    return _finish(manifesto, saida)


# --------------------------------------------------------------------------- #
# ui
# --------------------------------------------------------------------------- #
def cmd_ui(args: argparse.Namespace, settings: Any) -> int:
    try:
        from .webui import run_server
    except ImportError as exc:
        falta = "s7editor.webui" in str(exc)
        detalhe = ("o módulo s7editor/webui.py não está nesta instalação"
                   if falta else f"faltam fastapi e uvicorn ({exc})\n"
                                 "  Instale com:  pip install fastapi uvicorn")
        raise RunError(
            f"Não consegui subir a interface web: {detalhe}.\n"
            f"  Tudo funciona pela linha de comando enquanto isso ({PROG} --help).") from exc

    host, porta = str(args.host), int(args.port)
    print(bold(f"Interface web em http://{host}:{porta}"))
    print(dim("  Abra no navegador. Para parar, Ctrl+C."))
    try:
        run_server(host=host, port=porta, settings=settings)
    except OSError as exc:
        raise RunError(f"Não consegui subir o servidor em {host}:{porta} ({exc}).\n"
                       "  Talvez a porta esteja ocupada — tente --port 8771.") from exc
    return EXIT_OK


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def _global_flags() -> argparse.ArgumentParser:
    """Flags aceitas antes E depois do subcomando.

    ``SUPPRESS`` é essencial: sem ele o subparser sobrescreveria com ``None``
    o valor que o usuário passou antes do subcomando.
    """
    g = argparse.ArgumentParser(add_help=False)
    g.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS,
                   help="mostra o plano e não escreve nada")
    g.add_argument("--out", "-o", metavar="PASTA", default=argparse.SUPPRESS,
                   help="pasta de saída (padrão: outbox/<nome-do-lote>)")
    g.add_argument("--concurrency", "-j", type=int, metavar="N", default=argparse.SUPPRESS,
                   help="quantas imagens processar em paralelo")
    g.add_argument("--verbose", "-v", action="store_true", default=argparse.SUPPRESS,
                   help="mais detalhes e traceback completo em caso de erro")
    g.add_argument("--force", "-f", action="store_true", default=argparse.SUPPRESS,
                   help="sobrescreve pasta de saída/arquivos existentes")
    g.add_argument("--quality", choices=["low", "medium", "high"], default=argparse.SUPPRESS,
                   help="qualidade (e custo) das operações com IA")
    return g


def build_parser() -> argparse.ArgumentParser:
    g = _global_flags()
    p = _Parser(
        prog=PROG, parents=[g],
        description="S7 Editor — edição de criativos em lote com garantia de zero drift.",
        epilog=("Exemplos:\n"
                f"  {PROG} init\n"
                f"  {PROG} inspect inbox/campanha-agosto\n"
                f"  {PROG} trocar-texto inbox/campanha-agosto --de \"GARANTA O SEU\" --para \"ULTIMAS VAGAS\"\n"
                f"  {PROG} reframe inbox/campanha-agosto --to 16:9 --mode relayout\n"
                f"  {PROG} vary inbox/referencias -n 30\n"
                f"  {PROG} run recipes/trocar-cta.yaml\n"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="store_true", help="mostra a versão e sai")
    sub = p.add_subparsers(dest="cmd", metavar="comando")

    s = sub.add_parser("init", parents=[g], help="cria pastas, receitas de exemplo e .env.example",
                       description="Prepara inbox/, outbox/, recipes/, fonts/ e o .env.example.")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("doctor", parents=[g], help="checa dependências, fontes e chave",
                       description="Diz exatamente o que está faltando para rodar.")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("inspect", parents=[g], help="analisa uma pasta e lista os blocos de texto",
                       description="Mostra tamanho, formato e os blocos de texto de cada criativo.")
    s.add_argument("pasta", help="pasta com os criativos")
    s.add_argument("--json", action="store_true", help="sai em JSON estruturado (stdout limpo)")
    s.add_argument("--recursive", "-r", action="store_true", help="inclui subpastas")
    s.add_argument("--limite", "--limit", type=int, default=None, metavar="N",
                   help="processa só as N primeiras (use --limite 1 para provar antes do lote)")
    s.add_argument("--offline", action="store_true",
                   help="força a detecção offline mesmo com chave configurada")
    s.set_defaults(func=cmd_inspect)

    s = sub.add_parser("run", parents=[g], help="executa uma receita .yaml",
                       description="Executa a receita e entrega ZIP + relatório.")
    s.add_argument("receita", help="caminho da receita (ex.: recipes/trocar-cta.yaml)")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("reframe", parents=[g], help="converte o lote para outro formato",
                       description="Converte de 9:16 para 16:9 (ou qualquer par) sem distorcer.")
    s.add_argument("pasta", help="pasta com os criativos")
    s.add_argument("--to", required=True, metavar="FORMATO",
                   help="formato de destino: 16:9, 1080x1920 ou 9:16@1080")
    s.add_argument("--mode", default="pad", choices=["pad", "outpaint", "relayout", "crop"],
                   help="pad (offline) | crop (offline) | relayout (offline) | outpaint (IA)")
    s.add_argument("--long-edge", type=int, metavar="PX",
                   help="lado maior em pixels quando o formato não traz tamanho (padrão 1440)")
    s.add_argument("--recursive", "-r", action="store_true", help="inclui subpastas")
    s.add_argument("--limite", "--limit", type=int, default=None, metavar="N",
                   help="processa só as N primeiras (use --limite 1 para provar antes do lote)")
    s.set_defaults(func=cmd_reframe)

    s = sub.add_parser("vary", parents=[g], help="gera variações a partir de referências",
                       description="Lê o DNA das referências e devolve criativos parecidos.")
    s.add_argument("pasta", help="pasta com os criativos de referência")
    s.add_argument("-n", type=int, default=10, metavar="N", help="quantas variações gerar")
    s.add_argument("--mode", default="template",
                   choices=["template", "generative", "hybrid", "remix", "copy"],
                   help="template (offline) | generative/hybrid (IA) | remix | copy")
    s.add_argument("--recursive", "-r", action="store_true", help="inclui subpastas")
    s.add_argument("--limite", "--limit", type=int, default=None, metavar="N",
                   help="processa só as N primeiras (use --limite 1 para provar antes do lote)")
    s.set_defaults(func=cmd_vary)

    s = sub.add_parser("trocar-texto", parents=[g], aliases=["replace-text"],
                       help="troca um texto em todo o lote sem mexer no resto",
                       description="O atalho mais pedido: muda só o texto pedido, "
                                   "com garantia de zero drift.")
    s.add_argument("pasta", help="pasta com os criativos")
    s.add_argument("--de", metavar="TEXTO", help="texto atual (ignora acento e caixa)")
    s.add_argument("--para", required=True, metavar="TEXTO", help="texto novo")
    s.add_argument("--papel", "--role", dest="papel", metavar="PAPEL",
                   choices=["headline", "subhead", "cta", "price", "badge", "legal", "logo", "other"],
                   help="acha o bloco pelo papel em vez do texto")
    s.add_argument("--caixa", "--box", dest="caixa", metavar="x,y,w,h",
                   help="acha o bloco pela posição (pixels ou fração 0–1)")
    s.add_argument("--senao-abaixo-de", dest="senao_abaixo_de", metavar="PAPEL",
                   help="se não achar o texto, escreve embaixo deste bloco "
                        "(ex.: --senao-abaixo-de price)")
    s.add_argument("--recursive", "-r", action="store_true", help="inclui subpastas")
    s.add_argument("--limite", "--limit", type=int, default=None, metavar="N",
                   help="processa só as N primeiras (use --limite 1 para provar antes do lote)")
    s.set_defaults(func=cmd_trocar_texto)

    s = sub.add_parser("ui", parents=[g], help="sobe a interface web",
                       description="Interface web local para arrastar as imagens e editar.")
    s.add_argument("--host", default="127.0.0.1", help="padrão 127.0.0.1 (só esta máquina)")
    s.add_argument("--port", type=int, default=8770, help="padrão 8770")
    s.set_defaults(func=cmd_ui)

    return p


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def _version() -> str:
    try:
        from . import __version__  # type: ignore

        return str(__version__)
    except Exception:  # noqa: BLE001
        return "0.1.0"


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada. Devolve 0 (ok), 1 (falhou) ou 2 (uso errado)."""
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:   # --help sai 0; erro de uso sai 2
        return int(exc.code or 0)

    if getattr(args, "version", False):
        print(f"S7 Editor {_version()}")
        return EXIT_OK
    if not getattr(args, "cmd", None):
        parser.print_help()
        return EXIT_USAGE

    verbose = bool(getattr(args, "verbose", False))
    try:
        settings = load_settings(
            dry_run=getattr(args, "dry_run", None),
            verbose=verbose or None,
            max_concurrency=getattr(args, "concurrency", None),
            quality=getattr(args, "quality", None),
        )
    except Exception as exc:  # noqa: BLE001
        err(red(f"erro ao carregar a configuração: {exc}"))
        return EXIT_FAIL

    if verbose:
        import logging

        logging.basicConfig(level=logging.INFO, format="  [%(name)s] %(message)s",
                            stream=sys.stderr)

    try:
        return int(args.func(args, settings))
    except UsageError as exc:
        err(f"\n{red('erro')}: {exc}")
        return EXIT_USAGE
    except KeyboardInterrupt:
        err(f"\n{yellow('interrompido')}: nada mais foi escrito. "
            "Os arquivos já gerados continuam na pasta de saída.")
        return EXIT_FAIL
    except Exception as exc:  # noqa: BLE001
        # Erros que os módulos levantam com mensagem pronta em português
        # (chave ausente, receita inválida, fonte faltando) chegam aqui.
        nome = type(exc).__name__
        if verbose:
            import traceback

            traceback.print_exc()
        msg = str(exc) or nome
        err(f"\n{red('erro')}: {msg}")
        if not verbose:
            err(dim(f"  ({nome} — rode de novo com --verbose para ver o traceback)"))
        return EXIT_FAIL


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
