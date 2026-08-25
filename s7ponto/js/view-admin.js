/* ==========================================================================
   S7 PONTO — painel do super admin.
   Equipe · Empresas · Tarefas · Turnos · Conferência · Importar · Relatórios
   ========================================================================== */
import { store } from './store.js';
import {
  esc, money, horas, horasCurto, num, iniciais, maiuscula, plural,
  mesAno, nomeMes, dataLonga, dataBR, dataCurta, hora, diaChave,
  inicioDoMes, fimDoMes, somaMeses, somaDias, inicioDaSemana,
  paraInputLocal, deInputLocal, juntaDiaHora, deDiaChave,
  baixaArquivo, csvLinha, horasEntre, PERIODOS, HORARIOS_PERIODO,
  nomePeriodo, chaveMes, senhaPadrao,
} from './util.js';
import {
  $, $$, ICONE, el, abreFolha, confirma, torrada, carregando, vazio, comBotaoOcupado,
} from './ui.js';
import { PALETA, graficoDias, graficoPizza, tabelaDeApoio } from './charts.js';
import {
  pintaTrechos, agrega, horasDoTurno, valorDoTurno, somaBonus, totalComBonus,
  somaPagamentos, resumoDoMes, serieDoMes, agrupaBonus,
} from './metricas.js';
import {
  htmlRecibo, htmlReciboPessoa, htmlPizzas, pintaPizzas, htmlDetalheBonus, fatiasPorPessoa,
} from './extrato.js';
import {
  extraDoPeriodo, extraPorPessoa, htmlAlertaExtra, htmlRecadoExtraPessoa,
} from './hora-extra.js';

const ABAS = [
  { id: 'equipe',      nome: 'Equipe' },
  { id: 'empresas',    nome: 'Empresas' },
  { id: 'tarefas',     nome: 'Tarefas' },
  { id: 'turnos',      nome: 'Turnos' },
  { id: 'conferencia', nome: 'Conferência' },
  { id: 'importar',    nome: 'Importar' },
  { id: 'relatorios',  nome: 'Relatórios' },
];

export async function telaDeAdmin(raiz, ctx) {
  let aba = 'equipe';
  let pessoas = [], tarefas = [], atribuicoes = [];
  let empresas = [], atribEmpresas = [];
  let mesRef = inicioDoMes(new Date());
  let filtroPessoa = '';
  let pessoaFoco = null; // quando aba === 'visao'

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

  const rotuloDoTurno = (t) => {
    if ((t.pay_mode === 'shift' || t.period) && t.period) return `Turno ${nomePeriodo(t.period)}`;
    return [...new Set((t.segments || []).map((s) => s.task_name))].filter(Boolean).join(', ') || 'sem tarefa';
  };
  const rotuloModo = (modo) => {
    if (modo === 'shift') return { ficha: 'Por turno', dica: 'Manhã, tarde ou noite — valor fixo, não conta hora.' };
    if (modo === 'task') return { ficha: 'Por tarefa', dica: 'Valor fixo da tarefa, não multiplica pelas horas.' };
    return { ficha: 'Por hora', dica: 'Horas × o R$/h da tarefa desta pessoa.' };
  };
  const taxaDaTarefa = (task, modo, ratesT) => {
    const r = ratesT.find((x) => x.task_id === task.id);
    if (modo === 'task') return r?.flat_amount != null ? +r.flat_amount : +task.hourly_rate || 0;
    return r?.hourly_rate != null ? +r.hourly_rate : +task.hourly_rate || 0;
  };
  const taxaDoPeriodo = (period, ratesS) => +(ratesS.find((r) => r.period === period)?.amount || 0);
  const empresasPara = (userId) => {
    const suas = empresasDe(userId).filter((c) => c.active !== false);
    return suas.length ? suas : empresas.filter((c) => c.active);
  };
  const tarefasPara = (userId) => {
    const suas = tarefasDe(userId).filter((t) => t.active !== false);
    return suas.length ? suas : tarefas.filter((t) => t.active);
  };

  /* ======================================================================
     Casca com abas
     ====================================================================== */

  function desenha() {
    if (aba === 'visao' && pessoaFoco) {
      raiz.innerHTML = `
        <button class="btn btn-fantasma btn-medio" id="voltar-equipe" style="margin-bottom:12px">
          ${ICONE.esquerda}<span>Voltar à equipe</span>
        </button>
        <h1 class="secao-titulo" style="margin-bottom:4px">${esc(pessoaFoco.full_name)}</h1>
        <p class="apagado" style="margin-bottom:16px">@${esc(pessoaFoco.username)} · visão como a pessoa vê</p>
        <div id="conteudo-aba"></div>`;
      $('#voltar-equipe', raiz).addEventListener('click', () => {
        aba = 'equipe'; pessoaFoco = null; desenha();
      });
      abaVisaoPessoa($('#conteudo-aba', raiz), pessoaFoco);
      return;
    }

    raiz.innerHTML = `
      <h1 class="secao-titulo">Painel</h1>
      <div class="abas" role="tablist">
        ${ABAS.map((a) => `
          <button class="aba" role="tab" data-aba="${a.id}"
                  aria-selected="${a.id === aba}">${esc(a.nome)}</button>`).join('')}
      </div>
      <div id="conteudo-aba"></div>`;

    $$('[data-aba]', raiz).forEach((b) => {
      b.addEventListener('click', () => { aba = b.dataset.aba; pessoaFoco = null; desenha(); });
      if (b.dataset.aba === aba) {
        b.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
      }
    });

    const alvo = $('#conteudo-aba', raiz);
    ({
      equipe: abaEquipe, empresas: abaEmpresas, tarefas: abaTarefas, turnos: abaTurnos,
      conferencia: abaConferencia, importar: abaImportar, relatorios: abaRelatorios,
    }[aba])(alvo);
  }

  /* ======================================================================
     ABA: EQUIPE
     ====================================================================== */

  function abaEquipe(alvo) {
    alvo.innerHTML = `
      <div id="alerta-extra-equipe"></div>
      <button class="btn btn-primario btn-largo" id="nova-pessoa">
        ${ICONE.mais}<span>Cadastrar pessoa</span>
      </button>
      <div class="lista" style="margin-top:16px">
        ${pessoas.map(cartaoDaPessoa).join('')}
      </div>`;

    $('#nova-pessoa', alvo).addEventListener('click', () => editaPessoa(null));
    $$('[data-pessoa]', alvo).forEach((b) =>
      b.addEventListener('click', () => menuDaPessoa(pessoas.find((p) => p.id === b.dataset.pessoa))));

    const mesAgora = inicioDoMes(new Date());
    const ym = chaveMes(mesAgora);
    Promise.all([
      store.listaTurnos({ de: mesAgora, ate: fimDoMes(mesAgora) }),
      store.listaAvisosHoraExtra({ yearMonth: ym }).catch(() => []),
    ]).then(([brutos, avisos]) => {
      if (!$('#alerta-extra-equipe', alvo)) return;
      const extras = extraPorPessoa(pintaTrechos(brutos, tarefas), pessoas);
      $('#alerta-extra-equipe', alvo).innerHTML = htmlAlertaExtra(extras, {
        tituloMes: nomeMes(mesAgora),
        avisos: (avisos || []).length,
      });
      extras.forEach((e) => {
        if (!e.temExtra) return;
        const titulo = alvo.querySelector(`[data-pessoa="${e.user_id}"] .item-titulo`);
        if (titulo && !titulo.querySelector('[data-extra]')) {
          titulo.insertAdjacentHTML('beforeend', ` ${htmlRecadoExtraPessoa(e, { compacto: true })}`);
        }
      });
    }).catch(() => {});
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
          <button class="btn btn-primario btn-medio" data-visao>${ICONE.grafico}<span>Ver números (como ela vê)</span></button>
          <button class="btn btn-medio" data-empresas>${ICONE.predio}<span>Liberar empresas</span></button>
          <button class="btn btn-medio" data-tarefas>${ICONE.etiqueta}<span>Liberar tarefas</span></button>
          <button class="btn btn-medio" data-pagamento>${ICONE.engrenagem}<span>Como paga</span></button>
          <button class="btn btn-medio" data-bonus>${ICONE.etiqueta}<span>Bônus</span></button>
          <button class="btn btn-medio" data-edita>${ICONE.lapis}<span>Editar dados</span></button>
          <button class="btn btn-medio" data-senha>${ICONE.engrenagem}<span>Definir nova senha</span></button>
          <button class="btn btn-medio btn-perigo" data-apaga>${ICONE.lixo}<span>Remover do sistema</span></button>
        </div>`,
      aoMontar: (caixa, fechar) => {
        $('[data-visao]', caixa).addEventListener('click', () => {
          fechar(); pessoaFoco = p; aba = 'visao'; desenha();
        });
        $('[data-empresas]', caixa).addEventListener('click', () => { fechar(); liberaEmpresas(p); });
        $('[data-tarefas]', caixa).addEventListener('click', () => { fechar(); liberaTarefas(p); });
        $('[data-pagamento]', caixa).addEventListener('click', () => { fechar(); editaPagamento(p); });
        $('[data-bonus]', caixa).addEventListener('click', () => { fechar(); editaBonus(p); });
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

  async function editaBonus(p) {
    const ym = chaveMes(mesRef);
    let templates = [];
    let entries = [];

    async function carregaBonus() {
      [templates, entries] = await Promise.all([
        store.listaTemplatesBonus(p.id),
        store.listaBonusMes({ userId: p.id, yearMonth: ym }),
      ]);
    }

    function corpoBonus() {
      const soma = somaBonus(entries);
      return `
        <p class="campo-dica" style="margin-bottom:14px">
          Automático repete todo mês. Manual vale só em <strong>${esc(nomeMes(mesRef))}</strong>.
          O funcionário vê cada item separado e o total junto.
        </p>

        <h3 style="font-size:15px;margin:0 0 10px">Automáticos (todo mês)</h3>
        ${templates.length ? `<div class="lista" style="margin-bottom:12px">${templates.map((t) => `
          <div class="item" data-tpl="${esc(t.id)}" style="gap:10px">
            <span class="item-corpo" style="min-width:0;flex:1">
              <span class="item-titulo">${esc(t.title)}
                ${t.active ? '' : '<span class="ficha ficha-baixa" style="margin-left:6px;padding:2px 8px;font-size:11px">pausado</span>'}
              </span>
              <span class="item-sub">${esc(money(t.amount))} · automático</span>
            </span>
            <button class="btn btn-pequeno btn-fantasma" data-ed-tpl="${esc(t.id)}">Editar</button>
            <button class="btn btn-pequeno btn-fantasma" data-rm-tpl="${esc(t.id)}">${ICONE.lixo}</button>
          </div>`).join('')}</div>`
          : `<p class="apagado" style="margin:0 0 12px;font-size:14px">Nenhum bônus automático ainda.</p>`}
        <button class="btn btn-medio btn-largo" data-novo-tpl style="margin-bottom:20px">${ICONE.mais}<span>Novo automático</span></button>

        <h3 style="font-size:15px;margin:0 0 10px">Neste mês · ${esc(nomeMes(mesRef))}</h3>
        ${entries.length ? `<div class="lista" style="margin-bottom:12px">${entries.map((e) => `
          <div class="item" style="gap:10px">
            <span class="item-corpo" style="min-width:0;flex:1">
              <span class="item-titulo">${esc(e.title)}</span>
              <span class="item-sub">${e.bonus_on ? `${esc(dataBR(e.bonus_on))} · ` : ''}${esc(money(e.amount))} · ${e.source === 'auto' ? 'auto' : e.source === 'import' ? 'importado' : 'manual'}${e.note ? ` · ${esc(e.note)}` : ''}</span>
            </span>
            <button class="btn btn-pequeno btn-fantasma" data-ed-ent="${esc(e.id)}">Editar</button>
            <button class="btn btn-pequeno btn-fantasma" data-rm-ent="${esc(e.id)}">${ICONE.lixo}</button>
          </div>`).join('')}</div>`
          : `<p class="apagado" style="margin:0 0 12px;font-size:14px">Nenhum lançamento neste mês.</p>`}
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <span class="apagado" style="font-size:14px">Soma dos bônus</span>
          <strong class="num">${esc(money(soma))}</strong>
        </div>
        <button class="btn btn-primario btn-medio btn-largo" data-novo-ent>${ICONE.mais}<span>Lançar bônus neste mês</span></button>`;
    }

    function formBonus({ tituloFolha, sub, title = '', amount = '', note = '', mostraNota = false, active = null, datas = null, bonusOn = null, aoSalvar }) {
      const usaDatas = datas !== null || !!bonusOn;
      const datasIni = Array.isArray(datas) && datas.length
        ? datas.slice()
        : (bonusOn ? [String(bonusOn).slice(0, 10)] : [chaveMes(mesRef) + '-01']);
      // min/max do mês do painel
      const ymin = chaveMes(mesRef) + '-01';
      const ymax = (() => {
        const fim = fimDoMes(mesRef);
        return `${fim.getFullYear()}-${String(fim.getMonth() + 1).padStart(2, '0')}-${String(fim.getDate()).padStart(2, '0')}`;
      })();

      abreFolha({
        titulo: tituloFolha,
        sub,
        corpo: `
          <label class="campo"><span class="campo-rotulo">Título</span>
            <input class="entrada" id="b-titulo" value="${esc(title)}" placeholder="ex.: Comissão, Bônus noite"></label>
          <label class="campo"><span class="campo-rotulo">Valor (R$)</span>
            <input class="entrada" type="number" min="0" step="0.01" id="b-valor" value="${esc(amount)}" placeholder="ex.: 200"></label>
          ${usaDatas ? `
            <div class="campo">
              <span class="campo-rotulo">Datas em ${esc(nomeMes(mesRef))}</span>
              <span class="campo-dica">Mesmo título e valor em cada data. Toque em + para duplicar.</span>
              <div id="b-datas" style="display:flex;flex-direction:column;gap:8px;margin-top:8px">
                ${datasIni.map((d, i) => `
                  <div style="display:flex;gap:8px;align-items:center" data-linha-data>
                    <input class="entrada" type="date" data-data value="${esc(d)}" min="${esc(ymin)}" max="${esc(ymax)}" style="flex:1">
                    ${i === 0 ? '' : `<button type="button" class="btn btn-pequeno btn-fantasma" data-rm-data>${ICONE.lixo}</button>`}
                  </div>`).join('')}
              </div>
              <button type="button" class="btn btn-medio btn-largo" id="b-mais-data" style="margin-top:10px">
                ${ICONE.mais}<span>Mais uma data</span>
              </button>
            </div>` : ''}
          ${mostraNota ? `
            <label class="campo"><span class="campo-rotulo">Nota (opcional)</span>
              <input class="entrada" id="b-nota" value="${esc(note || '')}" placeholder="ex.: meta batida"></label>` : ''}
          ${active !== null ? `
            <label class="chave" style="margin-bottom:16px">
              <input type="checkbox" id="b-ativo" ${active ? 'checked' : ''}>
              <span class="chave-pista"></span>
              <span>Ativo — gera todo mês</span>
            </label>` : ''}
          <p class="campo-erro" id="b-erro" hidden></p>
          <button class="btn btn-primario btn-medio btn-largo" id="b-salva">Salvar</button>`,
        aoMontar: (caixa, fechar) => {
          const erro = $('#b-erro', caixa);
          const caixaDatas = $('#b-datas', caixa);

          function ligaRemover() {
            caixaDatas?.querySelectorAll('[data-rm-data]').forEach((b) => {
              b.onclick = () => { b.closest('[data-linha-data]')?.remove(); };
            });
          }
          ligaRemover();

          $('#b-mais-data', caixa)?.addEventListener('click', () => {
            if (!caixaDatas) return;
            const wrap = document.createElement('div');
            wrap.style.cssText = 'display:flex;gap:8px;align-items:center';
            wrap.setAttribute('data-linha-data', '');
            wrap.innerHTML = `
              <input class="entrada" type="date" data-data value="${esc(ymin)}" min="${esc(ymin)}" max="${esc(ymax)}" style="flex:1">
              <button type="button" class="btn btn-pequeno btn-fantasma" data-rm-data>${ICONE.lixo}</button>`;
            caixaDatas.appendChild(wrap);
            ligaRemover();
          });

          $('#b-salva', caixa).addEventListener('click', async (ev) => {
            erro.hidden = true;
            const tit = $('#b-titulo', caixa).value.trim();
            const val = $('#b-valor', caixa).value;
            if (!tit) { erro.textContent = 'Escreva o título.'; erro.hidden = false; return; }
            const dates = usaDatas
              ? [...caixa.querySelectorAll('[data-data]')].map((inp) => inp.value).filter(Boolean)
              : undefined;
            if (usaDatas && !dates.length) {
              erro.textContent = 'Escolha pelo menos uma data.'; erro.hidden = false; return;
            }
            try {
              await comBotaoOcupado(ev.currentTarget, 'Salvando…', () => aoSalvar({
                title: tit,
                amount: val === '' ? 0 : +val,
                note: mostraNota ? ($('#b-nota', caixa)?.value || null) : undefined,
                active: active !== null ? !!$('#b-ativo', caixa)?.checked : undefined,
                dates,
                bonus_on: dates?.length === 1 ? dates[0] : undefined,
              }));
              fechar();
            } catch (e) { erro.textContent = e.message; erro.hidden = false; }
          });
        },
      });
    }

    await carregaBonus();
    abreFolha({
      titulo: `Bônus · ${p.full_name.split(' ')[0]}`,
      sub: 'Título e valor — automático ou só neste mês.',
      corpo: `<div id="bonus-corpo">${corpoBonus()}</div>`,
      aoMontar: (caixa) => {
        const corpo = $('#bonus-corpo', caixa);

        async function redesenha() {
          await carregaBonus();
          corpo.innerHTML = corpoBonus();
          liga();
        }

        function liga() {
          $('[data-novo-tpl]', corpo)?.addEventListener('click', () => {
            formBonus({
              tituloFolha: 'Novo bônus automático',
              sub: 'Vai aparecer todo mês enquanto estiver ativo.',
              aoSalvar: async ({ title, amount }) => {
                await store.criaTemplateBonus({
                  user_id: p.id, title, amount, active: true,
                  sort_order: templates.length,
                });
                torrada('Automático criado.', 'bom');
                await redesenha();
              },
            });
          });

          corpo.querySelectorAll('[data-ed-tpl]').forEach((b) => {
            b.addEventListener('click', () => {
              const t = templates.find((x) => x.id === b.dataset.edTpl);
              if (!t) return;
              formBonus({
                tituloFolha: 'Editar automático',
                sub: 'Desligue “Ativo” para pausar nos próximos meses.',
                title: t.title, amount: t.amount, active: t.active,
                aoSalvar: async ({ title, amount, active }) => {
                  await store.atualizaTemplateBonus(t.id, { title, amount, active });
                  torrada('Automático atualizado.', 'bom');
                  await redesenha();
                },
              });
            });
          });

          corpo.querySelectorAll('[data-rm-tpl]').forEach((b) => {
            b.addEventListener('click', async () => {
              const t = templates.find((x) => x.id === b.dataset.rmTpl);
              if (!t) return;
              if (!await confirma({
                titulo: `Remover “${t.title}”?`,
                texto: 'Para de gerar nos próximos meses. Lançamentos já feitos neste mês continuam até você apagar.',
                ok: 'Remover', perigo: true,
              })) return;
              await store.apagaTemplateBonus(t.id);
              torrada('Automático removido.', 'bom');
              await redesenha();
            });
          });

          $('[data-novo-ent]', corpo)?.addEventListener('click', () => {
            formBonus({
              tituloFolha: 'Lançar bônus neste mês',
              sub: `Escolha as datas em ${nomeMes(mesRef)}. Mesmo título e valor — use + para repetir.`,
              mostraNota: true,
              datas: [chaveMes(mesRef) + '-01'],
              aoSalvar: async ({ title, amount, note, dates }) => {
                const criados = await store.lancaBonus({
                  user_id: p.id, title, amount, note, dates,
                });
                const n = Array.isArray(criados) ? criados.length : 1;
                torrada(n > 1 ? `${n} bônus lançados.` : 'Bônus lançado.', 'bom');
                await redesenha();
              },
            });
          });

          corpo.querySelectorAll('[data-ed-ent]').forEach((b) => {
            b.addEventListener('click', () => {
              const e = entries.find((x) => x.id === b.dataset.edEnt);
              if (!e) return;
              formBonus({
                tituloFolha: 'Editar lançamento',
                sub: e.source === 'auto' ? 'Veio do automático — ajuste só este lançamento.' : 'Altere título, valor ou data.',
                title: e.title, amount: e.amount, note: e.note, mostraNota: true,
                bonusOn: e.bonus_on || `${e.year_month}-01`,
                aoSalvar: async ({ title, amount, note, dates, bonus_on }) => {
                  const dia = (dates && dates[0]) || bonus_on || e.bonus_on;
                  await store.atualizaBonus(e.id, { title, amount, note, bonus_on: dia });
                  // se o usuário colocou mais de uma data no editar, lança as extras
                  if (dates && dates.length > 1) {
                    await store.lancaBonus({
                      user_id: p.id, title, amount, note, dates: dates.slice(1),
                    });
                  }
                  torrada('Lançamento atualizado.', 'bom');
                  await redesenha();
                },
              });
            });
          });

          corpo.querySelectorAll('[data-rm-ent]').forEach((b) => {
            b.addEventListener('click', async () => {
              const e = entries.find((x) => x.id === b.dataset.rmEnt);
              if (!e) return;
              if (!await confirma({
                titulo: `Apagar “${e.title}” deste mês?`,
                texto: e.source === 'auto'
                  ? 'Some só deste mês. No próximo o automático pode gerar de novo.'
                  : 'Some só deste mês.',
                ok: 'Apagar', perigo: true,
              })) return;
              await store.apagaBonus(e.id);
              torrada('Lançamento apagado.', 'bom');
              await redesenha();
            });
          });
        }
        liga();
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
            <input class="entrada" id="f-senha" type="text" placeholder="ex.: maria321*">
            <span class="campo-dica">Padrão: usuário + 321*. Ela pode trocar depois no próprio perfil.</span></label>` : ''}
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
        const campoUser = $('#f-user', caixa);
        const campoSenha = $('#f-senha', caixa);
        campoUser?.addEventListener('input', () => {
          if (!campoSenha || campoSenha.dataset.tocado) return;
          const u = campoUser.value.trim().toLowerCase();
          campoSenha.value = u ? senhaPadrao(u) : '';
        });
        campoSenha?.addEventListener('input', () => { campoSenha.dataset.tocado = '1'; });
        $('#f-salva', caixa).addEventListener('click', async (ev) => {
          erro.hidden = true;
          const nome = $('#f-nome', caixa).value.trim();
          const papel = $('#f-papel', caixa).value;
          if (!nome) { erro.textContent = 'Escreva o nome da pessoa.'; erro.hidden = false; return; }
          try {
            if (novo) {
              const user = $('#f-user', caixa).value.trim().toLowerCase();
              const senha = $('#f-senha', caixa).value.trim() || senhaPadrao(user);
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
      sub: `Padrão da equipe: ${p.username}321*. Ela também pode trocar no próprio perfil.`,
      corpo: `
        <label class="campo"><span class="campo-rotulo">Senha</span>
          <input class="entrada" id="p-senha" type="text" placeholder="${esc(senhaPadrao(p.username))}" value="${esc(senhaPadrao(p.username))}"></label>
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
    const grupos = [];
    for (const t of turnos) {
      const k = diaChave(t.started_at);
      const ultimo = grupos[grupos.length - 1];
      if (!ultimo || ultimo.chave !== k) grupos.push({ chave: k, data: t.started_at, itens: [t] });
      else ultimo.itens.push(t);
    }

    const htmlItem = (t) => `
      <button class="item clicavel" data-turno="${esc(t.id)}">
        <span class="item-faixa" style="background:${esc(t.segments?.[0]?.cor || PALETA[0])}"></span>
        <span class="item-corpo">
          <span class="item-titulo">${esc(nomeDe(t.user_id))}
            ${t.ended_at ? '' : '<span class="ficha ficha-alta" style="margin-left:6px;padding:2px 8px;font-size:11px">em turno</span>'}</span>
          <span class="item-sub">${esc(hora(t.started_at))} → ${t.ended_at ? esc(hora(t.ended_at)) : '—'} ·
            ${t.company_name ? `${esc(t.company_name)} · ` : ''}${esc(rotuloDoTurno(t))}
            ${t.source === 'import' ? ' · importado' : t.source === 'manual' ? ' · manual' : ''}</span>
        </span>
        <span class="item-fim">
          <span class="num" style="font-weight:600">${esc(horasCurto(horasDoTurno(t)))}</span>
          <span class="num apagado" style="display:block;font-size:12px">${esc(money(valorDoTurno(t)))}</span>
        </span>
      </button>`;

    const extrasMes = extraPorPessoa(turnos, pessoas);
    const avisosPromessa = store.listaAvisosHoraExtra({ yearMonth: chaveMes(mesRef) }).catch(() => []);

    alvo.innerHTML = `
      ${barraDeFiltro({ sticky: true })}
      <div id="alerta-extra-turnos">${htmlAlertaExtra(extrasMes, { tituloMes: nomeMes(mesRef) })}</div>
      ${abertos.length ? `
        <div class="recado" style="margin-bottom:16px">
          <span class="recado-emoji">⏳</span>
          <span><strong>${esc(plural(abertos.length, 'turno em aberto', 'turnos em aberto'))}</strong> —
                ${esc(abertos.map((t) => nomeDe(t.user_id)).join(', '))}.
                Toque no turno para corrigir a hora de saída.</span>
        </div>` : ''}
      <button class="btn btn-primario btn-largo" id="novo-turno">
        ${ICONE.mais}<span>Lançar horários na mão</span>
      </button>
      <div class="lista" style="margin-top:16px">
        ${grupos.length ? grupos.map((g) => `
          <div class="turno-dia-cabeca">${esc(maiuscula(dataLonga(g.data)))}</div>
          ${g.itens.map(htmlItem).join('')}
        `).join('')
          : vazio({ emoji: '📭', titulo: 'Nenhum turno neste mês',
                    texto: 'Mude o mês, tire o filtro de pessoa, ou lance um turno na mão.' })}
      </div>`;

    ligaFiltro(alvo, abaTurnos);
    $('#novo-turno', alvo).addEventListener('click', () => editaTurno(null));
    $$('[data-turno]', alvo).forEach((b) =>
      b.addEventListener('click', () => editaTurno(turnos.find((t) => t.id === b.dataset.turno))));
    avisosPromessa.then((avisos) => {
      const caixa = $('#alerta-extra-turnos', alvo);
      if (caixa) {
        caixa.innerHTML = htmlAlertaExtra(extrasMes, {
          tituloMes: nomeMes(mesRef), avisos: (avisos || []).length,
        });
      }
    });
  }

  function editaTurno(t, opts = {}) {
    if (t) return corrigeTurno(t, opts);
    return lancaVarios(opts);
  }

  async function aposSalvarTurno(fechar) {
    fechar();
    if (aba === 'visao' && pessoaFoco) {
      await abaVisaoPessoa($('#conteudo-aba', raiz), pessoaFoco);
    } else {
      desenha();
    }
  }

  function lancaVarios(opts = {}) {
    const userFixo = opts.userId || null;
    const gente = pessoas.filter((p) => p.active !== false || p.id === userFixo);
    if (!gente.length) { torrada('Cadastre alguém antes de lançar turnos.', 'ruim', 5); return; }
    if (!empresas.filter((x) => x.active).length) {
      torrada('Cadastre uma empresa antes de lançar turnos.', 'ruim', 5); return;
    }

    const hoje = new Date();
    let userId = userFixo || gente[0].id;
    let empresaId = '';
    let tarefaId = '';
    let ratesT = [];
    let ratesS = [];
    let padraoIni = '08:00';
    let padraoFim = '17:00';
    let semanaRef = inicioDaSemana(chaveMes(mesRef) === chaveMes(hoje) ? hoje : mesRef);
    const dias = {};
    const LETRAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];

    const modoDe = () => pessoas.find((p) => p.id === userId)?.pay_mode || 'hourly';
    const moldaDia = (modo) => (modo === 'shift'
      ? { periodos: new Set() }
      : { ini: padraoIni, fim: padraoFim });

    const kHoje = diaChave(hoje);
    if ([0, 1, 2, 3, 4, 5, 6].some((i) => diaChave(somaDias(semanaRef, i)) === kHoje)) {
      dias[kHoje] = moldaDia(modoDe());
    }

    abreFolha({
      titulo: 'Lançar horários',
      sub: 'Toque nos dias da semana. O formulário muda se a pessoa ganha por hora, por tarefa ou por turno.',
      corpo: '<div id="lanca-raiz"><p class="apagado" style="padding:22px;text-align:center">Montando…</p></div>',
      aoMontar: async (caixa, fechar) => {
        const raizL = $('#lanca-raiz', caixa);

        async function carregaTaxas() {
          [ratesT, ratesS] = await Promise.all([
            store.listaTaxasTarefa(userId),
            store.listaTaxasTurno(userId),
          ]);
        }

        function nItens(modo) {
          let n = 0;
          for (const d of Object.values(dias)) {
            n += modo === 'shift' ? (d.periodos?.size || 0) : 1;
          }
          return n;
        }

        function pinta() {
          const p = pessoas.find((x) => x.id === userId) || gente[0];
          const modo = p?.pay_mode || 'hourly';
          const info = rotuloModo(modo);
          const sedes = empresasPara(userId);
          const tars = tarefasPara(userId);
          if (!sedes.some((s) => s.id === empresaId)) empresaId = sedes[0]?.id || '';
          if (!tars.some((t) => t.id === tarefaId)) tarefaId = tars[0]?.id || '';
          const subEl = caixa.closest('.folha')?.querySelector('.folha-sub');
          if (subEl) subEl.textContent = info.dica;

          const diasSem = Array.from({ length: 7 }, (_, i) => {
            const d = somaDias(semanaRef, i);
            return { d, k: diaChave(d), letra: LETRAS[i] };
          });
          const chaves = Object.keys(dias).sort();
          const itens = nItens(modo);

          const optsTarefa = tars.map((x) => {
            const v = taxaDaTarefa(x, modo, ratesT);
            const preco = modo === 'task' ? `${money(v)} fixo` : `${money(v)}/h`;
            return `<option value="${esc(x.id)}" ${x.id === tarefaId ? 'selected' : ''}>${esc(x.name)} — ${esc(preco)}</option>`;
          }).join('');

          raizL.innerHTML = `
            <label class="campo"><span class="campo-rotulo">De quem é</span>
              <select class="entrada" id="v-pessoa" ${userFixo ? 'disabled' : ''}>
                ${gente.map((x) => `<option value="${esc(x.id)}" ${x.id === userId ? 'selected' : ''}>${esc(x.full_name)}</option>`).join('')}
              </select></label>
            <div class="lanca-modo">
              <span class="ficha ficha-viva">${esc(info.ficha)}</span>
              <span class="apagado" style="font-size:13px">${esc(info.dica)}</span>
            </div>
            <label class="campo"><span class="campo-rotulo">Empresa / sede</span>
              <select class="entrada" id="v-empresa">
                ${sedes.map((x) => `<option value="${esc(x.id)}" ${x.id === empresaId ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}
              </select></label>
            ${modo === 'shift' ? '' : `
              <label class="campo"><span class="campo-rotulo">${modo === 'task' ? 'Tarefa (valor fixo)' : 'Tarefa (R$/h)'}</span>
                <select class="entrada" id="v-tarefa">${optsTarefa}</select>
                ${tars.length ? '' : '<span class="campo-dica">Libere uma tarefa nesta pessoa antes de lançar.</span>'}
              </label>
              <div class="grade-campos">
                <label class="campo"><span class="campo-rotulo">Entrada padrão</span>
                  <input class="entrada" id="lanca-pad-ini" type="time" value="${esc(padraoIni)}"></label>
                <label class="campo"><span class="campo-rotulo">Saída padrão</span>
                  <input class="entrada" id="lanca-pad-fim" type="time" value="${esc(padraoFim)}"></label>
              </div>
              <div class="lanca-atalhos">
                <button type="button" class="lanca-atalho" id="lanca-aplica-padrao">Usar nesses dias</button>
              </div>`}
            <div class="lanca-semana-nav">
              <button type="button" class="mes-nav-btn" id="lanca-sem-ant" aria-label="Semana anterior">${ICONE.esquerda}</button>
              <div class="lanca-semana-tit"><strong>${esc(dataCurta(diasSem[0].d))} – ${esc(dataCurta(diasSem[6].d))}</strong></div>
              <button type="button" class="mes-nav-btn" id="lanca-sem-prox" aria-label="Próxima semana">${ICONE.direita}</button>
            </div>
            <div class="lanca-atalhos">
              <button type="button" class="lanca-atalho" id="lanca-uteis">Seg a sex</button>
              <button type="button" class="lanca-atalho" id="lanca-limpa">Limpar</button>
            </div>
            <div class="lanca-semana">
              ${diasSem.map(({ d, k, letra }) => `
                <button type="button" class="lanca-dia ${dias[k] ? 'on' : ''} ${k === kHoje ? 'hoje' : ''}" data-lanca-dia="${esc(k)}">
                  <span class="lanca-dia-letra">${esc(letra)}</span>
                  <span class="lanca-dia-num">${d.getDate()}</span>
                </button>`).join('')}
            </div>
            <p class="campo-dica" style="margin-top:-6px">${esc(plural(chaves.length, 'dia marcado', 'dias marcados'))}${itens ? ` · ${esc(plural(itens, 'turno', 'turnos'))}` : ''}</p>
            ${chaves.map((k) => {
              const d = deDiaChave(k);
              const infoDia = dias[k];
              if (modo === 'shift') {
                const vazioPer = !infoDia.periodos?.size;
                return `
                  <div class="lanca-cartao-dia ${vazioPer ? 'warn' : ''}" data-cartao-dia="${esc(k)}">
                    <div class="lanca-cartao-topo">${esc(maiuscula(dataLonga(d)))}
                      <button type="button" class="lanca-cartao-tira" data-tira-dia="${esc(k)}">tirar</button></div>
                    <div class="lanca-periodos">
                      ${PERIODOS.map((per) => {
                        const on = infoDia.periodos?.has(per.id);
                        const hor = HORARIOS_PERIODO[per.id];
                        return `<button type="button" class="lanca-per ${on ? 'on' : ''}" data-dia="${esc(k)}" data-per="${esc(per.id)}">
                          <span class="lanca-per-nome">${esc(per.nome)}</span>
                          <span class="lanca-per-preco">${esc(money(taxaDoPeriodo(per.id, ratesS)))} · ${esc(hor.ini)}–${esc(hor.fim)}</span>
                        </button>`;
                      }).join('')}
                    </div>
                  </div>`;
              }
              return `
                <div class="lanca-cartao-dia" data-cartao-dia="${esc(k)}">
                  <div class="lanca-cartao-topo">${esc(maiuscula(dataLonga(d)))}
                    <button type="button" class="lanca-cartao-tira" data-tira-dia="${esc(k)}">tirar</button></div>
                  <div class="lanca-horas">
                    <label class="campo" style="margin:0"><span class="campo-rotulo">Entrada</span>
                      <input class="entrada" type="time" data-ini value="${esc(infoDia.ini || padraoIni)}"></label>
                    <label class="campo" style="margin:0"><span class="campo-rotulo">Saída</span>
                      <input class="entrada" type="time" data-fim value="${esc(infoDia.fim || '')}">
                      <span class="campo-dica">Vazio = em aberto</span></label>
                  </div>
                </div>`;
            }).join('')}
            <p class="campo-erro" id="v-erro" hidden></p>
            <div class="linha-botoes">
              <button class="btn btn-primario btn-medio" id="v-salva">${itens > 1 ? `Lançar ${itens} turnos` : 'Lançar'}</button>
            </div>`;

          liga();
        }

        function liga() {
          const modo = modoDe();
          $('#v-pessoa', raizL)?.addEventListener('change', async (ev) => {
            userId = ev.target.value;
            empresaId = '';
            tarefaId = '';
            for (const k of Object.keys(dias)) dias[k] = moldaDia(modoDe());
            raizL.innerHTML = '<p class="apagado" style="padding:22px;text-align:center">Atualizando…</p>';
            await carregaTaxas();
            pinta();
          });
          $('#v-empresa', raizL)?.addEventListener('change', (ev) => { empresaId = ev.target.value; });
          $('#v-tarefa', raizL)?.addEventListener('change', (ev) => { tarefaId = ev.target.value; });
          $('#lanca-pad-ini', raizL)?.addEventListener('change', (ev) => { padraoIni = ev.target.value || '08:00'; });
          $('#lanca-pad-fim', raizL)?.addEventListener('change', (ev) => { padraoFim = ev.target.value || ''; });
          $('#lanca-aplica-padrao', raizL)?.addEventListener('click', () => {
            padraoIni = $('#lanca-pad-ini', raizL)?.value || padraoIni;
            padraoFim = $('#lanca-pad-fim', raizL)?.value || padraoFim;
            for (const k of Object.keys(dias)) {
              if (dias[k] && modo !== 'shift') { dias[k].ini = padraoIni; dias[k].fim = padraoFim; }
            }
            pinta();
          });
          $('#lanca-sem-ant', raizL)?.addEventListener('click', () => { semanaRef = somaDias(semanaRef, -7); pinta(); });
          $('#lanca-sem-prox', raizL)?.addEventListener('click', () => { semanaRef = somaDias(semanaRef, 7); pinta(); });
          $('#lanca-uteis', raizL)?.addEventListener('click', () => {
            for (let i = 0; i < 5; i++) {
              const k = diaChave(somaDias(semanaRef, i));
              if (!dias[k]) dias[k] = moldaDia(modo);
            }
            pinta();
          });
          $('#lanca-limpa', raizL)?.addEventListener('click', () => {
            for (const k of Object.keys(dias)) delete dias[k];
            pinta();
          });
          $$('[data-lanca-dia]', raizL).forEach((b) => b.addEventListener('click', () => {
            const k = b.dataset.lancaDia;
            if (dias[k]) delete dias[k];
            else dias[k] = moldaDia(modo);
            pinta();
          }));
          $$('[data-tira-dia]', raizL).forEach((b) => b.addEventListener('click', () => {
            delete dias[b.dataset.tiraDia];
            pinta();
          }));
          $$('[data-per]', raizL).forEach((b) => b.addEventListener('click', () => {
            const k = b.dataset.dia;
            if (!dias[k]) dias[k] = moldaDia('shift');
            const set = dias[k].periodos;
            if (set.has(b.dataset.per)) set.delete(b.dataset.per);
            else set.add(b.dataset.per);
            pinta();
          }));
          $$('[data-ini]', raizL).forEach((inp) => inp.addEventListener('change', () => {
            const k = inp.closest('[data-cartao-dia]')?.dataset.cartaoDia;
            if (k && dias[k]) dias[k].ini = inp.value;
          }));
          $$('[data-fim]', raizL).forEach((inp) => inp.addEventListener('change', () => {
            const k = inp.closest('[data-cartao-dia]')?.dataset.cartaoDia;
            if (k && dias[k]) dias[k].fim = inp.value;
          }));
          $('#v-salva', raizL)?.addEventListener('click', (ev) => salvar(ev.currentTarget));
        }

        async function salvar(botao) {
          const erro = $('#v-erro', raizL);
          erro.hidden = true;
          const p = pessoas.find((x) => x.id === userId);
          const modo = p?.pay_mode || 'hourly';
          const emp = empresas.find((x) => x.id === ($('#v-empresa', raizL)?.value || empresaId));
          if (!emp) { erro.textContent = 'Escolha a empresa.'; erro.hidden = false; return; }
          const chaves = Object.keys(dias).sort();
          if (!chaves.length) { erro.textContent = 'Toque em pelo menos um dia.'; erro.hidden = false; return; }

          const payloads = [];
          try {
            if (modo === 'shift') {
              for (const k of chaves) {
                const pers = [...(dias[k].periodos || [])];
                if (!pers.length) {
                  throw new Error(`Marque manhã, tarde ou noite em ${dataLonga(deDiaChave(k))}.`);
                }
                const base = deDiaChave(k);
                for (const per of pers) {
                  const hor = HORARIOS_PERIODO[per];
                  const de = juntaDiaHora(base, hor.ini);
                  const ate = juntaDiaHora(base, hor.fim);
                  const valor = taxaDoPeriodo(per, ratesS);
                  payloads.push({
                    user_id: userId, company_id: emp.id, company_name: emp.name,
                    started_at: de, ended_at: ate, source: 'manual',
                    pay_mode: 'shift', period: per, flat_amount: valor,
                    trechos: [{
                      task_id: null, task_name: `Turno ${nomePeriodo(per)}`,
                      hourly_rate: 0, flat_amount: null, period: per,
                      started_at: de, ended_at: ate,
                    }],
                  });
                }
              }
            } else {
              const tar = tarefas.find((x) => x.id === ($('#v-tarefa', raizL)?.value || tarefaId));
              if (!tar) throw new Error('Escolha a tarefa.');
              for (const k of chaves) {
                const base = deDiaChave(k);
                const de = juntaDiaHora(base, dias[k].ini || padraoIni);
                const ate = dias[k].fim ? juntaDiaHora(base, dias[k].fim) : null;
                if (ate && ate < de) throw new Error(`A saída de ${dataLonga(base)} precisa ser depois da entrada.`);
                if (modo === 'task') {
                  const fixo = taxaDaTarefa(tar, 'task', ratesT);
                  payloads.push({
                    user_id: userId, company_id: emp.id, company_name: emp.name,
                    started_at: de, ended_at: ate, source: 'manual',
                    pay_mode: 'task', period: null, flat_amount: null,
                    trechos: [{
                      task_id: tar.id, task_name: tar.name,
                      hourly_rate: 0, flat_amount: fixo,
                      started_at: de, ended_at: ate,
                    }],
                  });
                } else {
                  const taxa = taxaDaTarefa(tar, 'hourly', ratesT);
                  payloads.push({
                    user_id: userId, company_id: emp.id, company_name: emp.name,
                    started_at: de, ended_at: ate, source: 'manual',
                    pay_mode: 'hourly', period: null, flat_amount: null,
                    trechos: [{
                      task_id: tar.id, task_name: tar.name,
                      hourly_rate: taxa, flat_amount: null,
                      started_at: de, ended_at: ate,
                    }],
                  });
                }
              }
            }
            const abertos = payloads.filter((x) => !x.ended_at);
            if (abertos.length > 1) {
              throw new Error('Só pode um turno em aberto. Preencha a saída nos outros dias.');
            }
          } catch (e) { erro.textContent = e.message; erro.hidden = false; return; }

          try {
            await comBotaoOcupado(botao, 'Lançando…', async () => {
              let feitos = 0;
              for (const pl of payloads) {
                try {
                  await store.gravaTurnoManual(pl);
                  feitos += 1;
                } catch (e) {
                  throw new Error(feitos
                    ? `${feitos} lançados, depois falhou: ${e.message}`
                    : e.message);
                }
              }
            });
            await aposSalvarTurno(fechar);
            torrada(payloads.length > 1
              ? `${payloads.length} horários lançados.`
              : 'Horário lançado.', 'bom');
          } catch (e) { erro.textContent = e.message; erro.hidden = false; }
        }

        await carregaTaxas();
        pinta();
      },
    });
  }

  function corrigeTurno(t, opts = {}) {
    const p = pessoas.find((x) => x.id === t.user_id);
    const modo = t.pay_mode || p?.pay_mode || 'hourly';
    const ini = new Date(t.started_at);
    const fim = t.ended_at ? new Date(t.ended_at) : null;
    const empresaAtual = t.company_id || empresasPara(t.user_id)[0]?.id || '';
    const tarefaAtual = t.segments?.[0]?.task_id || tarefasPara(t.user_id)[0]?.id || '';
    const periodoAtual = t.period || t.segments?.[0]?.period || 'manha';
    const info = rotuloModo(modo);

    abreFolha({
      titulo: 'Corrigir turno',
      sub: info.dica,
      corpo: '<div id="corrige-raiz"><p class="apagado" style="padding:22px;text-align:center">Carregando…</p></div>',
      aoMontar: async (caixa, fechar) => {
        const raizC = $('#corrige-raiz', caixa);
        const [ratesT, ratesS] = await Promise.all([
          store.listaTaxasTarefa(t.user_id),
          store.listaTaxasTurno(t.user_id),
        ]);
        const sedes = empresasPara(t.user_id);
        const tars = tarefasPara(t.user_id);
        const optsTarefa = tars.map((x) => {
          const v = taxaDaTarefa(x, modo, ratesT);
          const preco = modo === 'task' ? `${money(v)} fixo` : `${money(v)}/h`;
          return `<option value="${esc(x.id)}" ${x.id === tarefaAtual ? 'selected' : ''}>${esc(x.name)} — ${esc(preco)}</option>`;
        }).join('');

        raizC.innerHTML = `
          <label class="campo"><span class="campo-rotulo">De quem é o turno</span>
            <select class="entrada" disabled>
              <option>${esc(p?.full_name || 'Alguém')}</option>
            </select></label>
          <div class="lanca-modo">
            <span class="ficha ficha-viva">${esc(info.ficha)}</span>
          </div>
          <label class="campo"><span class="campo-rotulo">Empresa / sede</span>
            <select class="entrada" id="v-empresa">
              ${sedes.map((x) => `<option value="${esc(x.id)}" ${x.id === empresaAtual ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}
            </select></label>
          ${modo === 'shift' ? `
            <p class="campo-rotulo">Período</p>
            <div class="lanca-periodos" style="margin-bottom:16px" id="v-periodos">
              ${PERIODOS.map((per) => `
                <button type="button" class="lanca-per ${per.id === periodoAtual ? 'on' : ''}" data-per="${esc(per.id)}">
                  <span class="lanca-per-nome">${esc(per.nome)}</span>
                  <span class="lanca-per-preco">${esc(money(taxaDoPeriodo(per.id, ratesS)))}</span>
                </button>`).join('')}
            </div>` : `
            <label class="campo"><span class="campo-rotulo">${modo === 'task' ? 'Tarefa (valor fixo)' : 'Tarefa (R$/h)'}</span>
              <select class="entrada" id="v-tarefa">${optsTarefa}</select></label>`}
          <div class="grade-campos">
            <label class="campo"><span class="campo-rotulo">Entrada</span>
              <input class="entrada" id="v-ini" type="datetime-local" value="${esc(paraInputLocal(ini))}"></label>
            <label class="campo"><span class="campo-rotulo">Saída</span>
              <input class="entrada" id="v-fim" type="datetime-local" value="${fim ? esc(paraInputLocal(fim)) : ''}">
              <span class="campo-dica">Deixe vazio para manter em aberto.</span></label>
          </div>
          <p class="campo-erro" id="v-erro" hidden></p>
          <div class="linha-botoes">
            <button class="btn btn-medio btn-perigo" id="v-apaga">Apagar turno</button>
            <button class="btn btn-primario btn-medio" id="v-salva">Salvar</button>
          </div>`;

        let periodo = periodoAtual;
        $$('[data-per]', raizC).forEach((b) => b.addEventListener('click', () => {
          periodo = b.dataset.per;
          $$('[data-per]', raizC).forEach((x) => x.classList.toggle('on', x === b));
        }));

        $('#v-salva', raizC).addEventListener('click', async (ev) => {
          const erro = $('#v-erro', raizC);
          erro.hidden = true;
          const de = deInputLocal($('#v-ini', raizC).value);
          const ate = deInputLocal($('#v-fim', raizC).value);
          const emp = empresas.find((x) => x.id === $('#v-empresa', raizC).value);
          if (!de) { erro.textContent = 'Informe a hora de entrada.'; erro.hidden = false; return; }
          if (ate && ate < de) { erro.textContent = 'A saída precisa ser depois da entrada.'; erro.hidden = false; return; }
          if (!emp) { erro.textContent = 'Escolha a empresa.'; erro.hidden = false; return; }
          let patch;
          if (modo === 'shift') {
            const valor = taxaDoPeriodo(periodo, ratesS);
            patch = {
              started_at: de, ended_at: ate,
              company_id: emp.id, company_name: emp.name,
              pay_mode: 'shift', period: periodo, flat_amount: valor,
              trechos: [{
                task_id: null, task_name: `Turno ${nomePeriodo(periodo)}`,
                hourly_rate: 0, flat_amount: null, period: periodo,
                started_at: de, ended_at: ate,
              }],
            };
          } else {
            const tar = tarefas.find((x) => x.id === $('#v-tarefa', raizC).value);
            if (!tar) { erro.textContent = 'Escolha a tarefa.'; erro.hidden = false; return; }
            const trecho = modo === 'task'
              ? {
                task_id: tar.id, task_name: tar.name, hourly_rate: 0,
                flat_amount: taxaDaTarefa(tar, 'task', ratesT),
                started_at: de, ended_at: ate,
              }
              : {
                task_id: tar.id, task_name: tar.name,
                hourly_rate: taxaDaTarefa(tar, 'hourly', ratesT),
                flat_amount: null, started_at: de, ended_at: ate,
              };
            patch = {
              started_at: de, ended_at: ate,
              company_id: emp.id, company_name: emp.name,
              pay_mode: modo, period: null, flat_amount: null,
              trechos: [trecho],
            };
          }
          try {
            await comBotaoOcupado(ev.currentTarget, 'Salvando…', () => store.atualizaTurno(t.id, patch));
            await aposSalvarTurno(fechar);
            torrada('Turno corrigido.', 'bom');
          } catch (e) { erro.textContent = e.message; erro.hidden = false; }
        });

        $('#v-apaga', raizC).addEventListener('click', async () => {
          if (!await confirma({ titulo: 'Apagar este turno?', texto: 'As horas somem do relatório. Não dá para desfazer.', ok: 'Apagar', perigo: true })) return;
          try {
            await store.apagaTurno(t.id);
            await aposSalvarTurno(fechar);
            torrada('Turno apagado.', 'bom');
          } catch (e) { torrada(e.message, 'ruim', 6); }
        });
      },
    });
  }

  /* ======================================================================
     ABA: VISÃO DA PESSOA (como ela vê + editar horários)
     ====================================================================== */

  async function abaVisaoPessoa(alvo, p) {
    alvo.innerHTML = carregando('Carregando números…');
    const ym = chaveMes(mesRef);
    const [turnosBrutos, bonusMes, pagamentos] = await Promise.all([
      store.listaTurnos({ userId: p.id }),
      store.listaBonusMes({ userId: p.id, yearMonth: ym }),
      store.listaPagamentos({ userId: p.id }),
    ]);
    const turnos = pintaTrechos(turnosBrutos, tarefas);
    const r = resumoDoMes(turnos, mesRef);
    const grupos = agrupaBonus(bonusMes);
    const total = totalComBonus(r.valor, bonusMes);
    const pagsMes = pagamentos.filter((x) => x.year_month === ym);
    const pagoMes = somaPagamentos(pagsMes);
    const noMes = turnos.filter((t) => {
      const d = new Date(t.started_at);
      return d >= inicioDoMes(mesRef) && d <= fimDoMes(mesRef);
    });
    const planilha = (await store.listaTotaisPlanilha({ userId: p.id, yearMonth: ym }))[0];
    const esperado = planilha ? +planilha.expected_total : null;
    const diff = esperado != null ? total - esperado : null;
    const taxaGeral = r.horas > 0.001 ? total / r.horas : 0;

    alvo.innerHTML = `
      ${htmlSeletorMes()}

      <div style="display:flex;flex-direction:column;gap:10px;margin-bottom:16px">
        <button class="btn btn-primario btn-largo" id="v-novo-turno">
          ${ICONE.mais}<span>Lançar horários</span>
        </button>
        <button class="btn btn-medio btn-largo" id="v-novo-pag">
          ${ICONE.mais}<span>Registrar pagamento / recebimento</span>
        </button>
      </div>

      <section class="cartao">
        <div class="heroi">
          <p class="heroi-rotulo">Total a receber em ${esc(nomeMes(mesRef))}</p>
          <p class="heroi-valor saldo">${esc(money(total))}</p>
          <div class="heroi-nota">
            <span class="ficha ficha-neutra">${esc(horas(r.horas))} · média ${esc(money(taxaGeral))}/h</span>
            ${htmlRecadoExtraPessoa(extraDoPeriodo(noMes), { compacto: true })}
          </div>
        </div>
        ${htmlRecibo({ horasMes: r.horas, trabalho: r.valor, grupos, total, pago: pagoMes })}
        ${htmlDetalheBonus(bonusMes)}
      </section>

      ${htmlRecadoExtraPessoa(extraDoPeriodo(noMes), { nomeMes: nomeMes(mesRef) })}

      ${esperado != null ? `
        <div class="recado ${Math.abs(diff) < 0.5 ? '' : 'ruim'}" style="margin-top:14px">
          <span class="recado-emoji">${Math.abs(diff) < 0.5 ? '✅' : '⚠️'}</span>
          <span>Planilha: <strong>${esc(money(esperado))}</strong> · App: <strong>${esc(money(total))}</strong>
            · diferença <strong>${esc(money(diff))}</strong>
            ${Math.abs(diff) >= 0.5 ? ' — confira extras/horários que escaparam.' : ' — batendo.'}</span>
        </div>` : ''}

      <section class="cartao" style="margin-top:16px">
        ${htmlPizzas()}
      </section>

      <section class="cartao" style="margin-top:16px">
        <div class="cartao-topo"><h2 class="cartao-titulo">Pagamentos / recebimentos</h2>
          <span class="apagado">${esc(plural(pagamentos.length, 'lançamento', 'lançamentos'))}</span></div>
        ${pagamentos.length ? `<div class="lista">${pagamentos.slice(0, 40).map((pg) => `
          <button class="item clicavel" data-pag="${esc(pg.id)}">
            <div class="item-corpo">
              <div class="item-titulo">${esc(pg.title)}</div>
              <div class="item-sub">${esc(dataBR(pg.paid_on))} · ${esc(pg.year_month)}
                ${pg.source === 'import' ? ' · importado' : ''}
                ${pg.note ? ` · ${esc(String(pg.note).slice(0, 60))}` : ''}</div>
            </div>
            <div class="num" style="font-weight:600">${esc(money(pg.amount))}</div>
          </button>`).join('')}</div>`
          : vazio({ emoji: '💸', titulo: 'Nenhum pagamento registrado',
                    texto: 'Importe das planilhas ou lance na mão.' })}
      </section>

      <section class="cartao" style="margin-top:16px">
        <div class="cartao-topo"><h2 class="cartao-titulo">Turnos do mês</h2>
          <span class="apagado">${esc(plural(noMes.length, 'turno', 'turnos'))}</span></div>
        <div class="grafico" id="vp-dias"></div>
        <div id="vp-tabela"></div>
        ${noMes.length ? `<div class="lista" style="margin-top:12px">${noMes.map((t) => `
          <button class="item clicavel" data-turno="${esc(t.id)}">
            <span class="item-faixa" style="background:${esc(t.segments?.[0]?.cor || PALETA[0])}"></span>
            <span class="item-corpo">
              <span class="item-titulo">${esc(maiuscula(dataLonga(t.started_at)))}</span>
              <span class="item-sub">${esc(hora(t.started_at))} → ${t.ended_at ? esc(hora(t.ended_at)) : '—'}
                ${t.company_name ? ` · ${esc(t.company_name)}` : ''}
                · ${esc(rotuloDoTurno(t))}</span>
            </span>
            <span class="item-fim">
              <span class="num" style="font-weight:600">${esc(horasCurto(horasDoTurno(t)))}</span>
              <span class="num apagado" style="display:block;font-size:12px">${esc(money(valorDoTurno(t)))}</span>
            </span>
          </button>`).join('')}</div>`
          : vazio({ emoji: '📭', titulo: 'Nenhum turno neste mês' })}
      </section>`;

    const serieD = serieDoMes(mesRef, r.porDia);
    graficoDias($('#vp-dias', alvo), serieD, { cor: PALETA[0] });
    pintaPizzas(alvo, r.porTarefa, grupos);
    $('#vp-tabela', alvo).innerHTML = tabelaDeApoio(
      serieD.filter((d) => d.horas > 0).map((d) => [dataCurta(d.data), horasCurto(d.horas), money(d.valor)]),
      ['Dia', 'Horas', 'Valor'],
    );

    $$('[data-mes]', alvo).forEach((b) => b.addEventListener('click', () => {
      mesRef = somaMeses(mesRef, +b.dataset.mes);
      abaVisaoPessoa(alvo, p);
    }));
    $('[data-mes-escolhe]', alvo)?.addEventListener('change', (ev) => {
      const [y, mo] = ev.target.value.split('-').map(Number);
      mesRef = inicioDoMes(new Date(y, mo - 1, 1));
      abaVisaoPessoa(alvo, p);
    });
    $('#v-novo-turno', alvo).addEventListener('click', () => editaTurno(null, { userId: p.id }));
    $$('[data-turno]', alvo).forEach((b) => b.addEventListener('click', () => {
      editaTurno(noMes.find((t) => t.id === b.dataset.turno) || turnos.find((t) => t.id === b.dataset.turno), { userId: p.id });
    }));
    $('#v-novo-pag', alvo).addEventListener('click', () => editaPagamentoLanc(null, p));
    $$('[data-pag]', alvo).forEach((b) => b.addEventListener('click', () => {
      editaPagamentoLanc(pagamentos.find((x) => x.id === b.dataset.pag), p);
    }));
  }

  function editaPagamentoLanc(pg, p) {
    const novo = !pg;
    const quando = novo ? new Date() : new Date(pg.paid_on);
    abreFolha({
      titulo: novo ? 'Registrar pagamento' : 'Editar pagamento',
      sub: p.full_name,
      corpo: `
        <label class="campo"><span class="campo-rotulo">Título</span>
          <input class="entrada" id="pg-tit" value="${esc(pg?.title || 'Pagamento')}" placeholder="ex.: Pagamento"></label>
        <label class="campo"><span class="campo-rotulo">Valor (R$)</span>
          <input class="entrada" type="number" min="0" step="0.01" id="pg-val" value="${esc(pg?.amount ?? '')}"></label>
        <label class="campo"><span class="campo-rotulo">Data</span>
          <input class="entrada" type="date" id="pg-data" value="${esc(quando.toISOString().slice(0, 10))}"></label>
        <label class="campo"><span class="campo-rotulo">Nota (opcional)</span>
          <input class="entrada" id="pg-nota" value="${esc(pg?.note || '')}"></label>
        <p class="campo-erro" id="pg-erro" hidden></p>
        <div class="linha-botoes">
          ${novo ? '' : '<button class="btn btn-medio btn-perigo" id="pg-apaga">Apagar</button>'}
          <button class="btn btn-primario btn-medio" id="pg-salva">${novo ? 'Lançar' : 'Salvar'}</button>
        </div>`,
      aoMontar: (caixa, fechar) => {
        const erro = $('#pg-erro', caixa);
        $('#pg-salva', caixa).addEventListener('click', async (ev) => {
          erro.hidden = true;
          const title = $('#pg-tit', caixa).value.trim() || 'Pagamento';
          const amount = +$('#pg-val', caixa).value;
          const paid_on = $('#pg-data', caixa).value;
          if (!Number.isFinite(amount) || amount < 0) {
            erro.textContent = 'Informe o valor.'; erro.hidden = false; return;
          }
          try {
            await comBotaoOcupado(ev.currentTarget, 'Salvando…', () => novo
              ? store.lancaPagamento({
                user_id: p.id, paid_on, amount, title, note: $('#pg-nota', caixa).value || null,
              })
              : store.atualizaPagamento(pg.id, {
                paid_on, amount, title, note: $('#pg-nota', caixa).value || null,
              }));
            fechar();
            if (aba === 'visao' && pessoaFoco) abaVisaoPessoa($('#conteudo-aba', raiz), pessoaFoco);
            torrada(novo ? 'Pagamento lançado.' : 'Pagamento salvo.', 'bom');
          } catch (e) { erro.textContent = e.message; erro.hidden = false; }
        });
        $('#pg-apaga', caixa)?.addEventListener('click', async () => {
          if (!await confirma({ titulo: 'Apagar pagamento?', ok: 'Apagar', perigo: true })) return;
          await store.apagaPagamento(pg.id);
          fechar();
          if (aba === 'visao' && pessoaFoco) abaVisaoPessoa($('#conteudo-aba', raiz), pessoaFoco);
          torrada('Pagamento apagado.', 'bom');
        });
      },
    });
  }

  /* ======================================================================
     ABA: CONFERÊNCIA planilha × app
     ====================================================================== */

  async function abaConferencia(alvo) {
    alvo.innerHTML = carregando('Conferindo planilha × app…');
    const ym = chaveMes(mesRef);
    const [turnosBrutos, bonusMes, planilhas] = await Promise.all([
      store.listaTurnos({ de: inicioDoMes(mesRef), ate: fimDoMes(mesRef) }),
      store.listaBonusMes({ yearMonth: ym }),
      store.listaTotaisPlanilha({ yearMonth: ym }),
    ]);
    const turnos = pintaTrechos(turnosBrutos, tarefas);
    const geral = agrega(turnos);
    const bonusPor = new Map();
    for (const e of bonusMes) {
      if (!bonusPor.has(e.user_id)) bonusPor.set(e.user_id, []);
      bonusPor.get(e.user_id).push(e);
    }
    const planPor = new Map(planilhas.map((x) => [x.user_id, x]));

    const extrasPor = new Map(extraPorPessoa(turnos, pessoas).map((e) => [e.user_id, e]));

    const linhas = pessoas.map((p) => {
      const r = geral.porPessoa.get(p.id) || { horas: 0, valor: 0, turnos: 0 };
      const bons = bonusPor.get(p.id) || [];
      const bonus = somaBonus(bons);
      const app = (+r.valor || 0) + bonus;
      const pl = planPor.get(p.id);
      const esperado = pl ? +pl.expected_total : null;
      const diff = esperado != null ? app - esperado : null;
      const extra = extrasPor.get(p.id);
      return { p, trabalho: +r.valor || 0, bonus, app, esperado, diff, bons, horas: r.horas, extra };
    }).filter((l) => l.app > 0 || l.esperado != null || l.p.active)
      .sort((a, b) => Math.abs(b.diff || 0) - Math.abs(a.diff || 0));

    const comDiff = linhas.filter((l) => l.diff != null && Math.abs(l.diff) >= 0.5);
    const comExtra = [...extrasPor.values()].filter((e) => e.temExtra);

    alvo.innerHTML = `
      ${barraDeFiltro({ semPessoa: true })}
      ${htmlAlertaExtra(comExtra, { tituloMes: nomeMes(mesRef) })}
      <div class="recado" style="margin-bottom:16px">
        <span class="recado-emoji">🔎</span>
        <span>Compara o total da <strong>planilha</strong> (trabalho + extras importados) com o
              <strong>app</strong> (turnos + bônus). Se a diferença não for zero, algo escapou.</span>
      </div>
      ${comDiff.length ? `
        <div class="recado ruim" style="margin-bottom:16px">
          <span class="recado-emoji">⚠️</span>
          <span><strong>${esc(plural(comDiff.length, 'pessoa com diferença', 'pessoas com diferença'))}</strong> em ${esc(nomeMes(mesRef))}.</span>
        </div>` : `
        <div class="recado" style="margin-bottom:16px">
          <span class="recado-emoji">✅</span>
          <span>Nenhuma diferença relevante neste mês${planilhas.length ? '' : ' (ainda sem totais de planilha importados)'}.</span>
        </div>`}

      <section class="cartao">
        <div class="cartao-topo"><h2 class="cartao-titulo">Por pessoa · ${esc(nomeMes(mesRef))}</h2></div>
        ${linhas.length ? `<div class="lista">${linhas.map((l) => {
          const okDiff = l.diff == null || Math.abs(l.diff) < 0.5;
          return `
          <button class="item clicavel" data-conf="${esc(l.p.id)}" style="flex-direction:column;align-items:stretch;gap:6px">
            <div style="display:flex;align-items:center;gap:12px">
              <span class="avatar" style="width:38px;height:38px;font-size:12px;flex:none">${esc(iniciais(l.p.full_name))}</span>
              <span class="item-titulo" style="flex:1">${esc(l.p.full_name)}</span>
              ${l.extra?.temExtra ? htmlRecadoExtraPessoa(l.extra, { compacto: true }) : ''}
              <span class="ficha ${okDiff ? 'ficha-alta' : 'ficha-baixa'}">${okDiff ? 'ok' : esc(money(l.diff))}</span>
            </div>
            <div class="item-sub" style="margin:0">
              app ${esc(money(l.app))} (trabalho ${esc(money(l.trabalho))} + bônus ${esc(money(l.bonus))})
              · planilha ${l.esperado != null ? esc(money(l.esperado)) : '—'}
              ${l.extra?.temExtra ? ` · hora extra ${esc(horas(l.extra.extra))}` : ''}
            </div>
            ${l.bons.length ? `<div class="recibo-corpo" style="padding-top:4px">${
              agrupaBonus(l.bons).map((g) =>
                `<div class="recibo-linha"><span class="recibo-nome">${esc(g.title)}${
                  g.count > 1 ? ` <small>${g.count}× ${esc(money(g.unit))}</small>` : ''
                }</span><span class="num recibo-valor">${esc(money(g.total))}</span></div>`).join('')
            }</div>` : ''}
          </button>`;
        }).join('')}</div>` : vazio({ emoji: '🔎', titulo: 'Sem dados neste mês' })}
      </section>`;

    ligaFiltro(alvo, abaConferencia);
    $$('[data-conf]', alvo).forEach((b) => b.addEventListener('click', () => {
      const p = pessoas.find((x) => x.id === b.dataset.conf);
      if (!p) return;
      pessoaFoco = p; aba = 'visao'; desenha();
    }));
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
    const ym = chaveMes(mesRef);
    const [turnosBrutos, bonusMes] = await Promise.all([
      store.listaTurnos({ de: inicioDoMes(mesRef), ate: fimDoMes(mesRef) }),
      store.listaBonusMes({ yearMonth: ym }),
    ]);
    const turnos = pintaTrechos(turnosBrutos, tarefas);
    const geral = agrega(turnos);
    const bonusPorPessoa = new Map();
    for (const e of bonusMes) {
      if (!bonusPorPessoa.has(e.user_id)) bonusPorPessoa.set(e.user_id, []);
      bonusPorPessoa.get(e.user_id).push(e);
    }
    const totalBonus = somaBonus(bonusMes);

    const extrasPor = new Map(extraPorPessoa(turnos, pessoas).map((e) => [e.user_id, e]));

    const linhas = pessoas.map((p) => {
      const r = geral.porPessoa.get(p.id) || { horas: 0, valor: 0, turnos: 0 };
      const bons = bonusPorPessoa.get(p.id) || [];
      const bonus = somaBonus(bons);
      const dias = new Set(turnos.filter((t) => t.user_id === p.id).map((t) => diaChave(t.started_at))).size;
      const extra = extrasPor.get(p.id);
      return {
        p, ...r, dias, media: dias ? r.horas / dias : 0,
        bonus, total: (+r.valor || 0) + bonus, bons, extra,
      };
    }).filter((l) => l.horas > 0 || l.bonus > 0 || l.p.active)
      .sort((a, b) => b.total - a.total);

    const custoTotal = geral.valor + totalBonus;
    const comExtra = [...extrasPor.values()].filter((e) => e.temExtra);

    alvo.innerHTML = `
      ${barraDeFiltro({ semPessoa: true })}
      ${htmlAlertaExtra(comExtra, { tituloMes: nomeMes(mesRef) })}

      <section class="cartao">
        <div class="heroi">
          <p class="heroi-rotulo">Custo de mão de obra em ${esc(nomeMes(mesRef))}</p>
          <p class="heroi-valor saldo">${esc(money(custoTotal))}</p>
          <div class="heroi-nota">
            <span class="ficha ficha-neutra">trabalho ${esc(money(geral.valor))}</span>
            <span class="ficha ficha-neutra">bônus ${esc(money(totalBonus))}</span>
            <span class="ficha ficha-neutra">${esc(horas(geral.horas))}</span>
            <span class="ficha ficha-neutra">${esc(plural(linhas.filter((l) => l.horas > 0 || l.bonus > 0).length, 'pessoa', 'pessoas'))}</span>
          </div>
        </div>
      </section>

      <section class="cartao">
        <div class="cartao-topo">
          <h2 class="cartao-titulo">Por pessoa</h2>
          <button class="btn btn-pequeno btn-fantasma" id="r-csv">${ICONE.baixar}<span>Baixar CSV</span></button>
        </div>
        ${linhas.length ? `<div class="lista-recibos">${linhas.map((l) =>
          htmlReciboPessoa({
            p: l.p, horasMes: l.horas, dias: l.dias, trabalho: l.valor,
            grupos: agrupaBonus(l.bons), total: l.total, clicavel: true,
            horasExtra: l.extra?.temExtra ? l.extra.extra : 0,
          })).join('')}</div>`
          : vazio({ emoji: '📊', titulo: 'Nada registrado neste mês' })}
      </section>

      <section class="cartao">
        <div class="cartao-topo"><h2 class="cartao-titulo">Como se divide o custo</h2></div>
        <div class="grade-pizzas">
          <div class="pizza-bloco">
            <h3 class="pizza-titulo">Por pessoa</h3>
            <div class="grafico" id="r-pizza-pessoas"></div>
          </div>
          <div class="pizza-bloco">
            <h3 class="pizza-titulo">Por tarefa (horas)</h3>
            <div class="grafico" id="r-tarefas"></div>
          </div>
        </div>
      </section>`;

    ligaFiltro(alvo, abaRelatorios);
    graficoPizza($('#r-pizza-pessoas', alvo), fatiasPorPessoa(linhas), {
      formato: 'money', rotuloCentro: 'custo',
    });
    graficoPizza($('#r-tarefas', alvo),
      [...geral.porTarefa.values()].filter((t) => t.horas > 0.001)
        .map((t) => ({ nome: t.nome, valor: t.horas, cor: t.cor })),
      { formato: 'horas', rotuloCentro: 'horas' });
    $$('[data-pessoa]', alvo).forEach((b) => {
      const abre = () => {
        const pessoa = pessoas.find((x) => x.id === b.dataset.pessoa);
        if (!pessoa) return;
        pessoaFoco = pessoa; aba = 'visao'; desenha();
      };
      b.addEventListener('click', abre);
      b.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); abre(); }
      });
    });

    $('#r-csv', alvo).addEventListener('click', () => {
      if (!linhas.length) { torrada('Nada para baixar neste mês.', 'ruim'); return; }
      const csv = [csvLinha(['Pessoa', 'Usuário', 'Turnos', 'Dias', 'Horas', 'Hora extra', 'Trabalho R$', 'Bônus R$', 'Total R$'])];
      linhas.forEach((l) => csv.push(csvLinha([
        l.p.full_name, l.p.username, l.turnos, l.dias,
        num(l.horas, 2), num(l.extra?.temExtra ? l.extra.extra : 0, 2),
        num(l.valor, 2), num(l.bonus, 2), num(l.total, 2),
      ])));
      csv.push('');
      csv.push(csvLinha(['TOTAL', '', geral.turnos, '', num(geral.horas, 2),
        num(geral.valor, 2), num(totalBonus, 2), num(custoTotal, 2)]));
      baixaArquivo(`s7ponto-relatorio-${ym}.csv`, csv.join('\n'));
      torrada('Relatório baixado.', 'bom');
    });
  }

  /* ======================================================================
     Filtro compartilhado (mês + pessoa)
     ====================================================================== */

  function htmlSeletorMes({ sticky = false } = {}) {
    const podeAvancar = somaMeses(mesRef, 1) <= inicioDoMes(new Date());
    const fim = inicioDoMes(new Date());
    const ini = somaMeses(fim, -24);
    const opts = [];
    const visto = new Set();
    for (let m = new Date(fim); m >= ini; m = somaMeses(m, -1)) {
      const k = chaveMes(m);
      visto.add(k);
      opts.push(`<option value="${esc(k)}" ${k === chaveMes(mesRef) ? 'selected' : ''}>${esc(maiuscula(mesAno(m)))}</option>`);
    }
    if (!visto.has(chaveMes(mesRef))) {
      opts.unshift(`<option value="${esc(chaveMes(mesRef))}" selected>${esc(maiuscula(mesAno(mesRef)))}</option>`);
    }
    return `
      <nav class="mes-nav${sticky ? ' barra-mes-sticky' : ''}" aria-label="Escolher o mês">
        <button class="mes-nav-btn" data-mes="-1" aria-label="Mês anterior">${ICONE.esquerda}</button>
        <label class="mes-nav-escolhe">
          <select class="mes-nav-titulo" data-mes-escolhe aria-label="Ver outro mês">${opts.join('')}</select>
        </label>
        <button class="mes-nav-btn" data-mes="1" ${podeAvancar ? '' : 'disabled'} aria-label="Próximo mês">${ICONE.direita}</button>
      </nav>`;
  }

  function barraDeFiltro({ semPessoa = false, sticky = false } = {}) {
    return `
      ${htmlSeletorMes({ sticky })}
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
    $('[data-mes-escolhe]', alvo)?.addEventListener('change', (ev) => {
      const [y, mo] = ev.target.value.split('-').map(Number);
      mesRef = inicioDoMes(new Date(y, mo - 1, 1));
      redesenha(alvo);
    });
    $('[data-filtro-pessoa]', alvo)?.addEventListener('change', (ev) => {
      filtroPessoa = ev.target.value;
      redesenha(alvo);
    });
  }

  desenha();
  return { destruir() {} };
}
