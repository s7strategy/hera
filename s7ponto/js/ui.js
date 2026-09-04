/* ==========================================================================
   S7 PONTO — peças de interface: ícones, torradas, folhas, confirmações.
   ========================================================================== */
import { esc } from './util.js';

/* ---------- ícones (traço, 24x24) ---------------------------------------- */

const svg = (d, extra = '') =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false" ${extra}>${d}</svg>`;

export const ICONE = {
  play:    svg('<polygon points="6 4 20 12 6 20 6 4" fill="currentColor" stroke="none"/>'),
  parar:   svg('<rect x="6" y="6" width="12" height="12" rx="2.5" fill="currentColor" stroke="none"/>'),
  trocar:  svg('<path d="M17 2l4 4-4 4"/><path d="M3 6h18"/><path d="M7 22l-4-4 4-4"/><path d="M21 18H3"/>'),
  relogio: svg('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>'),
  grafico: svg('<path d="M3 3v17a1 1 0 0 0 1 1h17"/><path d="M7 15l3.5-4 3 2.5L18 8"/>'),
  engrenagem: svg('<circle cx="12" cy="12" r="3.2"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 9 19.4a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 4.6 9a1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>'),
  sair:    svg('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>'),
  esquerda: svg('<path d="M15 18l-6-6 6-6"/>'),
  direita:  svg('<path d="M9 18l6-6-6-6"/>'),
  mais:    svg('<path d="M12 5v14"/><path d="M5 12h14"/>'),
  lapis:   svg('<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>'),
  lixo:    svg('<path d="M3 6h18"/><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>'),
  planilha: svg('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h5"/>'),
  gente:   svg('<path d="M17 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9.5" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9"/>'),
  predio:  svg('<path d="M4 21V6a2 2 0 0 1 2-2h5v17"/><path d="M11 21h9V9a2 2 0 0 0-2-2h-7"/><path d="M7 8h1"/><path d="M7 12h1"/><path d="M7 16h1"/><path d="M15 12h1"/><path d="M15 16h1"/>'),
  etiqueta: svg('<path d="M20.6 13.6L12 22l-9-9V4a1 1 0 0 1 1-1h9z"/><circle cx="7.5" cy="7.5" r="1.4" fill="currentColor"/>'),
  baixar:  svg('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>'),
  fecha:   svg('<path d="M18 6L6 18"/><path d="M6 6l12 12"/>'),
  check:   svg('<path d="M20 6L9 17l-5-5"/>'),
  aviso:   svg('<path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>'),
  seta:    svg('<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>'),
  cima:    svg('<path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>'),
  baixo:   svg('<path d="M12 5v14"/><path d="M19 12l-7 7-7-7"/>'),
  pagar:   svg('<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.6"/><path d="M6 12h.01"/><path d="M18 12h.01"/>'),
  sol:     svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="M4.9 4.9l1.4 1.4"/><path d="M17.7 17.7l1.4 1.4"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="M4.9 19.1l1.4-1.4"/><path d="M17.7 6.3l1.4-1.4"/>'),
  lua:     svg('<path d="M21 14.5A8.5 8.5 0 1 1 9.5 3 7 7 0 0 0 21 14.5z"/>'),
};

/* ---------- DOM ---------------------------------------------------------- */

export const $  = (sel, raiz = document) => raiz.querySelector(sel);
export const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

export function el(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

/** Liga cliques por data-acao, num só ouvinte. */
export function ligaAcoes(raiz, mapa) {
  raiz.addEventListener('click', (ev) => {
    const alvo = ev.target.closest('[data-acao]');
    if (!alvo || !raiz.contains(alvo)) return;
    const fn = mapa[alvo.dataset.acao];
    if (fn) { ev.preventDefault(); fn(alvo, ev); }
  });
}

/* ---------- torradas ----------------------------------------------------- */

let bandeja = null;
function pegaBandeja() {
  if (!bandeja || !document.body.contains(bandeja)) {
    bandeja = el('<div class="torradeira" role="status" aria-live="polite"></div>');
    document.body.appendChild(bandeja);
  }
  return bandeja;
}

export function torrada(texto, tipo = 'info', segundos = 4) {
  const emoji = { bom: '✅', ruim: '⚠️', info: '💡', lembrete: '🔔' }[tipo] || '💡';
  const t = el(`<div class="torrada ${esc(tipo)}"><span class="torrada-emoji">${emoji}</span><span>${esc(texto)}</span></div>`);
  pegaBandeja().appendChild(t);
  const sai = () => {
    t.classList.add('saindo');
    setTimeout(() => t.remove(), 260);
  };
  const relogio = setTimeout(sai, segundos * 1000);
  t.addEventListener('click', () => { clearTimeout(relogio); sai(); });
  return sai;
}

/* ---------- folhas ------------------------------------------------------- */

let folhaAberta = null;

/**
 * Abre uma folha por cima da tela.
 * corpo: HTML. aoMontar(caixa, fechar) recebe o elemento já no DOM.
 */
export function abreFolha({ titulo, sub = '', corpo = '', aoMontar = null, aoFechar = null }) {
  fechaFolha();
  const fundo = el(`
    <div class="folha-fundo" role="dialog" aria-modal="true" aria-label="${esc(titulo)}">
      <div class="folha">
        <div class="folha-alca"></div>
        <h2 class="folha-titulo">${esc(titulo)}</h2>
        ${sub ? `<p class="folha-sub">${esc(sub)}</p>` : ''}
        <div class="folha-corpo"></div>
      </div>
    </div>`);
  const caixa = $('.folha-corpo', fundo);
  caixa.innerHTML = corpo;

  const fechar = (motivo) => {
    if (folhaAberta !== fundo) return;
    folhaAberta = null;
    fundo.remove();
    document.body.style.overflow = '';
    document.removeEventListener('keydown', naTecla);
    aoFechar?.(motivo);
  };
  const naTecla = (ev) => {
    if (ev.key === 'Escape') fechar('escape');
  };

  fundo.addEventListener('click', (ev) => { if (ev.target === fundo) fechar('fora'); });
  document.addEventListener('keydown', naTecla);
  document.body.appendChild(fundo);
  document.body.style.overflow = 'hidden';
  folhaAberta = fundo;

  aoMontar?.(caixa, fechar);
  // foco no primeiro campo, sem roubar a tela no celular
  const primeiro = $('input:not([type=hidden]), select, textarea, button', caixa);
  if (primeiro && window.matchMedia('(min-width: 620px)').matches) primeiro.focus();
  return fechar;
}

export function fechaFolha() {
  if (folhaAberta) {
    folhaAberta.remove();
    folhaAberta = null;
    document.body.style.overflow = '';
  }
}

/** Confirmação grande e sem susto. Resolve true/false. */
export function confirma({ titulo, texto = '', ok = 'Confirmar', cancelar = 'Voltar', perigo = false }) {
  return new Promise((resolve) => {
    let decidido = false;
    const fechar = abreFolha({
      titulo, sub: texto,
      corpo: `
        <div class="linha-botoes" style="margin-top:6px">
          <button class="btn btn-medio btn-fantasma" data-r="0">${esc(cancelar)}</button>
          <button class="btn btn-medio ${perigo ? 'btn-perigo' : 'btn-primario'}" data-r="1">${esc(ok)}</button>
        </div>`,
      aoMontar: (caixa) => {
        $$('[data-r]', caixa).forEach((b) => b.addEventListener('click', () => {
          decidido = true;
          resolve(b.dataset.r === '1');
          fechar('botao');
        }));
      },
      aoFechar: () => { if (!decidido) resolve(false); },
    });
  });
}

/* ---------- estados de tela ---------------------------------------------- */

export const carregando = (texto = 'Carregando…') =>
  `<div class="carregando"><div class="giro"></div><p>${esc(texto)}</p></div>`;

export const vazio = ({ emoji = '🌿', titulo, texto = '', acao = '' }) => `
  <div class="vazio">
    <span class="vazio-emoji">${emoji}</span>
    <p class="vazio-titulo">${esc(titulo)}</p>
    ${texto ? `<p>${esc(texto)}</p>` : ''}
    ${acao ? `<div style="margin-top:18px">${acao}</div>` : ''}
  </div>`;

/** Desabilita o botão enquanto a promessa roda — evita clique duplo. */
export async function comBotaoOcupado(botao, texto, fn) {
  if (!botao) return fn();
  const antes = botao.innerHTML;
  botao.disabled = true;
  botao.innerHTML = `<span class="giro" style="width:18px;height:18px;border-width:2px"></span><span>${esc(texto)}</span>`;
  try { return await fn(); }
  finally { botao.disabled = false; botao.innerHTML = antes; }
}
