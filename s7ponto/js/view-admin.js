/* ==========================================================================
   S7 PONTO — painel do super admin.
   Equipe · Tarefas · Turnos · Importar · Relatórios
   ========================================================================== */
import { store } from './store.js';
import {
  esc, money, horas, horasCurto, num, iniciais, maiuscula, plural,
  mesAno, nomeMes, dataLonga, dataBR, dataCurta, hora, diaChave,
  inicioDoMes, fimDoMes, somaMeses, paraInputLocal, deInputLocal,
  baixaArquivo, csvLinha, horasEntre, PERIODOS,
} from './util.js';
import {
  $, $$, ICONE, el, abreFolha, confirma, torrada, carregando, vazio, comBotaoOcupado,
} from './ui.js';
import { PALETA, graficoTarefas } from './charts.js';
import { pintaTrechos, agrega, horasDoTurno, valorDoTurno } from './metricas.js';

const ABAS = [
  { id: 'equipe',     nome: 'Equipe' },
  { id: 'empresas',   nome: 'Empresas' },
  { id: 'tarefas',    nome: 'Tarefas' },
  { id: 'turnos',     nome: 'Turnos' },
  { id: 'importar',   nome: 'Importar' },
  { id: 'relatorios', nome: 'Relatórios' },
];

export async function telaDeAdmin(raiz, ctx) {
  let aba = 'equipe';
  let pessoas = [], tarefas = [], atribuicoes = [];
  let empresas = [], atribEmpresas = [];
  let mesRef = inicioDoMes(new Date());
  let filtroPessoa = '';

  raiz.innerHTML = carregando('Abrindo o painel…');
  await recarregaBase();

  async function recarregaBase() {
    [pessoas, tarefas, atribuicoes, empresas, atribEmpresas] = await Promise.all([
      store.listaPessoas(), store.listaTarefas(true), store.listaAtribuicoes(),
      store.listaEmpresas(true), store.listaAtribuicoesEmpresa(),
    ]);
  }

  const tarefasDe = (userId) => atribuicoes
    .filter((a) => a.user_id === userId)
    .map((a) => tarefas.find((t) => t.id === a.task_id))
    .filter(Boolean);

  const empresasDe = (userId) => atribEmpresas
    .filter((a) => a.user_id === userId)
    .map((a) => empresas.find((c) => c.id === a.company_id))
    .filter(Boolean);

  /* ======================================================================
     Casca com abas
     ====================================================================== */

  function desenha() {
    raiz.innerHTML = `
      <h1 class="secao-titulo">Painel</h1>
      <div class="abas" role="tablist">
        ${ABAS.map((a) => `
          <button class="aba" role="tab" data-aba="${a.id}"
                  aria-selected="${a.id === aba}">${esc(a.nome)}</button>`).join('')}
      </div>
      <div id="conteudo-aba"></div>`;

    $$('[data-aba]', raiz).forEach((b) => {
      b.addEventListener('click', () => { aba = b.dataset.aba; desenha(); });
      if (b.dataset.aba === aba) {
        b.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
      }
    });

    const alvo = $('#conteudo-aba', raiz);
    ({ equipe: abaEquipe, empresas: abaEmpresas, tarefas: abaTarefas, turnos: abaTurnos,
       importar: abaImportar, relatorios: abaRelatorios }[aba])(alvo);
  }

  /* ======================================================================
     ABA: EQUIPE
     ====================================================================== */

  function abaEquipe(alvo) {
    alvo.innerHTML = `
      <button class="btn btn-primario btn-largo" id="nova-pessoa">
        ${ICONE.mais}<span>Cadastrar pessoa</span>
      </button>
      <div class="lista" style="margin-top:16px">
        ${pessoas.map(cartaoDaPessoa).join('')}
      </div>`;

    $('#nova-pessoa', alvo).addEventListener('click', () => editaPessoa(null));
    $$('[data-pessoa]', alvo).forEach((b) =>
      b.addEventListener('click', () => menuDaPessoa(pessoas.find((p) => p.id === b.dataset.pessoa))));
  }

  function cartaoDaPessoa(p) {
    const suas = tarefasDe(p.id);
    const sedes = empresasDe(p.id);
    const sedeTxt = sedes.length
      ? sedes.map((c) => `<span class="ficha-ponto" style="display:inline-block;background:${esc(c.color)};vertical-align:-1px"></span> ${esc(c.name)}`).join(' · ')
      : '<em>nenhuma empresa</em>';
    const modoLbl = p.pay_mode === 'shift' ? 'por turno'
      : p.pay_mode === 'task' ? 'por tarefa' : 'por hora';
    return `
      <button class="item clicavel" data-pessoa="${esc(p.id)}">
        <span class="avatar" style="width:44px;height:44px">${esc(iniciais(p.full_name))}</span>
        <span class="item-corpo">
          <span class="item-titulo">${esc(p.full_name)}
            ${p.role === 'admin' ? '<span class="ficha ficha-viva" style="margin-left:6px;padding:2px 8px;font-size:11px">admin</span>' : ''}
            ${p.active ? '' : '<span class="ficha ficha-baixa" style="margin-left:6px;padding:2px 8px;font-size:11px">desativado</span>'}
          </span>
          <span class="item-sub">@${esc(p.username)} · ${esc(modoLbl)} · ${sedeTxt}</span>
          <span class="item-sub">${suas.length
            ? suas.map((t) => `<span class="ficha-ponto" style="display:inline-block;background:${esc(t.color)};vertical-align:-1px"></span> ${esc(t.name)}`).join(' &nbsp;')
            : (p.pay_mode === 'shift' ? '<em>pagamento por turno (manhã/tarde/noite)</em>' : '<em>nenhuma tarefa liberada</em>')}
          </span>
        </span>
        <span class="escolha-seta">${ICONE.seta}</span>
      </button>`;
  }

  function menuDaPessoa(p) {
    abreFolha({
      titulo: p.full_name,
      sub: `@${p.username}`,
      corpo: `
        <div style="display:flex;flex-direction:column;gap:10px">
          <button class="btn btn-medio" data-empresas>${ICONE.predio}<span>Liberar empresas</span></button>
          <button class="btn btn-medio" data-tarefas>${ICONE.etiqueta}<span>Liberar tarefas</span></button>
          <button class="btn btn-medio" data-pagamento>${ICONE.engrenagem}<span>Como paga</span></button>
          <button class="btn btn-medio" data-edita>${ICONE.lapis}<span>Editar dados</span></button>
          <button class="btn btn-medio" data-senha>${ICONE.engrenagem}<span>Definir nova senha</span></button>
          <button class="btn btn-medio btn-perigo" data-apaga>${ICONE.lixo}<span>Remover do sistema</span></button>
        </div>`,
      aoMontar: (caixa, fechar) => {
        $('[data-empresas]', caixa).addEventListener('click', () => { fechar(); liberaEmpresas(p); });
        $('[data-tarefas]', caixa).addEventListener('click', () => { fechar(); liberaTarefas(p); });
        $('[data-pagamento]', caixa).addEventListener('click', () => { fechar(); editaPagamento(p); });
        $('[data-edita]', caixa).addEventListener('click', () => { fechar(); editaPessoa(p); });
        $('[data-senha]', caixa).addEventListener('click', () => { fechar(); defineSenha(p); });
        $('[data-apaga]', caixa).addEventListener('click', async () => {
          fechar();
          const certeza = await confirma({
            titulo: `Remover ${p.full_name}?`,
            texto: 'Todo o histórico de turnos dessa pessoa some junto. Não dá para desfazer. Se for só afastamento, prefira "Editar dados" e desativar o acesso.',
            ok: 'Remover mesmo assim', perigo: true,
          });
          if (!certeza) return;
          try {
            await store.apagaPessoa(p.id);
            await recarregaBase(); desenha();
            torrada('Pessoa removida.', 'bom');
          } catch (e) { torrada(e.message, 'ruim', 6); }
        });
      },
    });
  }

  async function editaPagamento(p) {
    const [ratesT, ratesS] = await Promise.all([
      store.listaTaxasTarefa(p.id),
      store.listaTaxasTurno(p.id),
    ]);
    const modoAtual = p.pay_mode || 'hourly';
    const suas = tarefasDe(p.id);

    function corpoDoModo(modo) {
      if (modo === 'shift') {
        return `
          <p class="campo-dica" style="margin-bottom:12px">Valor FIXO por período — não multiplica pelas horas. Ex.: Fran.</p>
          ${PERIODOS.map((per) => {
            const r = ratesS.find((x) => x.period === per.id);
            return `<label class="campo"><span class="campo-rotulo">${esc(per.nome)} (R$ fixo)</span>
              <input class="entrada" type="number" min="0" step="0.01" data-periodo="${esc(per.id)}"
                     value="${esc(r?.amount ?? '')}" placeholder="ex.: 100"></label>`;
          }).join('')}`;
      }
      if (!suas.length) {
        return `<div class="recado" style="margin-top:8px"><span class="recado-emoji">💡</span>
          <span>Libere pelo menos uma tarefa nesta pessoa antes de definir valores.</span></div>`;
      }
      if (modo === 'task') {
        return `
          <p class="campo-dica" style="margin-bottom:12px">Valor FIXO por tarefa — não multiplica pelas horas.</p>
          ${suas.map((t) => {
            const r = ratesT.find((x) => x.task_id === t.id);
            const v = r?.flat_amount != null ? r.flat_amount : t.hourly_rate;
            return `<label class="campo"><span class="campo-rotulo">${esc(t.name)} (R$ fixo)</span>
              <input class="entrada" type="number" min="0" step="0.01" data-task="${esc(t.id)}"
                     value="${esc(v ?? '')}" placeholder="${esc(t.hourly_rate)}"></label>`;
          }).join('')}`;
      }
      return `
        <p class="campo-dica" style="margin-bottom:12px">R$ por hora de cada tarefa. Em branco = usa o valor padrão da tarefa.</p>
        ${suas.map((t) => {
          const r = ratesT.find((x) => x.task_id === t.id);
          return `<label class="campo"><span class="campo-rotulo">${esc(t.name)} (R$/h)</span>
            <input class="entrada" type="number" min="0" step="0.01" data-task="${esc(t.id)}"
                   value="${esc(r?.hourly_rate ?? '')}" placeholder="${esc(t.hourly_rate)} (padrão)"></label>`;
        }).join('')}`;
    }

    abreFolha({
      titulo: `Como paga · ${p.full_name.split(' ')[0]}`,
      sub: 'Três modos claros: por hora, por tarefa ou por turno.',
      corpo: `
        <label class="campo"><span class="campo-rotulo">Modo de pagamento</span>
          <select class="entrada" id="pg-modo">
            <option value="hourly" ${modoAtual === 'hourly' ? 'selected' : ''}>Por hora — horas × R$/h da tarefa</option>
            <option value="task" ${modoAtual === 'task' ? 'selected' : ''}>Por tarefa — valor fixo da tarefa</option>
            <option value="shift" ${modoAtual === 'shift' ? 'selected' : ''}>Por turno — valor fixo manhã/tarde/noite</option>
          </select></label>
        <div id="pg-corpo">${corpoDoModo(modoAtual)}</div>
        <p class="campo-erro" id="pg-erro" hidden></p>
        <button class="btn btn-primario btn-medio btn-largo" id="pg-salva">Salvar pagamento</button>`,
      aoMontar: (caixa, fechar) => {
        const erro = $('#pg-erro', caixa);
        const corpo = $('#pg-corpo', caixa);
        $('#pg-modo', caixa).addEventListener('change', (ev) => {
          corpo.innerHTML = corpoDoModo(ev.target.value);
        });
        $('#pg-salva', caixa).addEventListener('click', async (ev) => {
          erro.hidden = true;
          const pay_mode = $('#pg-modo', caixa).value;
          let ratesTarefa = [];
          let ratesTurno = [];
          if (pay_mode === 'shift') {
            ratesTurno = PERIODOS.map((per) => {
              const inp = caixa.querySelector(`[data-periodo="${per.id}"]`);
              return { period: per.id, amount: inp?.value === '' ? 0 : +inp.value };
            });
          } else {
            ratesTarefa = suas.map((t) => {
              const inp = caixa.querySelector(`[data-task="${t.id}"]`);
              const raw = inp?.value;
              if (pay_mode === 'task') {
                return {
                  task_id: t.id,
                  flat_amount: raw === '' || raw == null ? t.hourly_rate : +raw,
                  hourly_rate: null,
                };
              }
              return {
                task_id: t.id,
                hourly_rate: raw === '' || raw == null ? null : +raw,
                flat_amount: null,
              };
            }).filter((r) => pay_mode === 'task' || r.hourly_rate != null);
          }
          try {
            await comBotaoOcupado(ev.currentTarget, 'Salvando…',
              () => store.definePagamento(p.id, { pay_mode, ratesTarefa, ratesTurno }));
            fechar();
            await recarregaBase(); desenha();
            torrada('Pagamento salvo.', 'bom');
          } catch (e) { erro.textContent = e.message; erro.hidden = false; }
        });
      },
    });
  }

  function editaPessoa(p) {
    const novo = !p;
    abreFolha({
      titulo: novo ? 'Cadastrar pessoa' : 'Editar dados',
      sub: novo ? 'Ela vai entrar com este usuário e senha.' : '',
      corpo: `
        <label class="campo"><span class="campo-rotulo">Nome completo</span>
          <input class="entrada" id="f-nome" value="${esc(p?.full_name || '')}" placeholder="ex.: Maria Aparecida"></label>
        <label class="campo"><span class="campo-rotulo">Usuário (para entrar)</span>
          <input class="entrada" id="f-user" value="${esc(p?.username || '')}" placeholder="ex.: maria"
                 autocapitalize="none" autocorrect="off" spellcheck="false" ${novo ? '' : 'disabled'}>
          <span class="campo-dica">${novo ? 'Só letras minúsculas, números, ponto, hífen ou _.' : 'O usuário não muda depois de criado.'}</span></label>
        ${novo ? `
          <label class="campo"><span class="campo-rotulo">Senha inicial</span>
            <input class="entrada" id="f-senha" type="text" placeholder="ex.: 1234">
            <span class="campo-dica">Só a administração pode trocar a senha depois.</span></label>` : ''}
        <label class="campo"><span class="campo-rotulo">O que ela pode fazer</span>
          <select class="entrada" id="f-papel">
            <option value="employee" ${p?.role === 'admin' ? '' : 'selected'}>Bater ponto e ver os próprios números</option>
            <option value="admin" ${p?.role === 'admin' ? 'selected' : ''}>Tudo — inclusive este painel</option>
          </select></label>
        ${novo ? '' : `
          <label class="chave" style="margin-bottom:16px">
            <input type="checkbox" id="f-ativo" ${p.active ? 'checked' : ''}>
            <span class="chave-pista"></span>
            <span>Acesso liberado</span>
          </label>`}
        <p class="campo-erro" id="f-erro" hidden></p>
        <button class="btn btn-primario btn-medio btn-largo" id="f-salva">
          ${novo ? 'Cadastrar' : 'Salvar'}</button>`,
      aoMontar: (caixa, fechar) => {
        const erro = $('#f-erro', caixa);
        $('#f-salva', caixa).addEventListener('click', async (ev) => {
          erro.hidden = true;
          const nome = $('#f-nome', caixa).value.trim();
          const papel = $('#f-papel', caixa).value;
          if (!nome) { erro.textContent = 'Escreva o nome da pessoa.'; erro.hidden = false; return; }
          try {
            if (novo) {
              const user = $('#f-user', caixa).value.trim().toLowerCase();
              const senha = $('#f-senha', caixa).value;
              await comBotaoOcupado(ev.currentTarget, 'Cadastrando…',
                () => store.criaPessoa({ username: user, full_name: nome, password: senha, role: papel }));
            } else {
              await comBotaoOcupado(ev.currentTarget, 'Salvando…',
                () => store.atualizaPessoa(p.id, {
                  full_name: nome, role: papel, active: $('#f-ativo', caixa).checked,
                }));
            }
            fechar();
            await recarregaBase(); desenha();
            torrada(novo ? 'Pessoa cadastrada.' : 'Dados salvos.', 'bom');
          } catch (e) { erro.textContent = e.message; erro.hidden = false; }
        });
      },
    });
  }

  function defineSenha(p) {
    abreFolha({
      titulo: `Nova senha de ${p.full_name.split(' ')[0]}`,
      sub: 'Passe a senha para ela. Só a administração define senhas.',
      corpo: `
        <label class="campo"><span class="campo-rotulo">Senha</span>
          <input class="entrada" id="p-senha" type="text" placeholder="ex.: 1234"></label>
        <p class="campo-erro" id="p-erro" hidden></p>
        <button class="btn btn-primario btn-medio btn-largo" id="p-salva">Definir senha</button>`,
      aoMontar: (caixa, fechar) => {
        const erro = $('#p-erro', caixa);
        $('#p-salva', caixa).addEventListener('click', async (ev) => {
          erro.hidden = true;
          try {
            await comBotaoOcupado(ev.currentTarget, 'Salvando…',
              () => store.trocaSenha(p.id, $('#p-senha', caixa).value));
            fechar();
            torrada('Senha definida.', 'bom');
          } catch (e) { erro.textContent = e.message; erro.hidden = false; }
        });
      },
    });
  }

  function liberaEmpresas(p) {
    const jaTem = new Set(empresasDe(p.id).map((c) => c.id));
    const ativas = empresas.filter((c) => c.active);
    abreFolha({
      titulo: `Empresas de ${p.full_name.split(' ')[0]}`,
      sub: ativas.length
        ? 'Marque onde essa pessoa pode trabalhar. Com uma só marcada, o turno começa nessa sede sem perguntar.'
        : 'Cadastre uma empresa primeiro, na aba Empresas.',
      corpo: `
        <div class="escolhas">
          ${ativas.map((c) => `
            <button class="escolha" data-c="${esc(c.id)}" aria-pressed="${jaTem.has(c.id)}">
              <span class="escolha-cor" style="background:${esc(c.color)}"></span>
              <span class="escolha-texto">
                <span class="escolha-nome">${esc(c.name)}</span>
              </span>
              <span class="escolha-seta" data-check>${jaTem.has(c.id) ? ICONE.check : ''}</span>
            </button>`).join('')}
        </div>
        <button class="btn btn-primario btn-medio btn-largo" style="margin-top:18px" id="c-salva">Salvar</button>`,
      aoMontar: (caixa, fechar) => {
        $$('.escolha', caixa).forEach((b) => b.addEventListener('click', () => {
          const marcado = b.getAttribute('aria-pressed') === 'true';
          b.setAttribute('aria-pressed', String(!marcado));
          $('[data-check]', b).innerHTML = marcado ? '' : ICONE.check;
        }));
        $('#c-salva', caixa).addEventListener('click', async (ev) => {
          const ids = $$('.escolha[aria-pressed="true"]', caixa).map((b) => b.dataset.c);
          try {
            await comBotaoOcupado(ev.currentTarget, 'Salvando…', () => store.defineEmpresas(p.id, ids));
            fechar();
            await recarregaBase(); desenha();
            torrada(ids.length
              ? `${plural(ids.length, 'empresa liberada', 'empresas liberadas')}.`
              : 'Nenhuma empresa liberada.', 'bom');
          } catch (e) { torrada(e.message, 'ruim', 6); }
        });
      },
    });
  }

  function liberaTarefas(p) {
    const jaTem = new Set(tarefasDe(p.id).map((t) => t.id));
    const ativas = tarefas.filter((t) => t.active);
    abreFolha({
      titulo: `Tarefas de ${p.full_name.split(' ')[0]}`,
      sub: ativas.length
        ? 'Marque tudo o que essa pessoa pode fazer. Com uma só marcada, o turno começa direto, sem perguntar.'
        : 'Cadastre uma tarefa primeiro, na aba Tarefas.',
      corpo: `
        <div class="escolhas">
          ${ativas.map((t) => `
            <button class="escolha" data-t="${esc(t.id)}" aria-pressed="${jaTem.has(t.id)}">
              <span class="escolha-cor" style="background:${esc(t.color)}"></span>
              <span class="escolha-texto">
                <span class="escolha-nome">${esc(t.name)}</span>
                <span class="escolha-preco">${esc(money(t.hourly_rate))} por hora</span>
              </span>
              <span class="escolha-seta" data-check>${jaTem.has(t.id) ? ICONE.check : ''}</span>
            </button>`).join('')}
        </div>
        <button class="btn btn-primario btn-medio btn-largo" style="margin-top:18px" id="t-salva">Salvar</button>`,
      aoMontar: (caixa, fechar) => {
        $$('.escolha', caixa).forEach((b) => b.addEventListener('click', () => {
          const marcado = b.getAttribute('aria-pressed') === 'true';
          b.setAttribute('aria-pressed', String(!marcado));
          $('[data-check]', b).innerHTML = marcado ? '' : ICONE.check;
        }));
        $('#t-salva', caixa).addEventListener('click', async (ev) => {
          const ids = $$('.escolha[aria-pressed="true"]', caixa).map((b) => b.dataset.t);
          try {
            await comBotaoOcupado(ev.currentTarget, 'Salvando…', () => store.defineAtribuicoes(p.id, ids));
            fechar();
            await recarregaBase(); desenha();
            torrada(ids.length ? `${plural(ids.length, 'tarefa liberada', 'tarefas liberadas')}.` : 'Nenhuma tarefa liberada.', 'bom');
          } catch (e) { torrada(e.message, 'ruim', 6); }
        });
      },
    });
  }

  /* ======================================================================
     ABA: EMPRESAS / SEDES
     ====================================================================== */

  function abaEmpresas(alvo) {
    alvo.innerHTML = `
      <div class="recado info">
        <span class="recado-emoji">🏢</span>
        <span>Cadastre as sedes onde a equipe trabalha — Pessoal, Cineplay, S7…
              Depois liberar na ficha de cada pessoa. Quem tem mais de uma escolhe ao iniciar o turno.</span>
      </div>
      <button class="btn btn-primario btn-largo" style="margin-top:16px" id="nova-empresa">
        ${ICONE.mais}<span>Nova empresa</span>
      </button>
      <div class="lista" style="margin-top:16px">
        ${empresas.length ? empresas.map((c) => `
          <button class="item clicavel" data-empresa="${esc(c.id)}">
            <span class="item-faixa" style="background:${esc(c.color)}"></span>
            <span class="item-corpo">
              <span class="item-titulo">${esc(c.name)}
                ${c.active ? '' : '<span class="ficha ficha-baixa" style="margin-left:6px;padding:2px 8px;font-size:11px">inativa</span>'}</span>
              <span class="item-sub">${esc(plural(
                atribEmpresas.filter((a) => a.company_id === c.id).length, 'pessoa liberada', 'pessoas liberadas'))}</span>
            </span>
            <span class="escolha-seta">${ICONE.seta}</span>
          </button>`).join('')
          : vazio({ emoji: '🏢', titulo: 'Nenhuma empresa ainda',
                    texto: 'Crie a primeira sede para a equipe poder bater o ponto.' })}
      </div>`;

    $('#nova-empresa', alvo).addEventListener('click', () => editaEmpresa(null));
    $$('[data-empresa]', alvo).forEach((b) =>
      b.addEventListener('click', () => editaEmpresa(empresas.find((c) => c.id === b.dataset.empresa))));
  }

  function editaEmpresa(c) {
    const novo = !c;
    abreFolha({
      titulo: novo ? 'Nova empresa' : 'Editar empresa',
      sub: 'Ex.: Pessoal, Cineplay, S7…',
      corpo: `
        <label class="campo"><span class="campo-rotulo">Nome</span>
          <input class="entrada" id="e-nome" value="${esc(c?.name || '')}" placeholder="ex.: Cineplay"></label>
        <label class="campo"><span class="campo-rotulo">Cor</span>
          <input class="entrada" id="e-cor" type="color" value="${esc(c?.color || '#3987e5')}"
                 style="padding:4px;height:48px"></label>
        ${novo ? '' : `
          <label class="chave" style="margin-bottom:16px">
            <input type="checkbox" id="e-ativo" ${c.active ? 'checked' : ''}>
            <span class="chave-pista"></span>
            <span>Empresa ativa</span>
          </label>`}
        <p class="campo-erro" id="e-erro" hidden></p>
        <div class="linha-botoes">
          ${novo ? '' : `<button class="btn btn-medio btn-perigo" id="e-apaga">${ICONE.lixo}<span>Apagar</span></button>`}
          <button class="btn btn-primario btn-medio" id="e-salva" style="flex:1">
            ${novo ? 'Criar' : 'Salvar'}</button>
        </div>`,
      aoMontar: (caixa, fechar) => {
        const erro = $('#e-erro', caixa);
        $('#e-salva', caixa).addEventListener('click', async (ev) => {
          erro.hidden = true;
          const nome = $('#e-nome', caixa).value.trim();
          const cor = $('#e-cor', caixa).value;
          if (!nome) { erro.textContent = 'Escreva o nome da empresa.'; erro.hidden = false; return; }
          try {
            if (novo) {
              await comBotaoOcupado(ev.currentTarget, 'Criando…',
                () => store.criaEmpresa({ name: nome, color: cor, sort_order: empresas.length + 1 }));
            } else {
              await comBotaoOcupado(ev.currentTarget, 'Salvando…',
                () => store.atualizaEmpresa(c.id, {
                  name: nome, color: cor, active: $('#e-ativo', caixa).checked,
                }));
            }
            fechar();
            await recarregaBase(); desenha();
            torrada(novo ? 'Empresa criada.' : 'Empresa salva.', 'bom');
          } catch (e) { erro.textContent = e.message; erro.hidden = false; }
        });
        $('#e-apaga', caixa)?.addEventListener('click', async () => {
          const certeza = await confirma({
            titulo: `Apagar ${c.name}?`,
            texto: 'Quem tinha só esta empresa vai precisar receber outra. Turnos antigos mantêm o nome guardado.',
            ok: 'Apagar', perigo: true,
          });
          if (!certeza) return;
          try {
            await store.apagaEmpresa(c.id);
            fechar();
            await recarregaBase(); desenha();
            torrada('Empresa apagada.', 'bom');
          } catch (e) { torrada(e.message, 'ruim', 6); }
        });
      },
    });
  }

  /* ======================================================================
     ABA: TAREFAS
     ====================================================================== */

  function abaTarefas(alvo) {
    alvo.innerHTML = `
      <div class="recado info">
        <span class="recado-emoji">💰</span>
        <span>O valor da hora é congelado no momento em que a pessoa começa o trecho.
              Se você mudar o preço amanhã, o que já foi trabalhado continua valendo o de hoje.</span>
      </div>
      <button class="btn btn-primario btn-largo" style="margin-top:16px" id="nova-tarefa">
        ${ICONE.mais}<span>Nova tarefa</span>
      </button>
      <div class="lista" style="margin-top:16px">
        ${tarefas.length ? tarefas.map((t) => `
          <button class="item clicavel" data-tarefa="${esc(t.id)}">
            <span class="item-faixa" style="background:${esc(t.color)}"></span>
            <span class="item-corpo">
              <span class="item-titulo">${esc(t.name)}
                ${t.active ? '' : '<span class="ficha ficha-baixa" style="margin-left:6px;padding:2px 8px;font-size:11px">inativa</span>'}</span>
              <span class="item-sub">${esc(plural(
                atribuicoes.filter((a) => a.task_id === t.id).length, 'pessoa liberada', 'pessoas liberadas'))}</span>
            </span>
            <span class="item-fim">
              <span class="num" style="font-weight:600;font-size:17px">${esc(money(t.hourly_rate))}</span>
              <span class="apagado" style="display:block;font-size:12px">por hora</span>
            </span>
          </button>`).join('')
          : vazio({ emoji: '🏷️', titulo: 'Nenhuma tarefa ainda',
                    texto: 'Crie a primeira para a equipe poder bater o ponto.' })}
      </div>`;

    $('#nova-tarefa', alvo).addEventListener('click', () => editaTarefa(null));
    $$('[data-tarefa]', alvo).forEach((b) =>
      b.addEventListener('click', () => editaTarefa(tarefas.find((t) => t.id === b.dataset.tarefa))));
  }

  function editaTarefa(t) {
    const novo = !t;
    const corAtual = t?.color || PALETA[tarefas.length % PALETA.length];
    abreFolha({
      titulo: novo ? 'Nova tarefa' : t.name,
      sub: 'Nome curto e claro — é o que a equipe vê na hora de escolher.',
      corpo: `
        <label class="campo"><span class="campo-rotulo">Nome da tarefa</span>
          <input class="entrada" id="t-nome" value="${esc(t?.name || '')}" placeholder="ex.: Cozinha"></label>
        <label class="campo"><span class="campo-rotulo">Quanto vale a hora (R$)</span>
          <input class="entrada num" id="t-valor" type="number" inputmode="decimal" min="0" step="0.50"
                 value="${esc(t ? Number(t.hourly_rate).toFixed(2) : '')}" placeholder="ex.: 20,00"></label>
        <div class="campo">
          <span class="campo-rotulo">Cor (para achar rápido nos gráficos)</span>
          <div style="display:flex;gap:9px;flex-wrap:wrap" id="t-cores">
            ${PALETA.map((c) => `
              <button type="button" data-cor="${c}" aria-pressed="${c === corAtual}"
                style="width:44px;height:44px;border-radius:12px;background:${c};
                       border:3px solid ${c === corAtual ? 'var(--tinta)' : 'transparent'}"
                aria-label="Cor ${c}"></button>`).join('')}
          </div>
        </div>
        ${novo ? '' : `
          <label class="chave" style="margin-bottom:16px">
            <input type="checkbox" id="t-ativa" ${t.active ? 'checked' : ''}>
            <span class="chave-pista"></span>
            <span>Disponível para escolher</span>
          </label>`}
        <p class="campo-erro" id="t-erro" hidden></p>
        <div class="linha-botoes">
          ${novo ? '' : '<button class="btn btn-medio btn-perigo" id="t-apaga">Apagar</button>'}
          <button class="btn btn-primario btn-medio" id="t-salva">${novo ? 'Criar tarefa' : 'Salvar'}</button>
        </div>`,
      aoMontar: (caixa, fechar) => {
        let cor = corAtual;
        const erro = $('#t-erro', caixa);
        $$('[data-cor]', caixa).forEach((b) => b.addEventListener('click', () => {
          cor = b.dataset.cor;
          $$('[data-cor]', caixa).forEach((x) => {
            const sel = x.dataset.cor === cor;
            x.setAttribute('aria-pressed', String(sel));
            x.style.borderColor = sel ? 'var(--tinta)' : 'transparent';
          });
        }));

        $('#t-salva', caixa).addEventListener('click', async (ev) => {
          erro.hidden = true;
          const nome = $('#t-nome', caixa).value.trim();
          const valor = parseFloat(String($('#t-valor', caixa).value).replace(',', '.'));
          if (!nome) { erro.textContent = 'Dê um nome à tarefa.'; erro.hidden = false; return; }
          if (!Number.isFinite(valor) || valor < 0) { erro.textContent = 'Informe quanto vale a hora.'; erro.hidden = false; return; }
          try {
            await comBotaoOcupado(ev.currentTarget, 'Salvando…', () => novo
              ? store.criaTarefa({ name: nome, color: cor, hourly_rate: valor, sort_order: tarefas.length + 1 })
              : store.atualizaTarefa(t.id, { name: nome, color: cor, hourly_rate: valor, active: $('#t-ativa', caixa).checked }));
            fechar();
            await recarregaBase(); desenha();
            torrada(novo ? 'Tarefa criada.' : 'Tarefa salva.', 'bom');
          } catch (e) { erro.textContent = e.message; erro.hidden = false; }
        });

        $('#t-apaga', caixa)?.addEventListener('click', async () => {
          fechar();
          const certeza = await confirma({
            titulo: `Apagar "${t.name}"?`,
            texto: 'Os turnos que já usaram essa tarefa continuam valendo, com o nome e o valor guardados. Se é só para tirar da lista, prefira desmarcar "Disponível para escolher".',
            ok: 'Apagar', perigo: true,
          });
          if (!certeza) return;
          try {
            await store.apagaTarefa(t.id);
            await recarregaBase(); desenha();
            torrada('Tarefa apagada.', 'bom');
          } catch (e) { torrada(e.message, 'ruim', 6); }
        });
      },
    });
  }

  /* ======================================================================
     ABA: TURNOS
     ====================================================================== */

  async function abaTurnos(alvo) {
    alvo.innerHTML = carregando('Buscando turnos…');
    const turnos = pintaTrechos(await store.listaTurnos({
      userId: filtroPessoa || null,
      de: inicioDoMes(mesRef), ate: fimDoMes(mesRef),
    }), tarefas);
    const nomeDe = (id) => pessoas.find((p) => p.id === id)?.full_name || 'Alguém';
    const abertos = turnos.filter((t) => !t.ended_at);

    alvo.innerHTML = `
      ${barraDeFiltro()}
      ${abertos.length ? `
        <div class="recado" style="margin-bottom:16px">
          <span class="recado-emoji">⏳</span>
          <span><strong>${esc(plural(abertos.length, 'turno em aberto', 'turnos em aberto'))}</strong> —
                ${esc(abertos.map((t) => nomeDe(t.user_id)).join(', '))}.
                Toque no turno para corrigir a hora de saída.</span>
        </div>` : ''}
      <button class="btn btn-primario btn-largo" id="novo-turno">
        ${ICONE.mais}<span>Lançar turno na mão</span>
      </button>
      <div class="lista" style="margin-top:16px">
        ${turnos.length ? turnos.map((t) => `
          <button class="item clicavel" data-turno="${esc(t.id)}">
            <span class="item-faixa" style="background:${esc(t.segments?.[0]?.cor || PALETA[0])}"></span>
            <span class="item-corpo">
              <span class="item-titulo">${esc(nomeDe(t.user_id))}
                ${t.ended_at ? '' : '<span class="ficha ficha-alta" style="margin-left:6px;padding:2px 8px;font-size:11px">em turno</span>'}</span>
              <span class="item-sub">${esc(maiuscula(dataLonga(t.started_at)))} ·
                ${esc(hora(t.started_at))} → ${t.ended_at ? esc(hora(t.ended_at)) : '—'} ·
                ${t.company_name ? `${esc(t.company_name)} · ` : ''}${esc([...new Set((t.segments || []).map((s) => s.task_name))].join(', ') || 'sem tarefa')}
                ${t.source === 'import' ? ' · importado' : t.source === 'manual' ? ' · manual' : ''}</span>
            </span>
            <span class="item-fim">
              <span class="num" style="font-weight:600">${esc(horasCurto(horasDoTurno(t)))}</span>
              <span class="num apagado" style="display:block;font-size:12px">${esc(money(valorDoTurno(t)))}</span>
            </span>
          </button>`).join('')
          : vazio({ emoji: '📭', titulo: 'Nenhum turno neste mês',
                    texto: 'Mude o mês, tire o filtro de pessoa, ou lance um turno na mão.' })}
      </div>`;

    ligaFiltro(alvo, abaTurnos);
    $('#novo-turno', alvo).addEventListener('click', () => editaTurno(null));
    $$('[data-turno]', alvo).forEach((b) =>
      b.addEventListener('click', () => editaTurno(turnos.find((t) => t.id === b.dataset.turno))));
  }

  function editaTurno(t) {
    const novo = !t;
    const ativas = tarefas.filter((x) => x.active);
    const sedesAtivas = empresas.filter((x) => x.active);
    if (novo && !ativas.length) { torrada('Cadastre uma tarefa antes de lançar turnos.', 'ruim', 5); return; }
    if (novo && !pessoas.length) { torrada('Cadastre alguém antes de lançar turnos.', 'ruim', 5); return; }
    if (novo && !sedesAtivas.length) { torrada('Cadastre uma empresa antes de lançar turnos.', 'ruim', 5); return; }

    const ini = novo ? new Date(new Date().setHours(8, 0, 0, 0)) : new Date(t.started_at);
    const fim = novo ? new Date(new Date().setHours(17, 0, 0, 0)) : (t.ended_at ? new Date(t.ended_at) : null);
    const tarefaAtual = novo ? ativas[0].id
      : (tarefas.find((x) => x.id === t.segments?.[0]?.task_id)?.id || ativas[0]?.id || '');
    const empresaAtual = novo ? sedesAtivas[0].id
      : (t.company_id || sedesAtivas[0]?.id || '');

    abreFolha({
      titulo: novo ? 'Lançar turno na mão' : 'Corrigir turno',
      sub: novo ? 'Para quando alguém esqueceu de bater o ponto.'
                : `${t.segments?.length > 1 ? 'Este turno tem mais de uma tarefa — salvar aqui deixa ele com uma só. ' : ''}Ajuste os horários e salve.`,
      corpo: `
        <label class="campo"><span class="campo-rotulo">De quem é o turno</span>
          <select class="entrada" id="v-pessoa" ${novo ? '' : 'disabled'}>
            ${pessoas.map((p) => `<option value="${esc(p.id)}" ${!novo && p.id === t.user_id ? 'selected' : ''}>${esc(p.full_name)}</option>`).join('')}
          </select></label>
        <label class="campo"><span class="campo-rotulo">Empresa / sede</span>
          <select class="entrada" id="v-empresa">
            ${sedesAtivas.map((x) => `<option value="${esc(x.id)}" ${x.id === empresaAtual ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}
          </select></label>
        <label class="campo"><span class="campo-rotulo">Tarefa</span>
          <select class="entrada" id="v-tarefa">
            ${ativas.map((x) => `<option value="${esc(x.id)}" ${x.id === tarefaAtual ? 'selected' : ''}>${esc(x.name)} — ${esc(money(x.hourly_rate))}/h</option>`).join('')}
          </select></label>
        <div class="grade-campos">
          <label class="campo"><span class="campo-rotulo">Entrada</span>
            <input class="entrada" id="v-ini" type="datetime-local" value="${esc(paraInputLocal(ini))}"></label>
          <label class="campo"><span class="campo-rotulo">Saída</span>
            <input class="entrada" id="v-fim" type="datetime-local" value="${fim ? esc(paraInputLocal(fim)) : ''}">
            <span class="campo-dica">Deixe vazio para manter em aberto.</span></label>
        </div>
        <p class="campo-erro" id="v-erro" hidden></p>
        <div class="linha-botoes">
          ${novo ? '' : '<button class="btn btn-medio btn-perigo" id="v-apaga">Apagar turno</button>'}
          <button class="btn btn-primario btn-medio" id="v-salva">${novo ? 'Lançar' : 'Salvar'}</button>
        </div>`,
      aoMontar: (caixa, fechar) => {
        const erro = $('#v-erro', caixa);
        $('#v-salva', caixa).addEventListener('click', async (ev) => {
          erro.hidden = true;
          const de = deInputLocal($('#v-ini', caixa).value);
          const ate = deInputLocal($('#v-fim', caixa).value);
          const tar = tarefas.find((x) => x.id === $('#v-tarefa', caixa).value);
          const emp = empresas.find((x) => x.id === $('#v-empresa', caixa).value);
          if (!de) { erro.textContent = 'Informe a hora de entrada.'; erro.hidden = false; return; }
          if (ate && ate < de) { erro.textContent = 'A saída precisa ser depois da entrada.'; erro.hidden = false; return; }
          if (!tar) { erro.textContent = 'Escolha a tarefa.'; erro.hidden = false; return; }
          if (!emp) { erro.textContent = 'Escolha a empresa.'; erro.hidden = false; return; }
          const trecho = {
            task_id: tar.id, task_name: tar.name, hourly_rate: tar.hourly_rate,
            started_at: de, ended_at: ate,
          };
          try {
            await comBotaoOcupado(ev.currentTarget, 'Salvando…', () => novo
              ? store.gravaTurnoManual({
                  user_id: $('#v-pessoa', caixa).value,
                  company_id: emp.id, company_name: emp.name,
                  started_at: de, ended_at: ate, trechos: [trecho], source: 'manual',
                })
              : store.atualizaTurno(t.id, {
                  started_at: de, ended_at: ate, trechos: [trecho],
                  company_id: emp.id, company_name: emp.name,
                }));
            fechar();
            desenha();
            torrada(novo ? 'Turno lançado.' : 'Turno corrigido.', 'bom');
          } catch (e) { erro.textContent = e.message; erro.hidden = false; }
        });

        $('#v-apaga', caixa)?.addEventListener('click', async () => {
          fechar();
          if (!await confirma({ titulo: 'Apagar este turno?', texto: 'As horas somem do relatório. Não dá para desfazer.', ok: 'Apagar', perigo: true })) return;
          try {
            await store.apagaTurno(t.id);
            desenha();
            torrada('Turno apagado.', 'bom');
          } catch (e) { torrada(e.message, 'ruim', 6); }
        });
      },
    });
  }

  /* ======================================================================
     ABA: IMPORTAR
     ====================================================================== */

  async function abaImportar(alvo) {
    alvo.innerHTML = carregando('Preparando o importador…');
    const { montaImportador } = await import('./importador.js');
    montaImportador(alvo, {
      pessoas, tarefas,
      aoTerminar: async () => { await recarregaBase(); },
    });
  }

  /* ======================================================================
     ABA: RELATÓRIOS
     ====================================================================== */

  async function abaRelatorios(alvo) {
    alvo.innerHTML = carregando('Fechando as contas…');
    const turnos = pintaTrechos(await store.listaTurnos({
      de: inicioDoMes(mesRef), ate: fimDoMes(mesRef),
    }), tarefas);
    const geral = agrega(turnos);

    const linhas = pessoas.map((p) => {
      const r = geral.porPessoa.get(p.id) || { horas: 0, valor: 0, turnos: 0 };
      const dias = new Set(turnos.filter((t) => t.user_id === p.id).map((t) => diaChave(t.started_at))).size;
      return { p, ...r, dias, media: dias ? r.horas / dias : 0 };
    }).filter((l) => l.horas > 0 || l.p.active)
      .sort((a, b) => b.valor - a.valor);

    const maiorValor = Math.max(...linhas.map((l) => l.valor), 1);

    alvo.innerHTML = `
      ${barraDeFiltro({ semPessoa: true })}

      <section class="cartao">
        <div class="heroi">
          <p class="heroi-rotulo">Custo de mão de obra em ${esc(nomeMes(mesRef))}</p>
          <p class="heroi-valor">${esc(money(geral.valor))}</p>
          <div class="heroi-nota">
            <span class="ficha ficha-neutra">${esc(horas(geral.horas))}</span>
            <span class="ficha ficha-neutra">${esc(plural(geral.turnos, 'turno', 'turnos'))}</span>
            <span class="ficha ficha-neutra">${esc(plural(linhas.filter((l) => l.horas > 0).length, 'pessoa', 'pessoas'))}</span>
          </div>
        </div>
      </section>

      <section class="cartao">
        <div class="cartao-topo">
          <h2 class="cartao-titulo">Por pessoa</h2>
          <button class="btn btn-pequeno btn-fantasma" id="r-csv">${ICONE.baixar}<span>Baixar CSV</span></button>
        </div>
        ${linhas.length ? `<div class="lista">${linhas.map((l) => `
          <div class="item" style="flex-direction:column;align-items:stretch;gap:8px">
            <div style="display:flex;align-items:center;gap:12px">
              <span class="avatar" style="width:38px;height:38px;font-size:12px;flex:none">${esc(iniciais(l.p.full_name))}</span>
              <span class="item-titulo" style="flex:1;min-width:0">${esc(l.p.full_name)}</span>
              <span class="num" style="font-weight:600;font-size:17px;flex:none">${esc(money(l.valor))}</span>
            </div>
            <div class="item-sub" style="margin:0">${l.horas
              ? `${esc(horas(l.horas))} · ${esc(plural(l.dias, 'dia', 'dias'))} · média de ${esc(horas(l.media))} por dia`
              : 'sem registro neste mês'}</div>
            ${l.valor ? `
              <div style="height:8px;border-radius:5px;background:rgba(255,255,255,.05);overflow:hidden">
                <div style="height:100%;border-radius:5px;background:${PALETA[0]};width:${(l.valor / maiorValor) * 100}%"></div>
              </div>` : ''}
          </div>`).join('')}</div>`
          : vazio({ emoji: '📊', titulo: 'Nada registrado neste mês' })}
      </section>

      <section class="cartao">
        <div class="cartao-topo"><h2 class="cartao-titulo">Custo por tarefa</h2></div>
        <div class="grafico" id="r-tarefas"></div>
      </section>`;

    ligaFiltro(alvo, abaRelatorios);
    graficoTarefas($('#r-tarefas', alvo),
      [...geral.porTarefa.values()].sort((a, b) => b.horas - a.horas));

    $('#r-csv', alvo).addEventListener('click', () => {
      if (!linhas.length) { torrada('Nada para baixar neste mês.', 'ruim'); return; }
      const csv = [csvLinha(['Pessoa', 'Usuário', 'Turnos', 'Dias', 'Horas', 'Média h/dia', 'Total R$'])];
      linhas.forEach((l) => csv.push(csvLinha([
        l.p.full_name, l.p.username, l.turnos, l.dias,
        num(l.horas, 2), num(l.media, 2), num(l.valor, 2),
      ])));
      csv.push('');
      csv.push(csvLinha(['TOTAL', '', geral.turnos, '', num(geral.horas, 2), '', num(geral.valor, 2)]));
      baixaArquivo(`s7ponto-relatorio-${diaChave(mesRef).slice(0, 7)}.csv`, csv.join('\n'));
      torrada('Relatório baixado.', 'bom');
    });
  }

  /* ======================================================================
     Filtro compartilhado (mês + pessoa)
     ====================================================================== */

  function barraDeFiltro({ semPessoa = false } = {}) {
    const podeAvancar = somaMeses(mesRef, 1) <= inicioDoMes(new Date());
    return `
      <nav class="mes-nav">
        <button class="mes-nav-btn" data-mes="-1" aria-label="Mês anterior">${ICONE.esquerda}</button>
        <div class="mes-nav-titulo">${esc(maiuscula(mesAno(mesRef)))}</div>
        <button class="mes-nav-btn" data-mes="1" ${podeAvancar ? '' : 'disabled'} aria-label="Próximo mês">${ICONE.direita}</button>
      </nav>
      ${semPessoa ? '' : `
        <label class="campo">
          <span class="campo-rotulo">Filtrar por pessoa</span>
          <select class="entrada" data-filtro-pessoa>
            <option value="">Todo mundo</option>
            ${pessoas.map((p) => `<option value="${esc(p.id)}" ${p.id === filtroPessoa ? 'selected' : ''}>${esc(p.full_name)}</option>`).join('')}
          </select>
        </label>`}`;
  }

  function ligaFiltro(alvo, redesenha) {
    $$('[data-mes]', alvo).forEach((b) => b.addEventListener('click', () => {
      mesRef = somaMeses(mesRef, +b.dataset.mes);
      redesenha(alvo);
    }));
    $('[data-filtro-pessoa]', alvo)?.addEventListener('change', (ev) => {
      filtroPessoa = ev.target.value;
      redesenha(alvo);
    });
  }

  desenha();
  return { destruir() {} };
}
