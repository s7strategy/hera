/* ==========================================================================
   S7 PONTO — casca do aplicativo: entra, navega, sai.
   ========================================================================== */
import { CONFIG } from './config.js';
import { iniciaStore, store, demoForcada } from './store.js';
import { esc, iniciais } from './util.js';
import { $, $$, ICONE, el, abreFolha, confirma, torrada, carregando } from './ui.js';
import { telaDeEntrar } from './view-login.js';
import { telaDePonto } from './view-ponto.js';
import { telaDeNumeros } from './view-numeros.js';

const raiz = document.getElementById('raiz');
let usuario = null;
let viewAtual = null;
let telaAtual = 'ponto';

const TELAS = {
  ponto:   { nome: 'Ponto',        icone: ICONE.relogio,    carrega: () => telaDePonto },
  numeros: { nome: 'Meus números', icone: ICONE.grafico,    carrega: () => telaDeNumeros },
  admin:   { nome: 'Painel',       icone: ICONE.engrenagem, soAdmin: true,
             carrega: async () => (await import('./view-admin.js')).telaDeAdmin },
};

const telasVisiveis = () => Object.entries(TELAS)
  .filter(([, t]) => !t.soAdmin || usuario?.role === 'admin');

/* ==========================================================================
   Casca
   ========================================================================== */

function desenhaCasca() {
  raiz.innerHTML = `
    <div class="app">
      <header class="topo">
        <div class="marca">
          <div class="marca-selo">S7</div>
          <div>
            <div class="marca-nome">${esc(CONFIG.BRAND.name)}</div>
            <div class="marca-sub" id="casca-sub"></div>
          </div>
        </div>
        ${store.modo === 'demo' ? '<span class="ficha ficha-viva">demonstração</span>' : ''}
        <button class="avatar" id="btn-perfil" aria-label="Sua conta">${esc(iniciais(usuario.full_name))}</button>
      </header>
      <main class="pagina" id="pagina" tabindex="-1"></main>
      <nav class="nav" aria-label="Seções">
        ${telasVisiveis().map(([id, t]) => `
          <button class="nav-item" data-tela="${id}">${t.icone}<span>${esc(t.nome)}</span></button>`).join('')}
      </nav>
    </div>`;

  $('#casca-sub').textContent = usuario.full_name;

  $$('[data-tela]').forEach((b) => b.addEventListener('click', () => vaiPara(b.dataset.tela)));
  $('#btn-perfil').addEventListener('click', abreMenuDoPerfil);
}

async function vaiPara(tela) {
  if (!telasVisiveis().some(([id]) => id === tela)) tela = 'ponto';
  telaAtual = tela;
  $$('[data-tela]').forEach((b) =>
    b.setAttribute('aria-current', b.dataset.tela === tela ? 'page' : 'false'));

  viewAtual?.destruir?.();
  viewAtual = null;

  const pagina = $('#pagina');
  pagina.classList.toggle('larga', tela === 'admin');
  pagina.innerHTML = carregando();
  try {
    const montar = await TELAS[tela].carrega();
    viewAtual = await montar(pagina, { usuario, vaiPara, sai });
  } catch (e) {
    console.error(e);
    pagina.innerHTML = `
      <div class="recado ruim" style="margin-top:20px">
        <span class="recado-emoji">⚠️</span>
        <span><strong>Não consegui abrir esta tela.</strong><br>${esc(e.message || e)}</span>
      </div>
      <button class="btn btn-fantasma btn-largo" style="margin-top:14px" id="btn-tenta">Tentar de novo</button>`;
    $('#btn-tenta')?.addEventListener('click', () => vaiPara(tela));
  }
  pagina.scrollTop = 0;
  window.scrollTo({ top: 0 });
}

/* ==========================================================================
   Menu do perfil
   ========================================================================== */

function abreMenuDoPerfil() {
  abreFolha({
    titulo: usuario.full_name,
    sub: `@${usuario.username}${usuario.role === 'admin' ? ' · administração' : ''}`,
    corpo: `
      <div style="display:flex;flex-direction:column;gap:10px">
        ${store.modo === 'demo' ? `
          <button class="btn btn-medio btn-fantasma" data-zera>${ICONE.lixo}<span>Zerar a demonstração</span></button>` : ''}
        <button class="btn btn-medio btn-perigo" data-sai>${ICONE.sair}<span>Sair da minha conta</span></button>
      </div>`,
    aoMontar: (caixa, fechar) => {
      $('[data-sai]', caixa).addEventListener('click', async () => {
        fechar();
        if (await confirma({ titulo: 'Sair da conta?', texto: 'Você vai precisar entrar de novo com usuário e senha.', ok: 'Sair', perigo: true })) sai();
      });
      $('[data-zera]', caixa)?.addEventListener('click', async () => {
        fechar();
        if (await confirma({ titulo: 'Zerar a demonstração?', texto: 'Os dados de mentira voltam ao estado original.', ok: 'Zerar', perigo: true })) {
          await store.zeraDemo();
          location.reload();
        }
      });
    },
  });
}

/* ==========================================================================
   Entrada e saída
   ========================================================================== */

async function entrou(perfil) {
  usuario = perfil;
  desenhaCasca();
  await vaiPara('ponto');
}

async function sai() {
  viewAtual?.destruir?.();
  viewAtual = null;
  await store.logout();
  usuario = null;
  telaDeEntrar(raiz, entrou);
}

/* ==========================================================================
   Partida
   ========================================================================== */

async function partir() {
  raiz.innerHTML = carregando('Abrindo o S7 PONTO…');
  try {
    await iniciaStore();
  } catch (e) {
    console.error(e);
    raiz.innerHTML = `
      <div class="entrar"><div class="entrar-caixa">
        <div class="recado ruim">
          <span class="recado-emoji">⚠️</span>
          <span><strong>Não consegui conectar ao servidor.</strong><br>${esc(e.message || e)}
          <br><br>Confira <code>js/config.js</code> e o passo 3 do README.</span>
        </div>
        <a class="btn btn-fantasma btn-largo" style="margin-top:14px" href="?demo=1">Abrir em modo demonstração</a>
      </div></div>`;
    return;
  }

  const perfil = store.usuarioAtual();
  if (perfil) await entrou(perfil);
  else telaDeEntrar(raiz, entrou);

  if (demoForcada() || store.modo === 'demo') {
    document.title = `${CONFIG.BRAND.name} · demonstração`;
  }
}

// Voltar do celular fechando a folha em vez de sair do app
window.addEventListener('pageshow', () => { document.body.style.overflow = ''; });

partir();
