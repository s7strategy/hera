/* ==========================================================================
   S7 PONTO — tela de entrar. Dois campos, um botão. Só isso.
   ========================================================================== */
import { CONFIG } from './config.js';
import { store } from './store.js';
import { esc } from './util.js';
import { $, torrada, comBotaoOcupado } from './ui.js';
import { htmlLogo } from './tema.js';

export function telaDeEntrar(raiz, aoEntrar) {
  const demo = store.modo === 'demo';
  const dicas = demo ? store.dicasDeAcesso() : [];

  raiz.innerHTML = `
    <div class="entrar">
      <div class="entrar-caixa">
        ${htmlLogo('entrar-logo', 96)}
        <h1 class="entrar-titulo">${esc(CONFIG.BRAND.name)}</h1>
        <p class="entrar-sub">Bata seu ponto em dois toques.</p>

        <form id="form-entrar" novalidate>
          <label class="campo">
            <span class="campo-rotulo">Seu usuário</span>
            <input class="entrada" name="usuario" type="text" inputmode="text"
                   autocomplete="username" autocapitalize="none" autocorrect="off"
                   spellcheck="false" placeholder="ex.: maria" required>
          </label>
          <label class="campo">
            <span class="campo-rotulo">Sua senha</span>
            <input class="entrada" name="senha" type="password"
                   autocomplete="current-password" placeholder="••••••" required>
          </label>
          <p class="campo-erro" id="erro-entrar" hidden></p>
          <button class="btn btn-primario btn-medio btn-largo" type="submit">Entrar</button>
        </form>

        ${demo ? `
          <div class="entrar-dicas">
            <p class="rotulo" style="margin-bottom:8px">Modo demonstração · toque para preencher</p>
            ${dicas.map((d) => `
              <button type="button" class="entrar-dica" data-usuario="${esc(d.username)}" data-senha="${esc(d.senha)}">
                <span class="num">${esc(d.username)} / ${esc(d.senha)}</span>
                <span class="entrar-dica-papel">${esc(d.papel)}</span>
              </button>`).join('')}
            <p class="campo-dica" style="margin-top:12px">
              Os dados desta demonstração são inventados e ficam só neste aparelho.
            </p>
          </div>` : ''}
      </div>
    </div>`;

  const form = $('#form-entrar', raiz);
  const erro = $('#erro-entrar', raiz);

  raiz.querySelectorAll('.entrar-dica').forEach((b) => {
    b.addEventListener('click', () => {
      form.usuario.value = b.dataset.usuario;
      form.senha.value = b.dataset.senha;
      form.requestSubmit();
    });
  });

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    erro.hidden = true;
    const usuario = form.usuario.value.trim();
    const senha = form.senha.value;
    if (!usuario || !senha) {
      erro.textContent = 'Preencha usuário e senha.';
      erro.hidden = false;
      return;
    }
    try {
      const perfil = await comBotaoOcupado($('button[type=submit]', form), 'Entrando…',
        () => store.login(usuario, senha));
      torrada(`Bem-vindo(a), ${perfil.full_name.split(' ')[0]}!`, 'bom', 3);
      aoEntrar(perfil);
    } catch (e) {
      erro.textContent = e.message || 'Não consegui entrar.';
      erro.hidden = false;
      form.senha.select?.();
    }
  });
}
