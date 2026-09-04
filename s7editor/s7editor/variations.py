"""Variações em lote: 30 criativos de referência entram, 30 novos saem.

O módulo tem duas responsabilidades bem separadas:

1. **Copy** (:func:`copy_angles`) — escrever ``n`` conjuntos de texto
   (headline, subhead, CTA) no tom da marca, cada um puxando por um ângulo
   diferente (urgência, prova social, benefício, objeção...). Com chave da
   OpenAI o texto vem do modelo; sem chave um gerador **determinístico** monta
   as combinações a partir do :class:`CreativeDNA`. Mesmo DNA + mesmo ``n`` =>
   mesmíssimo resultado, sempre (nada de ``random`` sem semente).

2. **Imagem** (:func:`generate_variations`) — produzir as ``n`` peças em um de
   três modos:

   ``template``   pega criativos reais como base e troca **só os textos** com
                  :func:`textedit.replace_text`. Consistência perfeita de marca,
                  custo zero, drift zero (verificado com ``protect.drift_report``).
                  É o modo recomendado quando existem referências.
   ``hybrid``     gera o **fundo** com IA e escreve o texto por cima de forma
                  determinística. Junta a variedade visual da IA com tipografia
                  que não erra ortografia.
   ``generative`` só a IA, do fundo ao (eventual) texto. Mais variado e mais
                  arriscado — ver o aviso em :func:`generate_variations`.

Todos os modos devolvem ``list[tuple[Image, dict]]``; o ``dict`` carrega o
ângulo da copy, o prompt usado, o modo, o custo estimado e as caixas alteradas.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import threading
import unicodedata
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from PIL import Image, ImageDraw

from . import aigen as _aigen
from . import imageio_util as _io
from . import protect as _protect
from . import textedit as _textedit
from . import vision as _vision
from .config import Settings, load_settings, require_openai
from .models import (
    AspectSpec,
    BackgroundKind,
    Box,
    CreativeAnalysis,
    CreativeDNA,
    FontSpec,
    TextRole,
    color_to_hex,
)

__all__ = [
    "copy_angles",
    "generate_variations",
    # extras públicos, úteis para pipeline.py / cli.py
    "CopyAngle",
    "ANGLES",
    "MODES",
    "build_background_prompt",
    "layout_for",
    "variation_warnings",
    "clear_variation_warnings",
]

log = logging.getLogger("s7editor.variations")

#: Modos aceitos por :func:`generate_variations` (o primeiro nome é o canônico).
MODES: tuple[str, ...] = ("template", "hybrid", "generative")

_MODE_ALIASES: dict[str, str] = {
    "template": "template", "modelo": "template", "base": "template",
    "deterministic": "template", "deterministico": "template",
    "hybrid": "hybrid", "hibrido": "hybrid", "híbrido": "hybrid", "misto": "hybrid",
    "generative": "generative", "generativo": "generative", "ai": "generative",
    "ia": "generative",
}

#: Teto de segurança: 500 imagens de IA seriam ~US$ 30 sem ninguém perceber.
MAX_VARIATIONS = 200

#: Headline mais comprida que isto quase nunca cabe na caixa do criativo sem
#: derrubar o corpo da fonte (ver a escada de degradação em textedit.plan_fit).
MAX_HEADLINE_CHARS = 46

#: Chaves de copy -> papel do bloco de texto no criativo.
ROLE_OF_KEY: dict[str, TextRole] = {
    "headline": TextRole.HEADLINE,
    "subhead": TextRole.SUBHEAD,
    "cta": TextRole.CTA,
}
_COPY_KEYS: tuple[str, ...] = ("headline", "subhead", "cta")


# --------------------------------------------------------------------------- #
# Avisos (mesmo padrão de fonts/textedit: o pipeline drena para o manifesto)
# --------------------------------------------------------------------------- #
_warn_lock = threading.Lock()
_warnings: list[str] = []


def _warn(msg: str) -> str:
    with _warn_lock:
        if msg not in _warnings:
            _warnings.append(msg)
    log.warning("%s", msg)
    return msg


def variation_warnings() -> list[str]:
    """Avisos acumulados desde o último :func:`clear_variation_warnings`."""
    with _warn_lock:
        return list(_warnings)


def clear_variation_warnings() -> None:
    with _warn_lock:
        _warnings.clear()


def _tick(progress: Callable[[int, int, str], None] | None,
          i: int, total: int, msg: str) -> None:
    """Chama o callback de progresso sem deixar ele derrubar o lote.

    Convenção: ``i`` é 1-based e a chamada acontece ANTES de processar o item,
    para que a barra mostre o que está em andamento.
    """
    if progress is None:
        return
    try:
        progress(i, total, msg)
    except Exception:  # noqa: BLE001 - callback do usuário não quebra o lote
        log.debug("callback de progresso falhou", exc_info=True)


# --------------------------------------------------------------------------- #
# Ângulos de copy
# --------------------------------------------------------------------------- #
class CopyAngle:
    """Um ângulo de venda com seus moldes de texto em português.

    Os moldes existem para a trilha OFFLINE. Eles são propositalmente genéricos
    e **nunca inventam número, preço, prazo ou estatística** — copy publicitária
    com dado falso é problema jurídico, não criativo. O que sai daqui é um
    esqueleto para o time revisar; com chave da OpenAI o texto vem bem melhor.
    """

    __slots__ = ("slug", "label", "brief", "headlines", "subheads", "ctas")

    def __init__(self, slug: str, label: str, brief: str,
                 headlines: Sequence[str], subheads: Sequence[str],
                 ctas: Sequence[str]) -> None:
        self.slug = slug
        self.label = label
        self.brief = brief
        self.headlines = tuple(headlines)
        self.subheads = tuple(subheads)
        self.ctas = tuple(ctas)

    def __repr__(self) -> str:  # pragma: no cover - conveniência de debug
        return f"CopyAngle({self.slug!r})"


#: ``{tema}`` é preenchido com o assunto do DNA (ou "esta oferta" se não houver).
ANGLES: tuple[CopyAngle, ...] = (
    CopyAngle(
        "urgencia", "urgência", "senso de tempo curto, decisão hoje",
        ["Últimos dias de {tema}", "Acaba antes do que você imagina",
         "Hoje ainda dá tempo", "Depois dessa semana, não dá mais"],
        ["A janela para {tema} fecha em breve.", "Quem deixa para depois fica de fora.",
         "Decida agora e resolva de uma vez."],
        ["Garanta agora", "Quero antes que acabe", "Aproveitar hoje"],
    ),
    CopyAngle(
        "prova_social", "prova social", "outras pessoas já escolheram",
        ["Quem testou não voltou atrás", "A escolha de quem entende de {tema}",
         "Todo mundo comentando {tema}", "Você seria o próximo a recomendar"],
        ["Gente como você já resolveu isso.", "A recomendação vem de quem já usou.",
         "Entre para o time que já decidiu."],
        ["Ver por que todos falam", "Quero entender", "Entrar para o time"],
    ),
    CopyAngle(
        "beneficio", "benefício", "o ganho concreto para o cliente",
        ["{tema} do jeito que você queria", "Mais resultado, menos esforço",
         "O que muda quando você tem {tema}", "Simples assim: funciona"],
        ["Você ganha tempo e para de improvisar.", "Feito para resolver, não para enfeitar.",
         "O ganho aparece já na primeira semana."],
        ["Quero esse resultado", "Começar agora", "Ver como funciona"],
    ),
    CopyAngle(
        "objecao", "objeção", "derruba o motivo de não comprar",
        ["Achou que não era para você?", "Sem complicação, sem letra miúda",
         "{tema} sem enrolação", "Não precisa entender de nada"],
        ["A gente cuida da parte chata.", "Você não precisa mudar sua rotina.",
         "É mais simples do que parece."],
        ["Tirar minha dúvida", "Ver como é simples", "Falar com a gente"],
    ),
    CopyAngle(
        "preco", "preço", "custo-benefício, sem inventar valores",
        ["Cabe no seu orçamento", "Você paga menos do que imagina",
         "{tema} sem pesar no bolso", "Investimento que se paga"],
        ["Condição pensada para caber no seu mês.", "Custa menos que continuar improvisando.",
         "Transparência total, do começo ao fim."],
        ["Ver as condições", "Quero saber o valor", "Conferir a oferta"],
    ),
    CopyAngle(
        "curiosidade", "curiosidade", "abre um laço que só o clique fecha",
        ["Ninguém te contou isso sobre {tema}", "O detalhe que muda tudo",
         "Tem um jeito melhor de fazer isso", "Você está fazendo do jeito difícil"],
        ["Leva dois minutos para entender.", "O motivo é mais simples do que parece.",
         "Spoiler: não é o que você está pensando."],
        ["Descobrir agora", "Quero ver", "Me mostra"],
    ),
    CopyAngle(
        "autoridade", "autoridade", "quem fala tem bagagem",
        ["Feito por quem vive de {tema}", "Do jeito que os profissionais fazem",
         "Método, não sorte", "Sem achismo"],
        ["Anos de prática destilados em algo simples.", "A base é técnica, o resultado é prático.",
         "Quem faz todo dia resolveu por você."],
        ["Conhecer o método", "Ver por dentro", "Quero aprender"],
    ),
    CopyAngle(
        "exclusividade", "exclusividade", "não é para todo mundo",
        ["Não é para todo mundo", "Só para quem leva {tema} a sério",
         "Acesso limitado", "Convite aberto por pouco tempo"],
        ["Selecionamos quem realmente vai usar.", "Poucas vagas, de propósito.",
         "Quem entra, entra bem acompanhado."],
        ["Quero meu acesso", "Solicitar convite", "Entrar na lista"],
    ),
    CopyAngle(
        "transformacao", "transformação", "antes e depois",
        ["Do caos ao controle", "Antes era difícil. Agora não é.",
         "{tema} vira rotina, não problema", "A virada começa aqui"],
        ["A diferença aparece em poucos dias.", "Você não volta para o jeito antigo.",
         "Comece hoje, colha semana que vem."],
        ["Começar a virada", "Quero mudar isso", "Dar o primeiro passo"],
    ),
    CopyAngle(
        "novidade", "novidade", "chegou algo novo",
        ["Chegou {tema}", "Novo por aqui", "Acabou de sair",
         "A versão que faltava"],
        ["Feito do zero, com o que aprendemos até aqui.", "Novo, e já do jeito certo.",
         "Você é dos primeiros a ver."],
        ["Ver a novidade", "Conhecer agora", "Quero ser o primeiro"],
    ),
    CopyAngle(
        "facilidade", "facilidade", "sem fricção, sem esforço",
        ["Em poucos cliques", "Sem burocracia", "{tema} resolvido em minutos",
         "Comece sem instalar nada"],
        ["Do jeito mais simples que existe.", "Você faz sozinho, do celular.",
         "Sem formulário eterno, sem espera."],
        ["Começar agora", "Testar em 1 minuto", "É rápido, quero ver"],
    ),
    CopyAngle(
        "garantia", "garantia", "risco zero para decidir",
        ["Risco zero para experimentar", "Se não servir, a gente resolve",
         "Teste {tema} sem compromisso", "A decisão continua sendo sua"],
        ["Você experimenta antes de decidir.", "Sem pegadinha e sem fidelidade.",
         "Se não for para você, é só avisar."],
        ["Experimentar sem risco", "Quero testar", "Começar o teste"],
    ),
)

_ANGLE_BY_SLUG: dict[str, CopyAngle] = {a.slug: a for a in ANGLES}


# --------------------------------------------------------------------------- #
# Utilidades determinísticas
# --------------------------------------------------------------------------- #
def _stable_seed(*parts: Any) -> int:
    """Semente reprodutível entre processos.

    ``hash()`` de str em Python é randomizado por execução (PYTHONHASHSEED),
    então usamos sha256: o mesmo DNA gera a mesma copy amanhã e na máquina do
    cliente, que é o que permite reexecutar um lote e obter o mesmo pacote.
    """
    blob = "\x1f".join(str(p) for p in parts).encode("utf-8", "replace")
    return int.from_bytes(hashlib.sha256(blob).digest()[:8], "big")


def _dna_signature(dna: CreativeDNA) -> str:
    try:
        return json.dumps(dna.to_dict(), sort_keys=True, ensure_ascii=False)
    except Exception:  # noqa: BLE001 - DNA estranho não pode derrubar a copy
        return repr(dna)


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


_META_WORDS = {
    "padrao", "padrão", "headline", "headlines", "subhead", "cta", "ctas",
    "geralmente", "sempre", "estrutura", "tom", "frase", "frases", "verbo",
    "imperativo", "caixa alta", "uppercase", "curta", "curto", "maiuscula",
}


def _looks_like_copy(s: Any) -> bool:
    """True quando a string parece uma frase de anúncio, não a DESCRIÇÃO de um padrão.

    ``CreativeDNA.copy_patterns`` guarda headlines reais quando o DNA foi
    montado offline, mas guarda descrições ("headline curta, verbo no
    imperativo") quando veio do modelo. Reaproveitar uma descrição como copy
    seria constrangedor, então filtramos.
    """
    t = str(s or "").strip()
    if not (2 <= len(t) <= 70):
        return False
    low = _strip_accents(t.lower())
    if any(w in low for w in _META_WORDS):
        return False
    if t.endswith(":") or low.startswith(("ex.", "exemplo", "obs")):
        return False
    return len(t.split()) <= 12


def _mostly_upper(values: Iterable[str]) -> bool:
    vals = [v for v in values if any(c.isalpha() for c in v)]
    if not vals:
        return False
    up = sum(1 for v in vals if v == v.upper())
    return up * 2 > len(vals)


def _theme(dna: CreativeDNA) -> str:
    """Assunto curto para preencher ``{tema}`` nos moldes."""
    raw = str(dna.subject_matter or "").strip()
    if not raw:
        for c in dna.copy_patterns or []:
            if _looks_like_copy(c):
                raw = str(c)
                break
    raw = raw.split(".")[0].split(";")[0].strip().strip('"“”')
    if len(raw) > 48:
        raw = raw[:48].rsplit(" ", 1)[0]
    if not raw:
        return "esta oferta"
    # Minúscula inicial só quando não parece nome próprio (evita "Nike" -> "nike").
    if raw[:1].isupper() and not raw.split()[0].isupper() and len(raw.split()) > 1:
        raw = raw[0].lower() + raw[1:]
    return raw


def _pick(pool: Sequence[str], step: int, offset: int) -> str:
    """Escolha cíclica determinística dentro de um pool."""
    if not pool:
        return ""
    return pool[(step + offset) % len(pool)]


def _offline_copy(dna: CreativeDNA, n: int) -> list[dict[str, str]]:
    """``n`` conjuntos de copy sem tocar na rede. Reprodutível byte a byte."""
    seed = _stable_seed(_dna_signature(dna), n)
    rng = random.Random(seed)          # semeado: reexecutar dá o mesmo resultado
    tema = _theme(dna)

    ref_ctas = [str(c).strip() for c in (dna.cta_patterns or []) if _looks_like_copy(c)]
    ref_heads = [str(c).strip() for c in (dna.copy_patterns or []) if _looks_like_copy(c)]
    upper_cta = _mostly_upper(ref_ctas)
    upper_head = _mostly_upper(ref_heads)

    order = list(ANGLES)
    rng.shuffle(order)                 # ordem estável para um mesmo DNA

    out: list[dict[str, str]] = []
    seen_head: set[str] = set()
    for i in range(n):
        ang = order[i % len(order)]
        cycle = i // len(order)
        off = _stable_seed(ang.slug, seed) % 7

        head = ""
        reserva = ""
        for tentativa in range(len(ang.headlines)):
            cand = _pick(ang.headlines, cycle + tentativa, off).format(tema=tema)
            if cand.lower() in seen_head:
                continue
            reserva = reserva or cand
            # Headline de criativo é caixa curta: molde que ficou comprido depois
            # de receber o {tema} perde para o próximo do ângulo.
            if len(cand) <= MAX_HEADLINE_CHARS:
                head = cand
                break
        head = head or reserva
        if not head:
            # Todos os moldes do ângulo já saíram: desempata com o número do ciclo.
            head = f"{_pick(ang.headlines, cycle, off).format(tema=tema)} ({cycle + 1})"
        seen_head.add(head.lower())

        sub = _pick(ang.subheads, cycle, off).format(tema=tema)
        # A cada 3 variações reaproveitamos um CTA real da marca: nada é mais
        # fiel ao tom do cliente do que o CTA que ele já usa.
        if ref_ctas and i % 3 == 0:
            cta = ref_ctas[(i // 3) % len(ref_ctas)]
        else:
            cta = _pick(ang.ctas, cycle, off).format(tema=tema)

        out.append({
            "angle": ang.slug,
            "angle_label": ang.label,
            "headline": head.upper() if upper_head else head,
            "subhead": sub,
            "cta": cta.upper() if upper_cta else cta,
            "source": "offline",
        })
    return out


# --------------------------------------------------------------------------- #
# Copy com IA (modelo de texto — barato, sem imagem)
# --------------------------------------------------------------------------- #
_COPY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "variacoes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "angulo": {"type": "string"},
                    "headline": {"type": "string"},
                    "subhead": {"type": "string"},
                    "cta": {"type": "string"},
                },
                "required": ["angulo", "headline", "subhead", "cta"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["variacoes"],
    "additionalProperties": False,
}


def _openai_client(settings: Settings) -> Any:
    """Cliente da OpenAI. Import tardio: importar este módulo não paga o preço."""
    from openai import OpenAI  # import local de propósito

    return OpenAI(api_key=settings.openai_api_key, max_retries=2, timeout=90.0)


def _parse_json_object(text: str) -> dict[str, Any]:
    """Maior objeto JSON dentro do texto (modelos às vezes cercam com prosa)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t.split("\n", 1)[1] if "\n" in t else t
    try:
        val = json.loads(t)
        if isinstance(val, dict):
            return val
    except json.JSONDecodeError:
        pass
    depth, start, best = 0, -1, {}
    in_str = esc = False
    for i, ch in enumerate(t):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    cand = json.loads(t[start:i + 1])
                except json.JSONDecodeError:
                    cand = None
                if isinstance(cand, dict) and len(cand) >= len(best):
                    best = cand
                start = -1
    return best


def _chat_json(settings: Settings, messages: list[dict[str, Any]],
               max_tokens: int = 2000) -> dict[str, Any]:
    """Pede JSON ao modelo de texto degradando o mecanismo de formato.

    Ordem: ``json_schema`` estrito -> ``json_object`` -> texto puro. Assim o
    módulo continua funcionando se ``vision_model`` apontar para um modelo
    antigo que não conhece structured outputs.
    """
    client = _openai_client(settings)
    variants: list[dict[str, Any]] = [
        {"response_format": {"type": "json_schema",
                             "json_schema": {"name": "copy_variations", "strict": True,
                                             "schema": _COPY_SCHEMA}},
         "temperature": 0.9},
        {"response_format": {"type": "json_object"}, "temperature": 0.9},
        {"response_format": {"type": "json_object"}},
        {},
    ]
    last: Exception | None = None
    for extra in variants:
        for token_key in ("max_tokens", "max_completion_tokens"):
            kw = dict(extra)
            kw[token_key] = max_tokens
            try:
                resp = client.chat.completions.create(
                    model=settings.vision_model, messages=messages, **kw)
            except Exception as exc:  # noqa: BLE001 - degradamos de propósito
                last = exc
                continue
            data = _parse_json_object(resp.choices[0].message.content or "")
            if data:
                return data
            last = ValueError("o modelo respondeu sem JSON utilizável")
            break
    if last is not None:
        raise last
    return {}


def copy_angles(dna: CreativeDNA, n: int,
                settings: Settings | None = None) -> list[dict[str, str]]:
    """``n`` conjuntos de copy (headline, subhead, CTA), um ângulo por conjunto.

    Cada item traz também ``angle`` (slug), ``angle_label`` (nome em português)
    e ``source`` (``"ai"`` ou ``"offline"``), porque quem entrega o lote precisa
    dizer ao cliente de onde veio cada texto.

    Sem ``OPENAI_API_KEY`` (ou se a chamada falhar, ou em ``dry_run``) o
    resultado sai do gerador determinístico montado a partir de
    ``dna.copy_patterns`` / ``dna.cta_patterns`` e dos moldes de :data:`ANGLES`.
    Nesse caminho **nada é inventado**: sem número, sem preço, sem estatística.
    """
    settings = settings or load_settings()
    n = _check_n(n)
    base = _offline_copy(dna, n)

    if not settings.openai_api_key or settings.dry_run:
        return base

    wanted = [{"angulo": c["angle"], "briefing": _ANGLE_BY_SLUG[c["angle"]].brief}
              for c in base]
    contexto = json.dumps({
        "assunto": dna.subject_matter,
        "clima": dna.mood,
        "paleta": [color_to_hex(c) for c in dna.palette],
        "layout": dna.layout_archetype,
        "headlines_de_referencia": [c for c in (dna.copy_patterns or [])][:12],
        "ctas_de_referencia": [c for c in (dna.cta_patterns or [])][:12],
        "nunca_fazer": dna.do_not,
        "angulos_pedidos": wanted,
    }, ensure_ascii=False)[:6000]

    messages = [
        {"role": "system", "content":
            "Você é redator publicitário brasileiro. Escreve copy curta para "
            "criativo de performance, em português do Brasil, no tom da marca. "
            "Nunca invente número, preço, prazo, porcentagem ou depoimento: se o "
            "briefing não traz o dado, escreva sem ele. Responda SOMENTE com JSON."},
        {"role": "user", "content":
            f"Marca e referências:\n{contexto}\n\n"
            f"Escreva {n} variações, uma para cada item de 'angulos_pedidos', na "
            "MESMA ordem. Para cada uma: 'angulo' (repita o slug recebido), "
            "'headline' (no máximo 45 caracteres), 'subhead' (no máximo 80 "
            "caracteres, pode ser vazia se a marca não usa) e 'cta' (no máximo 22 "
            "caracteres, verbo no imperativo). Nada de headline repetida. "
            "Devolva {\"variacoes\": [...]}."},
    ]

    try:
        payload = _chat_json(settings, messages, max_tokens=min(4000, 200 + 90 * n))
    except Exception as exc:  # noqa: BLE001 - a copy offline já é entregável
        _warn(f"copy por IA falhou ({type(exc).__name__}); usei a copy determinística. "
              "Rode 's7editor doctor' se isso se repetir.")
        return base

    itens = payload.get("variacoes") or payload.get("variations") or []
    if not isinstance(itens, list):
        itens = []

    out = [dict(c) for c in base]
    usados: set[str] = set()
    for i, raw in enumerate(itens[:n]):
        if not isinstance(raw, dict):
            continue
        head = str(raw.get("headline") or "").strip()
        if not head or head.lower() in usados:
            continue
        usados.add(head.lower())
        slug = str(raw.get("angulo") or out[i]["angle"]).strip().lower()
        if slug in _ANGLE_BY_SLUG:
            out[i]["angle"] = slug
            out[i]["angle_label"] = _ANGLE_BY_SLUG[slug].label
        out[i]["headline"] = head
        out[i]["subhead"] = str(raw.get("subhead") or "").strip()
        out[i]["cta"] = str(raw.get("cta") or out[i]["cta"]).strip()
        out[i]["source"] = "ai"

    faltou = sum(1 for c in out if c["source"] != "ai")
    if faltou:
        _warn(f"o modelo devolveu {n - faltou} de {n} copies; o restante veio do "
              "gerador determinístico.")
    return out


# --------------------------------------------------------------------------- #
# Prompts de fundo
# --------------------------------------------------------------------------- #
#: Variantes cicladas por índice — sem isso 30 chamadas com o mesmo prompt
#: devolvem 30 imagens quase idênticas.
_COMPOSITIONS: tuple[str, ...] = (
    "centered composition, subject filling the middle third",
    "off-center composition with generous negative space on the left",
    "off-center composition with generous negative space on the right",
    "low camera angle looking slightly up",
    "top-down flat lay composition",
    "wide establishing shot with the subject small in frame",
    "tight macro detail of the subject",
    "diagonal composition with strong leading lines",
)
_LIGHTING: tuple[str, ...] = (
    "soft diffused daylight",
    "warm golden-hour backlight with gentle lens flare",
    "hard directional studio light with crisp shadows",
    "cool overcast light, low contrast",
    "dramatic single-source rim light on a dark background",
    "bright airy high-key lighting",
)
_TREATMENT: tuple[str, ...] = (
    "clean commercial photography finish",
    "subtle film grain, analog color",
    "glossy editorial retouch",
    "matte muted color grade",
    "vivid saturated color grade",
)

_NO_TEXT = ("Absolutely no text, no letters, no numbers, no logos, no watermarks, "
            "no UI elements and no signage anywhere in the image.")


def build_background_prompt(dna: CreativeDNA, index: int, *,
                            angle: str | None = None,
                            reserve: str | None = None) -> str:
    """Prompt em inglês para o FUNDO de uma variação.

    Inglês porque é o idioma em que os modelos de imagem foram treinados e onde
    erram menos; a copy em português entra depois, desenhada por nós.

    ``reserve`` ("top", "bottom", "left"...) pede uma área limpa para o texto —
    usado pelo modo híbrido, em que a tipografia é composta por cima.
    """
    seed = _stable_seed(_dna_signature(dna))
    base = str(dna.prompt_seed or "").strip()
    if not base:
        hexes = ", ".join(color_to_hex(c) for c in (dna.palette or [])[:4])
        base = (f"Advertising creative background, {dna.aspect or '9:16'} format. "
                f"{dna.layout_archetype or 'clean modern layout'}. "
                f"{('Subject: ' + dna.subject_matter + '. ') if dna.subject_matter else ''}"
                f"{('Palette: ' + hexes + '. ') if hexes else ''}")

    partes = [base.rstrip(". ") + "."]
    if dna.mood:
        partes.append(f"Mood: {dna.mood}.")
    if angle and angle in _ANGLE_BY_SLUG:
        partes.append(f"Emotional angle: {_ANGLE_BY_SLUG[angle].brief}.")
    partes.append(
        f"Variation {index + 1}: {_pick(_COMPOSITIONS, index, seed % 5)}, "
        f"{_pick(_LIGHTING, index, seed % 3)}, {_pick(_TREATMENT, index, seed % 2)}.")
    if dna.palette:
        partes.append("Keep the brand palette: "
                      + ", ".join(color_to_hex(c) for c in dna.palette[:4]) + ".")
    if reserve:
        partes.append(f"Leave the {reserve} area visually calm and uncluttered "
                      "so headline text can be placed there later.")
    partes.append(_NO_TEXT)
    for regra in (dna.do_not or [])[:4]:
        r = str(regra).strip().rstrip(".")
        if r:
            partes.append(f"Constraint: {r}.")
    return " ".join(partes)


# --------------------------------------------------------------------------- #
# Layout do modo híbrido
# --------------------------------------------------------------------------- #
#: Caixas normalizadas por orientação: headline, subhead e CTA.
_LAYOUTS: dict[str, dict[str, tuple[float, float, float, float]]] = {
    "portrait": {
        "headline": (0.08, 0.09, 0.84, 0.19),
        "subhead": (0.10, 0.30, 0.80, 0.09),
        "cta": (0.20, 0.795, 0.60, 0.075),
    },
    "square": {
        "headline": (0.08, 0.11, 0.84, 0.21),
        "subhead": (0.10, 0.35, 0.80, 0.10),
        "cta": (0.24, 0.775, 0.52, 0.095),
    },
    "landscape": {
        "headline": (0.06, 0.13, 0.54, 0.25),
        "subhead": (0.06, 0.42, 0.48, 0.11),
        "cta": (0.06, 0.665, 0.30, 0.12),
    },
}

_RESERVE = {"portrait": "top and bottom", "square": "top", "landscape": "left"}


def _orientation(w: int, h: int) -> str:
    r = w / max(h, 1)
    if r < 0.92:
        return "portrait"
    if r > 1.20:
        return "landscape"
    return "square"


def layout_for(width: int, height: int) -> dict[str, Box]:
    """Caixas de headline/subhead/CTA para uma tela ``width`` x ``height``.

    São proporções de segurança (nada encosta a menos de 6% da borda), pensadas
    para feed e stories. O modo ``template`` NÃO usa isto — lá as caixas vêm dos
    criativos reais, que é o que preserva o layout da marca.
    """
    kind = _orientation(width, height)
    return {k: Box.from_norm(*v, width, height) for k, v in _LAYOUTS[kind].items()}


def _luma(rgb: Sequence[int]) -> float:
    r, g, b = (float(v) for v in list(rgb)[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _accent(dna: CreativeDNA) -> tuple[int, int, int]:
    """Cor de destaque da marca: a mais saturada da paleta, sem ser quase preta/branca."""
    best: tuple[int, int, int] | None = None
    best_score = -1.0
    for c in dna.palette or []:
        r, g, b = (int(v) for v in c[:3])
        sat = max(r, g, b) - min(r, g, b)
        lum = _luma((r, g, b))
        if lum < 18 or lum > 240:
            continue
        score = sat + 0.15 * min(lum, 255 - lum)
        if score > best_score:
            best, best_score = (r, g, b), score
    return best or (17, 17, 17)


def _contrast_on(bg: Sequence[int]) -> tuple[int, int, int]:
    return (17, 17, 17) if _luma(bg) > 140 else (255, 255, 255)


def _family(dna: CreativeDNA) -> str:
    for f in dna.fonts or []:
        if str(f).strip():
            return str(f).strip()
    return "Inter"


def _apply_copy_layer(img: Image.Image, dna: CreativeDNA, copy: dict[str, str],
                      warns: list[str]) -> tuple[Image.Image, list[Box]]:
    """Escreve headline/subhead/CTA por cima de um fundo, de forma determinística.

    É este passo que resolve o defeito clássico da IA generativa: texto
    renderizado pelo modelo sai com letra trocada, palavra inventada e acento
    errado. Aqui a tipografia é desenhada com PIL, então a copy sai exatamente
    como foi escrita.
    """
    boxes = layout_for(img.width, img.height)
    fam = _family(dna)
    upper_head = _mostly_upper([c for c in (dna.copy_patterns or []) if _looks_like_copy(c)])
    accent = _accent(dna)
    out = img
    changed: list[Box] = []

    for key in ("headline", "subhead"):
        text = str(copy.get(key) or "").strip()
        if not text:
            continue
        b = boxes[key]
        bg = _io.average_color(out, b)
        spec = FontSpec(
            family=fam,
            weight="bold" if key == "headline" else "medium",
            size_px=max(12, int(b.h * (0.42 if key == "headline" else 0.62))),
            color=_contrast_on(bg),
            align="center" if _orientation(out.width, out.height) != "landscape" else "left",
            valign="middle",
            uppercase=upper_head and key == "headline",
            line_height=1.15,
            shadow=True,          # fundo é foto: sombra garante leitura
            shadow_color=(0, 0, 0),
            shadow_offset=(0, max(2, b.h // 26)),
            shadow_blur=max(3, b.h // 14),
        )
        rep: dict[str, Any] = {}
        out, ch = _textedit.add_text(out, b, text, spec, autofit=True, report=rep)
        for w in rep.get("warnings", []):
            if w not in warns:
                warns.append(w)
        if ch.area:
            changed.append(ch)

    cta = str(copy.get("cta") or "").strip()
    if cta:
        b = boxes["cta"]
        # `add_text` já devolve cópia; se nenhum texto foi desenhado ainda, copiamos
        # aqui — este módulo nunca muta a imagem que recebeu.
        out = out.copy() if out is img else out
        ImageDraw.Draw(out).rounded_rectangle(
            [b.x, b.y, b.x1 - 1, b.y1 - 1], radius=max(2, b.h // 2), fill=accent)
        inner = Box(b.x + int(b.h * 0.35), b.y + int(b.h * 0.16),
                    max(1, b.w - int(b.h * 0.70)), max(1, b.h - int(b.h * 0.32)))
        spec = FontSpec(family=fam, weight="bold",
                        size_px=max(10, int(inner.h * 0.80)),
                        color=_contrast_on(accent), align="center", valign="middle",
                        uppercase=True, letter_spacing=max(0.0, inner.h * 0.02))
        rep = {}
        out, ch = _textedit.add_text(out, inner, cta, spec, autofit=True, report=rep)
        for w in rep.get("warnings", []):
            if w not in warns:
                warns.append(w)
        changed.append(b)

    return out, changed


# --------------------------------------------------------------------------- #
# Preparação comum
# --------------------------------------------------------------------------- #
def _check_n(n: Any) -> int:
    try:
        n = int(n)
    except (TypeError, ValueError):
        raise ValueError(f"quantidade inválida: {n!r}. Informe um número inteiro, ex.: 30.") from None
    if n < 1:
        raise ValueError("a quantidade de variações precisa ser pelo menos 1.")
    if n > MAX_VARIATIONS:
        raise ValueError(
            f"você pediu {n} variações e o limite de segurança é {MAX_VARIATIONS}.\n"
            "  Um lote maior que isso costuma ser engano (e, no modo generativo, "
            "custa caro).\n"
            "  Rode em lotes menores ou ajuste variations.MAX_VARIATIONS."
        )
    return n


def _normalize_mode(mode: Any) -> str:
    key = _strip_accents(str(mode or "generative").strip().lower())
    canon = _MODE_ALIASES.get(key) or _MODE_ALIASES.get(str(mode or "").strip().lower())
    if not canon:
        raise ValueError(
            f"modo de variação desconhecido: {mode!r}.\n"
            f"  Use um destes: {', '.join(MODES)}.\n"
            "    template   = troca só os textos em cima dos seus criativos (recomendado)\n"
            "    hybrid     = fundo gerado por IA + texto escrito por nós\n"
            "    generative = imagem inteira pela IA"
        )
    return canon


def _normalize_copy(raw: Any, fallback: dict[str, str]) -> dict[str, str]:
    if isinstance(raw, str):
        item = dict(fallback)
        item["headline"] = raw.strip()
        item["source"] = "manual"
        return item
    if not isinstance(raw, dict):
        return dict(fallback)
    item = dict(fallback)
    for k in _COPY_KEYS:
        if k in raw and raw[k] is not None:
            item[k] = str(raw[k]).strip()
    slug = str(raw.get("angle") or raw.get("angulo") or item.get("angle") or "").lower()
    if slug in _ANGLE_BY_SLUG:
        item["angle"] = slug
        item["angle_label"] = _ANGLE_BY_SLUG[slug].label
    item["source"] = str(raw.get("source") or "manual")
    return item


def _prepare_copies(dna: CreativeDNA, n: int, settings: Settings,
                    copy_variants: Sequence[Any] | None) -> list[dict[str, str]]:
    base = _offline_copy(dna, n)
    if copy_variants is None:
        return copy_angles(dna, n, settings)
    seq = list(copy_variants)
    if not seq:
        raise ValueError(
            "copy_variants veio vazio. Passe pelo menos um conjunto de textos "
            "({'headline': ..., 'cta': ...}) ou deixe como None para eu escrever."
        )
    if len(seq) < n:
        _warn(f"recebi {len(seq)} conjuntos de copy para {n} variações; vou ciclar os textos.")
    return [_normalize_copy(seq[i % len(seq)], base[i]) for i in range(n)]


def _resolve_target(aspect: Any, dna: CreativeDNA) -> tuple[int, int]:
    spec: AspectSpec
    if isinstance(aspect, AspectSpec):
        spec = aspect
    else:
        raw = str(aspect or dna.aspect or "9:16")
        try:
            spec = AspectSpec.parse(raw)
        except ValueError as exc:
            raise ValueError(
                f"formato de saída inválido: {raw!r}.\n"
                "  Use '9:16', '16:9', '1080x1920' ou '9:16@1080'."
            ) from exc
    return spec.resolve(long_edge=1440)


# --------------------------------------------------------------------------- #
# Bases do modo template
# --------------------------------------------------------------------------- #
def _load_base(item: Any, settings: Settings) -> tuple[Image.Image, CreativeAnalysis]:
    """Normaliza uma entrada de ``base_images`` para ``(imagem, análise)``.

    Aceita caminho, ``PIL.Image``, ``CreativeAnalysis`` ou a tupla
    ``(imagem, análise)``. Imagem solta é gravada no cache e analisada de lá —
    ``vision.analyze_creative`` trabalha com arquivo, e assim o cache de análise
    continua valendo entre execuções.
    """
    if isinstance(item, (tuple, list)) and len(item) == 2:
        img, analysis = item
        if isinstance(img, Image.Image) and isinstance(analysis, CreativeAnalysis):
            return img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img, analysis
    if isinstance(item, CreativeAnalysis):
        return _io.load_image(item.path), item
    if isinstance(item, Image.Image):
        cache = Path(settings.cache_dir) / "variations_base"
        cache.mkdir(parents=True, exist_ok=True)
        path = cache / f"{_io.image_sha(item)[:16]}.png"
        if not path.exists():
            _io.save_image(item, path, fmt="PNG")
        return _io.load_image(path), _vision.analyze_creative(path, settings)
    if isinstance(item, (str, Path)):
        path = Path(item)
        if not path.exists():
            raise FileNotFoundError(
                f"criativo de base não encontrado: {path}\n"
                "  Confira o caminho ou a pasta passada em --base."
            )
        return _io.load_image(path), _vision.analyze_creative(path, settings)
    raise TypeError(
        f"item de base_images inválido: {type(item).__name__}.\n"
        "  Aceito: caminho de arquivo, PIL.Image, CreativeAnalysis ou (imagem, análise)."
    )


class _BasePool:
    """Bases carregadas sob demanda — não analisa 30 imagens para gerar 3."""

    def __init__(self, items: Sequence[Any], settings: Settings) -> None:
        self._items = list(items)
        self._settings = settings
        self._cache: dict[int, tuple[Image.Image, CreativeAnalysis]] = {}

    def __len__(self) -> int:
        return len(self._items)

    def get(self, index: int) -> tuple[Image.Image, CreativeAnalysis]:
        i = index % len(self._items)
        if i not in self._cache:
            self._cache[i] = _load_base(self._items[i], self._settings)
        return self._cache[i]


# --------------------------------------------------------------------------- #
# Modos
# --------------------------------------------------------------------------- #
def _meta(index: int, mode: str, copy: dict[str, str], **extra: Any) -> dict[str, Any]:
    slug = copy.get("angle") or "outro"
    d: dict[str, Any] = {
        "index": index,
        "mode": mode,
        "angle": slug,
        "angle_label": copy.get("angle_label") or slug,
        "copy": {k: copy.get(k, "") for k in _COPY_KEYS},
        "copy_source": copy.get("source", "offline"),
        "prompt": "",
        "engine": "deterministic",
        "cost_usd": 0.0,
        "base": None,
        "size": "",
        "changed_boxes": [],
        "drift_pixels": None,
        "untouched_pixels_verified": None,
        "warnings": [],
        "suggested_name": f"var_{index + 1:02d}_{slug}.png",
    }
    d.update(extra)
    return d


def _run_template(dna: CreativeDNA, n: int, copies: list[dict[str, str]],
                  settings: Settings, base_images: Sequence[Any] | None,
                  target: tuple[int, int] | None,
                  progress: Callable[[int, int, str], None] | None,
                  ) -> list[tuple[Image.Image, dict[str, Any]]]:
    if not base_images:
        raise ValueError(
            "o modo 'template' precisa de criativos de base — é neles que os "
            "textos são trocados.\n"
            "  Passe base_images=[...] (a mesma pasta de referências serve) ou "
            "use mode='hybrid' / 'generative' para gerar do zero."
        )
    pool = _BasePool(base_images, settings)
    if n > len(pool):
        log.info("ciclando %d base(s) para produzir %d variações", len(pool), n)

    out: list[tuple[Image.Image, dict[str, Any]]] = []
    last_exc: Exception | None = None
    for i in range(n):
        copy = copies[i]
        _tick(progress, i + 1, n, f"variação {i + 1}/{n} — {copy.get('angle_label', '')}")
        warns: list[str] = []
        try:
            base_img, analysis = pool.get(i)
        except Exception as exc:  # noqa: BLE001 - uma base ruim não derruba o lote
            last_exc = exc
            _warn(f"variação {i + 1}: base inválida ({exc})")
            continue

        original = base_img
        img = base_img
        changed: list[Box] = []
        aplicados: list[str] = []
        for key in _COPY_KEYS:
            text = str(copy.get(key) or "").strip()
            if not text:
                continue
            block = _vision.find_text_block(analysis, role=ROLE_OF_KEY[key])
            if block is None:
                warns.append(f"a base não tem bloco de {key}; esse texto foi ignorado")
                continue
            rep: dict[str, Any] = {}
            try:
                img, ch = _textedit.replace_text(img, block, text, settings=settings,
                                                 report=rep)
            except Exception as exc:  # noqa: BLE001
                warns.append(f"falha ao trocar o {key}: {exc}")
                continue
            for w in rep.get("warnings", []):
                if w not in warns:
                    warns.append(w)
            if ch.area:
                changed.append(ch)
            aplicados.append(key)

        if not aplicados:
            warns.append("nenhum texto foi trocado: a variação é uma cópia da base")

        # Prova da garantia de zero drift: fora das caixas alteradas, a imagem
        # tem que ser byte a byte igual à base.
        drift, bbox = (0, None)
        if changed:
            drift, bbox = _protect.drift_report(original, img, changed)
            if drift:
                warns.append(f"ATENÇÃO: {drift} pixels mudaram fora das caixas "
                             f"(maior mancha em {bbox.to_dict() if bbox else '?'})")
                _warn(f"variação {i + 1}: drift de {drift} pixels no modo template")

        if target and (img.width, img.height) != target:
            warns.append(
                f"a base é {img.width}x{img.height} e você pediu {target[0]}x{target[1]}; "
                "no modo template eu não reenquadro (isso mudaria o layout da marca) — "
                "rode 's7editor reframe' depois."
            )

        meta = _meta(i, "template", copy,
                     engine="deterministic",
                     base=str(getattr(analysis, "path", "") or ""),
                     size=f"{img.width}x{img.height}",
                     changed_boxes=[b.to_dict() for b in changed],
                     drift_pixels=int(drift),
                     untouched_pixels_verified=(drift == 0) if changed else None,
                     applied=aplicados,
                     warnings=warns)
        out.append((img, meta))

    if not out and last_exc is not None:
        # Nenhuma base pôde ser lida: silêncio aqui viraria "rodou e não gerou nada".
        raise last_exc
    return out


def _generate_background(dna: CreativeDNA, index: int, copy: dict[str, str],
                         settings: Settings, target: tuple[int, int],
                         *, reserve: str | None) -> tuple[Image.Image, dict[str, Any]]:
    """Uma imagem de fundo pela API, já ajustada ao tamanho alvo."""
    tw, th = target
    prompt = build_background_prompt(dna, index, angle=copy.get("angle"), reserve=reserve)
    size = _aigen.pick_api_size(settings.image_model, tw, th)
    imgs = _aigen.generate(prompt, settings=settings, size=size, n=1)
    if not imgs:
        raise _aigen.ImageAPIError("a API não devolveu nenhuma imagem.")
    img = imgs[0]

    warns: list[str] = []
    if (img.width, img.height) != (tw, th):
        ra, rb = img.width / max(img.height, 1), tw / max(th, 1)
        if abs(ra - rb) / max(rb, 1e-6) > 0.08:
            warns.append(
                f"o modelo só gera {size}; recortei para {tw}x{th} (cover). "
                "Para preservar todo o enquadramento, gere no formato nativo e "
                "use 's7editor reframe --mode outpaint'."
            )
        img = _io.resize_cover(img, tw, th)

    cost = 0.0 if settings.dry_run else _aigen.estimate_cost(
        settings.image_model, size, settings.quality, 1)
    return img, {"prompt": prompt, "api_size": size, "cost_usd": float(cost),
                 "warnings": warns}


def _run_ai(dna: CreativeDNA, n: int, copies: list[dict[str, str]], settings: Settings,
            target: tuple[int, int], mode: str,
            progress: Callable[[int, int, str], None] | None,
            ) -> list[tuple[Image.Image, dict[str, Any]]]:
    if not settings.dry_run:
        require_openai(settings)      # erro em português explicando como configurar

    reserve = _RESERVE[_orientation(*target)] if mode == "hybrid" else None
    out: list[tuple[Image.Image, dict[str, Any]]] = []
    last_exc: Exception | None = None

    for i in range(n):
        copy = copies[i]
        _tick(progress, i + 1, n,
              f"variação {i + 1}/{n} — {copy.get('angle_label', '')} (IA)")
        try:
            img, info = _generate_background(dna, i, copy, settings, target,
                                             reserve=reserve)
        except Exception as exc:  # noqa: BLE001 - uma falha não derruba as outras
            last_exc = exc
            _warn(f"variação {i + 1} falhou na geração: {exc}")
            continue

        warns = list(info["warnings"])
        changed: list[Box] = []
        if mode == "hybrid":
            img, changed = _apply_copy_layer(img, dna, copy, warns)

        meta = _meta(i, mode, copy,
                     engine="ai" if mode == "generative" else "ai+deterministic",
                     prompt=info["prompt"],
                     cost_usd=info["cost_usd"],
                     size=f"{img.width}x{img.height}",
                     api_size=info["api_size"],
                     changed_boxes=[b.to_dict() for b in changed],
                     warnings=warns)
        if mode == "generative":
            meta["warnings"].append(
                "modo generativo: qualquer texto que a IA tenha desenhado pode "
                "conter erro de ortografia — revise antes de publicar.")
        out.append((img, meta))

    if not out and last_exc is not None:
        raise last_exc
    return out


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def generate_variations(dna: CreativeDNA, n: int, *,
                        settings: Settings | None = None,
                        mode: str = "generative",
                        base_images: Sequence[Any] | None = None,
                        copy_variants: Sequence[Any] | None = None,
                        aspect: Any = None,
                        progress: Callable[[int, int, str], None] | None = None,
                        ) -> list[tuple[Image.Image, dict[str, Any]]]:
    """Produz ``n`` criativos novos no padrão do ``dna``.

    Modos
    -----
    ``template`` (recomendado quando existem referências)
        Usa os criativos de ``base_images`` e troca **apenas** os textos com
        :func:`textedit.replace_text`, ciclando as bases quando ``n`` é maior
        que a quantidade delas. Consistência de marca perfeita, custo zero e
        drift zero — o resultado é conferido com :func:`protect.drift_report` e
        o número vai em ``meta["drift_pixels"]``.

    ``hybrid``
        Gera o **fundo** com ``gpt-image-1`` e escreve headline/subhead/CTA por
        cima com PIL. É o caminho recomendado quando não há base: junta a
        variedade da IA com texto que sai escrito certo.

    ``generative``
        Deixa a imagem inteira por conta da IA. **Aviso:** modelos de imagem
        erram ortografia com frequência — trocam letra, inventam palavra, comem
        acento — e o defeito só aparece quando o cliente lê a peça. Por isso o
        padrão recomendado é gerar o FUNDO pela IA e escrever o texto por cima
        deterministicamente, que é exatamente o modo ``hybrid``.

    Parâmetros
    ----------
    copy_variants
        Textos prontos (lista de ``{"headline", "subhead", "cta"}``). Quando
        ``None``, :func:`copy_angles` escreve. Se vierem menos que ``n``, são
        ciclados.
    aspect
        ``"9:16"``, ``"1080x1920"``, ``AspectSpec`` ou ``None`` (usa
        ``dna.aspect``). Ignorado no modo ``template``, onde o tamanho é o da
        base — reenquadrar ali mudaria o layout da marca; use o comando
        ``reframe`` para isso.
    progress
        ``progress(i, total, msg)`` chamado antes de cada item, com ``i``
        começando em 1. Exceções no callback são engolidas de propósito.

    Devolve
    -------
    Lista de ``(imagem, metadados)``. Os metadados trazem ``angle``, ``copy``,
    ``prompt``, ``mode``, ``engine``, ``cost_usd``, ``changed_boxes``,
    ``drift_pixels`` e ``warnings``. Itens que falharam na IA são **omitidos**
    (com aviso em :func:`variation_warnings`); se todos falharem, o erro
    original é levantado.
    """
    settings = settings or load_settings()
    n = _check_n(n)
    canon = _normalize_mode(mode)
    dna = dna if isinstance(dna, CreativeDNA) else CreativeDNA()

    copies = _prepare_copies(dna, n, settings, copy_variants)

    if canon == "template":
        target = _resolve_target(aspect, dna) if aspect is not None else None
        return _run_template(dna, n, copies, settings, base_images, target, progress)

    if base_images and canon == "generative":
        _warn("base_images foi ignorado no modo 'generative'. Para aproveitar seus "
              "criativos reais use mode='template'.")

    target = _resolve_target(aspect, dna)
    return _run_ai(dna, n, copies, settings, target, canon, progress)


# --------------------------------------------------------------------------- #
# Teste de fumaça (offline): python -m s7editor.variations
# --------------------------------------------------------------------------- #
def _demo_dna() -> CreativeDNA:
    return CreativeDNA(
        palette=[(14, 30, 92), (240, 92, 30), (250, 250, 248), (30, 30, 30)],
        fonts=["Inter"],
        layout_archetype="foto full-bleed com faixa inferior",
        subject_matter="curso online de finanças pessoais",
        mood="confiante, direto",
        copy_patterns=["ORGANIZE SUAS FINANÇAS", "SAIA DO VERMELHO"],
        cta_patterns=["QUERO COMEÇAR", "SAIBA MAIS"],
        aspect="9:16",
        sample_count=6,
    )


def _demo_base(w: int = 720, h: int = 1280) -> tuple[Image.Image, CreativeAnalysis]:
    """Criativo sintético: bloco de foto falsa, faixa chapada e CTA em pastilha."""
    from .models import TextBlock

    img = Image.new("RGB", (w, h), (14, 30, 92))
    d = ImageDraw.Draw(img)
    for y in range(0, int(h * 0.55)):
        t = y / (h * 0.55)
        d.line([(0, y), (w, y)], fill=(int(20 + 60 * t), int(40 + 40 * t), int(110 - 30 * t)))
    d.rectangle([0, int(h * 0.55), w, h], fill=(250, 250, 248))

    head_box = Box(int(w * 0.08), int(h * 0.60), int(w * 0.84), int(h * 0.10))
    cta_box = Box(int(w * 0.20), int(h * 0.80), int(w * 0.60), int(h * 0.07))
    d.rectangle(list(cta_box.xyxy), fill=(240, 92, 30))

    head_spec = FontSpec(family="Inter", weight="bold", size_px=int(h * 0.055),
                         color=(14, 30, 92), align="center", valign="middle")
    cta_spec = FontSpec(family="Inter", weight="bold", size_px=int(h * 0.035),
                        color=(255, 255, 255), align="center", valign="middle",
                        uppercase=True)
    img, _ = _textedit.add_text(img, head_box, "ORGANIZE SUAS FINANÇAS", head_spec)
    img, _ = _textedit.add_text(img, cta_box, "QUERO COMEÇAR", cta_spec)

    analysis = CreativeAnalysis(
        path=Path("<demo>"), width=w, height=h, source="manual",
        background_kind=BackgroundKind.SOLID,
        text_blocks=[
            TextBlock(box=head_box, text="ORGANIZE SUAS FINANÇAS",
                      role=TextRole.HEADLINE, style=head_spec,
                      background_color=(250, 250, 248), on_solid_background=True,
                      confidence=1.0),
            TextBlock(box=cta_box, text="QUERO COMEÇAR", role=TextRole.CTA,
                      style=cta_spec, background_color=(240, 92, 30),
                      on_solid_background=True, confidence=1.0),
        ],
        palette=[(14, 30, 92), (240, 92, 30), (250, 250, 248)],
    )
    return img, analysis


def _smoke_test() -> int:  # pragma: no cover - roda na mão
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    settings = load_settings(dry_run=True)
    dna = _demo_dna()
    falhas = 0

    # 1) copy determinística e reprodutível
    a = copy_angles(dna, 5, settings)
    b = copy_angles(dna, 5, settings)
    print(f"copy_angles: {len(a)} conjuntos, reprodutível={a == b}")
    for c in a[:3]:
        print(f"  [{c['angle']}] {c['headline']!r} / {c['subhead']!r} / {c['cta']!r}")
    if a != b or len(a) != 5:
        falhas += 1
        print("  FALHA: copy não reprodutível")

    # 2) template: troca de texto com drift zero
    base = _demo_base()
    outs = generate_variations(dna, 4, settings=settings, mode="template",
                               base_images=[base],
                               progress=lambda i, t, m: None)
    print(f"template: {len(outs)} variações")
    for img, meta in outs:
        print(f"  #{meta['index']} {meta['angle']:<14} drift={meta['drift_pixels']} "
              f"boxes={len(meta['changed_boxes'])} {img.size}")
        if meta["drift_pixels"]:
            falhas += 1
            print("  FALHA: drift fora das caixas")
    if len(outs) != 4:
        falhas += 1
        print("  FALHA: contagem de variações no modo template")

    # 3) híbrido e generativo em dry-run (placeholders, sem rede)
    for mode in ("hybrid", "generative"):
        outs = generate_variations(dna, 2, settings=settings, mode=mode,
                                   aspect="9:16@720")
        print(f"{mode}: {len(outs)} variações {outs[0][0].size if outs else '-'} "
              f"custo={sum(m['cost_usd'] for _, m in outs):.3f}")
        if len(outs) != 2 or outs[0][0].size != (720, 1280):
            falhas += 1
            print(f"  FALHA: saída inesperada no modo {mode}")
        if not outs[0][1]["prompt"]:
            falhas += 1
            print(f"  FALHA: prompt vazio no modo {mode}")

    # 4) erros do usuário viram mensagem, não traceback
    for chamada, rotulo in (
        (lambda: generate_variations(dna, 2, settings=settings, mode="xpto"), "modo inválido"),
        (lambda: generate_variations(dna, 2, settings=settings, mode="template"), "template sem base"),
        (lambda: generate_variations(dna, 0, settings=settings), "n = 0"),
    ):
        try:
            chamada()
        except ValueError as exc:
            print(f"erro tratado ({rotulo}): {str(exc).splitlines()[0]}")
        else:
            falhas += 1
            print(f"  FALHA: {rotulo} não levantou ValueError")

    if variation_warnings():
        print("avisos:", "; ".join(variation_warnings()[:4]))
    print("OK" if not falhas else f"{falhas} FALHA(S)")
    return 1 if falhas else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_smoke_test())
