/* ==========================================================================
   S7 PONTO — tema claro/escuro por pessoa (local + servidor).
   ========================================================================== */

const ULTIMO = 's7ponto.tema.ultimo';
const chave = (id) => `s7ponto.tema.${id}`;

export const normalizaTema = (t) => (t === 'claro' ? 'claro' : 'escuro');

export function aplicaTema(tema) {
  const t = normalizaTema(tema);
  document.documentElement.dataset.tema = t;
  document.documentElement.style.colorScheme = t === 'claro' ? 'light' : 'dark';
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = t === 'claro' ? '#efe8d8' : '#0c0d0a';
}

export function leTemaLocal(userId) {
  try {
    if (userId) {
      const v = localStorage.getItem(chave(userId));
      if (v) return normalizaTema(v);
    }
    return normalizaTema(localStorage.getItem(ULTIMO) || 'escuro');
  } catch {
    return 'escuro';
  }
}

export function gravaTemaLocal(userId, tema) {
  const t = normalizaTema(tema);
  try {
    localStorage.setItem(ULTIMO, t);
    if (userId) localStorage.setItem(chave(userId), t);
  } catch { /* storage bloqueado */ }
}

export async function defineTemaUsuario(store, userId, tema) {
  const t = normalizaTema(tema);
  aplicaTema(t);
  gravaTemaLocal(userId, t);
  try { await store.defineTema?.(t); } catch { /* offline / coluna nova */ }
  return t;
}

export const htmlLogo = (classe = 'marca-logo', tamanho = 40) => `
  <span class="logo-caixa">
    <img class="${classe} logo-para-escuro" src="assets/logo-s7.svg" alt="S7"
         width="${tamanho}" height="${tamanho}">
    <img class="${classe} logo-para-claro" src="assets/logo-dark.png" alt="S7"
         width="${tamanho}" height="${tamanho}">
  </span>`;
