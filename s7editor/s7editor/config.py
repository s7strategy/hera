"""Configuração global do S7 Editor.

Duas responsabilidades, e só:

1. Descobrir a chave da OpenAI sem que o usuário precise exportar variável de
   ambiente na mão — ele já tem um ``.env`` em algum lugar (do próprio projeto,
   do home, ou do ORION Studio) e queremos aproveitá-lo.
2. Centralizar caminhos, modelos e a tabela de preços num objeto só, para que
   nenhum outro módulo precise ler ``os.environ`` por conta própria.

Nada aqui faz chamada de rede, e ``import s7editor.config`` é barato: a leitura
dos ``.env`` acontece dentro de :func:`load_settings`, não no import.

A chave NUNCA é impressa. Se algum diagnóstico precisar exibi-la, use
:func:`mask_key`, que devolve algo como ``sk-...AB12``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

__all__ = [
    "Settings",
    "MissingAPIKeyError",
    "load_settings",
    "has_openai",
    "require_openai",
    "mask_key",
    "read_env_file",
    "env_candidates",
    "price_per_image",
    "PRICING",
    "PLACEHOLDER_VALUES",
]

# --------------------------------------------------------------------------- #
# Raiz do projeto
# --------------------------------------------------------------------------- #
# config.py fica em <root>/s7editor/config.py, logo a raiz é o avô do arquivo.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# Nome da variável em todos os .env que consultamos.
API_KEY_VAR = "OPENAI_API_KEY"

# Valores que existem só para o usuário saber onde escrever a chave. O ORION
# Studio grava exatamente "sua_chave_aqui" no template dele — tratar isso como
# chave válida geraria um 401 confuso lá na frente.
PLACEHOLDER_VALUES: frozenset[str] = frozenset({
    "",
    "sua_chave_aqui",
    "sua-chave-aqui",
    "coloque_sua_chave_aqui",
    "your_api_key_here",
    "your-api-key-here",
    "your_openai_api_key",
    "changeme",
    "change_me",
    "todo",
    "xxx",
    "xxxx",
    "none",
    "null",
    "undefined",
    "sk-xxx",
    "sk-...",
    "sk-proj-xxx",
})


# --------------------------------------------------------------------------- #
# Preços (custo estimado por IMAGEM)
# --------------------------------------------------------------------------- #
# ATENÇÃO: estes valores são ESTIMATIVAS baseadas na tabela pública do
# gpt-image-1 e podem mudar sem aviso. Este é o ÚNICO lugar do projeto onde
# preço aparece — para atualizar, mexa só aqui.
#
# Formato:
#     PRICING[modelo][qualidade][tamanho] -> USD por imagem
#     PRICING["vision"]["per_image"]      -> USD por imagem analisada
#     PRICING["_default"]                 -> chute conservador quando nada casa
#
# Use :func:`price_per_image` em vez de indexar na mão: ela tolera tamanho
# "auto", qualidade desconhecida e modelo novo sem estourar KeyError.
PRICING: dict[str, Any] = {
    "gpt-image-1": {
        "low": {"1024x1024": 0.011, "1024x1536": 0.016, "1536x1024": 0.016},
        "medium": {"1024x1024": 0.042, "1024x1536": 0.063, "1536x1024": 0.063},
        "high": {"1024x1024": 0.167, "1024x1536": 0.250, "1536x1024": 0.250},
    },
    # Uma análise de criativo = 1 imagem + ~500 tokens de saída. Estimativa.
    "vision": {"per_image": 0.003},
    # Trilha determinística não custa nada: fica registrado para o manifesto.
    "deterministic": {"per_image": 0.0},
    "_default": 0.05,
}


def price_per_image(model: str, size: str | None = None,
                    quality: str | None = None, n: int = 1) -> float:
    """Custo estimado em USD de ``n`` imagens, tolerante a chaves desconhecidas.

    Quando o tamanho é "auto" (ou não está na tabela) devolvemos o MAIOR preço
    da faixa de qualidade: é melhor superestimar o orçamento do que assustar o
    usuário com uma fatura maior que o previsto.
    """
    n = max(0, int(n))
    if n == 0:
        return 0.0
    table = PRICING.get(str(model or "").strip())
    if table is None:
        return float(PRICING["_default"]) * n
    if "per_image" in table:
        return float(table["per_image"]) * n

    q = str(quality or "medium").strip().lower()
    if q in ("auto", "standard", "default", ""):
        q = "medium"
    tier = table.get(q) or table.get("medium") or next(iter(table.values()))

    key = str(size or "auto").strip().lower().replace(" ", "")
    if key in tier:
        return float(tier[key]) * n
    return float(max(tier.values())) * n


# --------------------------------------------------------------------------- #
# Leitor de .env (sem python-dotenv, que não é dependência do projeto)
# --------------------------------------------------------------------------- #
def read_env_file(path: str | Path) -> dict[str, str]:
    """Lê um ``.env`` simples e devolve o dicionário de variáveis.

    Aceita o que se vê no mundo real: linhas em branco, ``#`` de comentário,
    ``export FOO=bar``, valores entre aspas simples ou duplas e comentário no
    fim da linha (só quando o valor NÃO está entre aspas — dentro de aspas o
    ``#`` é conteúdo legítimo). Arquivo ausente ou ilegível devolve ``{}``:
    ler configuração nunca deve derrubar o programa.
    """
    p = Path(path)
    out: dict[str, str] = {}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return out

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if value[:1] in ("'", '"'):
            # Valor entre aspas: o conteúdo vai até a aspa de fechamento e o
            # que vier depois (tipicamente um comentário) é descartado. Assim
            # um '#' DENTRO das aspas continua sendo conteúdo legítimo.
            quote = value[0]
            end = value.find(quote, 1)
            value = value[1:end] if end > 0 else value[1:]
        else:
            for marker in (" #", "\t#"):
                idx = value.find(marker)
                if idx >= 0:
                    value = value[:idx]
            value = value.strip()
        out[key] = value
    return out


def env_candidates(root: Path | None = None) -> list[Path]:
    """Arquivos ``.env`` consultados, do mais específico para o mais genérico.

    A ordem importa: o primeiro arquivo que trouxer uma chave real vence.
    Inclui os ``.env`` do ORION Studio porque o usuário costuma já ter a chave
    configurada lá e não faz sentido pedir de novo.
    """
    root = Path(root) if root else PROJECT_ROOT
    parent = root.parent
    cands = [
        root / ".env",
        root / ".env.local",
        Path.home() / ".s7editor" / ".env",
        Path("/opt/orion-studio/agent-os/.env"),
        parent / "orion-studio" / "agent-os" / ".env",
        parent.parent / "orion-studio" / "agent-os" / ".env",
        Path.home() / "orion-studio" / "agent-os" / ".env",
    ]
    seen: set[str] = set()
    uniq: list[Path] = []
    for c in cands:
        key = str(c)
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


def _clean_key(value: Any) -> str | None:
    """Normaliza um valor de chave; devolve None se for vazio ou placeholder."""
    if value is None:
        return None
    s = str(value).strip().strip('"').strip("'").strip()
    if not s or s.lower() in PLACEHOLDER_VALUES:
        return None
    # Placeholders genéricos: nada além de letra repetida ou "<...>"
    if s.startswith("<") and s.endswith(">"):
        return None
    if len(s) < 12:  # chave real da OpenAI é bem mais longa que isso
        return None
    return s


def discover_api_key(root: Path | None = None) -> tuple[str | None, str]:
    """Procura a chave e devolve ``(chave, origem)`` para diagnóstico.

    Origem é uma string legível ("variável de ambiente", caminho do .env) que o
    ``doctor`` mostra ao usuário. A chave em si nunca entra nessa string.
    """
    env_value = _clean_key(os.environ.get(API_KEY_VAR))
    if env_value:
        return env_value, f"variável de ambiente {API_KEY_VAR}"
    for path in env_candidates(root):
        if not path.is_file():
            continue
        data = read_env_file(path)
        value = _clean_key(data.get(API_KEY_VAR))
        if value:
            return value, str(path)
    return None, "não encontrada"


def mask_key(key: str | None) -> str:
    """``sk-proj-abc...WX9Z`` -> ``sk-...WX9Z``. Use SEMPRE que for exibir."""
    if not key:
        return "(ausente)"
    tail = key[-4:] if len(key) >= 8 else "????"
    prefix = "sk" if key.startswith("sk") else key[:2]
    return f"{prefix}-...{tail}"


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
@dataclass
class Settings:
    """Configuração de uma execução. Construa com :func:`load_settings`."""

    openai_api_key: str | None = None
    image_model: str = "gpt-image-1"
    vision_model: str = "gpt-4.1-mini"
    root: Path = PROJECT_ROOT
    inbox: Path = field(default_factory=lambda: PROJECT_ROOT / "inbox")
    outbox: Path = field(default_factory=lambda: PROJECT_ROOT / "outbox")
    cache_dir: Path = field(default_factory=lambda: PROJECT_ROOT / ".cache")
    fonts_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "fonts")
    max_concurrency: int = 4
    dry_run: bool = False
    quality: str = "medium"        # low | medium | high (gpt-image-1)
    verbose: bool = False
    key_source: str = "não encontrada"   # de onde veio a chave, para o doctor

    # -- conveniências ----------------------------------------------------- #
    @property
    def has_key(self) -> bool:
        return bool(self.openai_api_key)

    def masked_key(self) -> str:
        return mask_key(self.openai_api_key)

    def ensure_dirs(self) -> "Settings":
        """Cria inbox/outbox/cache/fonts. Chamada explícita — nunca no import."""
        for d in (self.inbox, self.outbox, self.cache_dir, self.fonts_dir):
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        return self

    def with_overrides(self, **kw: Any) -> "Settings":
        return replace(self, **{k: v for k, v in kw.items() if v is not None})

    def to_dict(self) -> dict[str, Any]:
        """Serialização segura: a chave sai MASCARADA, nunca em claro."""
        return {
            "openai_api_key": self.masked_key(),
            "key_source": self.key_source,
            "image_model": self.image_model,
            "vision_model": self.vision_model,
            "root": str(self.root),
            "inbox": str(self.inbox),
            "outbox": str(self.outbox),
            "cache_dir": str(self.cache_dir),
            "fonts_dir": str(self.fonts_dir),
            "max_concurrency": self.max_concurrency,
            "dry_run": self.dry_run,
            "quality": self.quality,
            "verbose": self.verbose,
        }

    def __repr__(self) -> str:  # evita vazar a chave em traceback/log
        return (f"Settings(root={str(self.root)!r}, image_model={self.image_model!r}, "
                f"quality={self.quality!r}, openai_api_key={self.masked_key()!r})")


_TRUE = {"1", "true", "yes", "y", "on", "sim", "verdadeiro"}
_FALSE = {"0", "false", "no", "n", "off", "nao", "não", "falso"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    s = raw.strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(str(raw).strip()) if raw is not None else default
    except ValueError:
        return default


def load_settings(**overrides: Any) -> Settings:
    """Monta o :class:`Settings` da execução.

    Precedência (o primeiro que tiver valor ganha):
    ``overrides`` explícitos > variáveis ``S7EDITOR_*`` / ``OPENAI_API_KEY`` >
    ``.env`` do projeto > ``~/.s7editor/.env`` > ``.env`` do ORION Studio >
    padrões deste arquivo.

    Overrides com valor ``None`` são ignorados (facilita repassar argumentos de
    CLI opcionais direto para cá sem um monte de ``if``).
    """
    over = {k: v for k, v in overrides.items() if v is not None}

    root = Path(over.pop("root", os.environ.get("S7EDITOR_ROOT") or PROJECT_ROOT)).expanduser().resolve()

    key = _clean_key(over.pop("openai_api_key", None))
    source = "override explícito"
    if not key:
        key, source = discover_api_key(root)

    quality = str(over.pop("quality", os.environ.get("S7EDITOR_QUALITY") or "medium")).strip().lower()
    if quality not in ("low", "medium", "high", "auto"):
        quality = "medium"

    settings = Settings(
        openai_api_key=key,
        key_source=source,
        image_model=str(over.pop("image_model", os.environ.get("S7EDITOR_IMAGE_MODEL") or "gpt-image-1")),
        vision_model=str(over.pop("vision_model", os.environ.get("S7EDITOR_VISION_MODEL") or "gpt-4.1-mini")),
        root=root,
        inbox=Path(over.pop("inbox", os.environ.get("S7EDITOR_INBOX") or root / "inbox")).expanduser(),
        outbox=Path(over.pop("outbox", os.environ.get("S7EDITOR_OUTBOX") or root / "outbox")).expanduser(),
        cache_dir=Path(over.pop("cache_dir", os.environ.get("S7EDITOR_CACHE") or root / ".cache")).expanduser(),
        fonts_dir=Path(over.pop("fonts_dir", os.environ.get("S7EDITOR_FONTS") or root / "fonts")).expanduser(),
        max_concurrency=max(1, int(over.pop("max_concurrency", _env_int("S7EDITOR_CONCURRENCY", 4)))),
        dry_run=bool(over.pop("dry_run", _env_bool("S7EDITOR_DRY_RUN", False))),
        quality=quality,
        verbose=bool(over.pop("verbose", _env_bool("S7EDITOR_VERBOSE", False))),
    )
    if over:
        # Chave desconhecida é erro de programação nosso, não do usuário.
        raise TypeError(f"load_settings() recebeu opções desconhecidas: {sorted(over)}")
    return settings


def has_openai(settings: Settings | None = None) -> bool:
    """True se existe chave utilizável. Não valida a chave na rede."""
    if settings is None:
        return bool(discover_api_key()[0])
    return bool(settings.openai_api_key)


class MissingAPIKeyError(RuntimeError):
    """Falta a OPENAI_API_KEY para uma operação que exige IA."""


def require_openai(settings: Settings) -> str:
    """Devolve a chave ou explica, em português, exatamente como configurá-la."""
    if settings and settings.openai_api_key:
        return settings.openai_api_key

    root = settings.root if settings else PROJECT_ROOT
    locais = "\n".join(f"      - {p}" for p in env_candidates(root)[:5])
    raise MissingAPIKeyError(
        "Esta operação usa IA (gpt-image-1) e não encontrei a chave da OpenAI.\n"
        "\n"
        "  Como resolver (escolha UM caminho):\n"
        f"    1) Crie o arquivo {root / '.env'} com a linha:\n"
        f"          {API_KEY_VAR}=sk-sua-chave-real-aqui\n"
        f"    2) Ou exporte no terminal:  export {API_KEY_VAR}=sk-...\n"
        "    3) Ou salve em ~/.s7editor/.env com a mesma linha.\n"
        "\n"
        "  Procurei nestes lugares:\n"
        f"{locais}\n"
        "\n"
        "  Observação: valores de exemplo como \"sua_chave_aqui\" são ignorados\n"
        "  de propósito — troque pelo valor real.\n"
        "\n"
        "  Você NÃO precisa de chave para o modo determinístico: trocar texto,\n"
        "  apagar texto e reenquadrar com pad/crop funcionam 100% offline.\n"
        "  Rode o mesmo comando com --engine deterministic."
    )
