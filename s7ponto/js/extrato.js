/* ==========================================================================
   S7 PONTO — extrato de ganhos (trabalho + bônus agrupados) e pizzas.
   ========================================================================== */
import { esc, money, horas, iniciais, dataBR, plural } from './util.js';
import { $ } from './ui.js';
import { graficoPizza, PALETA } from './charts.js';
import { agrupaBonus, fatiasHoras, fatiasQtd, fatiasSalario } from './metricas.js';

export { agrupaBonus };

export function origemBonus(e) {
  if (e?.source === 'auto') return 'automático';
  if (e?.source === 'import') return 'da planilha';
  return 'lançado na mão';
}

function linha(nome, valor, detalhe = '') {
  if (!(valor > 0.004) && !detalhe) return '';
  return `
    <li class="recibo-linha">
      <span class="recibo-nome">${esc(nome)}${detalhe
        ? ` <small>${esc(detalhe)}</small>` : ''}</span>
      <span class="num recibo-valor">${esc(money(valor))}</span>
    </li>`;
}

/** Recibo: horas × valor, cada tipo de bônus agrupado, total embaixo.
 *  `partes` (ex.: Turno Manhã / Tarde) quebra o trabalho quando há mais de uma origem. */
export function htmlRecibo({
  horasMes = 0, trabalho = 0, grupos = [], total = 0, pago = 0, partes = [],
  ocultarPago = false,
}) {
  const bonus = grupos.reduce((s, g) => s + (g.total || 0), 0);
  const falta = total - pago;
  const mixTrab = total > 0 ? (trabalho / total) * 100 : 0;
  const mixBon = total > 0 ? (bonus / total) * 100 : 0;
  const linhasPartes = (partes || []).filter((p) => (p.valor || 0) > 0.004 || (p.horas || 0) > 0.001);
  const detalha = linhasPartes.length > 1;
  const linhasTrabalho = detalha
    ? linhasPartes.map((p) => linha(p.nome, p.valor, p.horas > 0.001 ? horas(p.horas) : '')).join('')
    : ((trabalho > 0.004 || horasMes > 0.001) ? linha(
      'Trabalho',
      trabalho,
      horasMes > 0.001 ? horas(horasMes) : '',
    ) : '');

  return `
    <div class="recibo-corpo">
      <ul class="recibo-linhas">
        ${linhasTrabalho}
        ${grupos.map((g) => linha(
          g.title,
          g.total,
          g.count > 1 ? `${g.count}× ${money(g.unit)}` : '',
        )).join('')}
      </ul>
      <div class="recibo-pe">
        <span>Total</span>
        <span class="num">${esc(money(total))}</span>
      </div>
      ${total > 0 ? `
        <div class="recibo-mix" aria-hidden="true">
          <span class="recibo-mix-trab" style="width:${mixTrab}%"></span>
          <span class="recibo-mix-bon" style="width:${mixBon}%"></span>
        </div>
        <div class="recibo-mix-legenda">
          <span>trabalho ${esc(money(trabalho))}</span>
          ${bonus ? `<span>bônus ${esc(money(bonus))}</span>` : ''}
        </div>` : ''}
      ${!ocultarPago && pago > 0.004 ? htmlBarraPago({ pago, total, falta }) : ''}
    </div>`;
}

function linhaExtrato({ nome, detalhe = '', valor = 0, sentido = '' }) {
  const n = +valor || 0;
  if (Math.abs(n) < 0.005 && !detalhe) return '';
  const menos = sentido === 'menos' || n < -0.005;
  const abs = Math.abs(n);
  const sinal = menos ? '−' : n > 0.005 ? '+' : '';
  return `
    <li class="extrato-linha ${menos ? 'menos' : 'mais'}">
      <span class="extrato-nome">${esc(nome)}${detalhe
        ? ` <small>${esc(detalhe)}</small>` : ''}</span>
      <span class="num extrato-valor">${sinal}${esc(money(abs))}</span>
    </li>`;
}

/**
 * Conta do saldo, compacta: iguais somados (3× Noite = um item).
 * Pagamentos entram só como um total — o detalhe fica no menu Pagamentos.
 */
export function htmlExtratoSaldo({
  mesNome = '',
  mesAntNome = '',
  saldoAnterior = 0,
  partes = [],
  trabalho = 0,
  horasMes = 0,
  bonusEntries = [],
  grupos = null,
  pagamentos = [],
  pagoMes = null,
  qtdPagamentos = null,
  saldo = 0,
  titulo = 'Como chegou no disponível',
} = {}) {
  const linhas = [];
  if (Math.abs(saldoAnterior) > 0.5) {
    linhas.push(linhaExtrato({
      nome: saldoAnterior < 0 ? `Crédito de ${mesAntNome}` : `Saldo de ${mesAntNome}`,
      detalhe: 'já puxa do mês anterior',
      valor: saldoAnterior,
    }));
  }

  const linhasPartes = (partes || []).filter((p) => (p.valor || 0) > 0.004 || (p.horas || 0) > 0.001);
  if (linhasPartes.length > 1) {
    for (const p of linhasPartes) {
      const qtd = p.qtd > 1 ? `${p.qtd}×` : '';
      linhas.push(linhaExtrato({
        nome: p.nome,
        detalhe: [p.horas > 0.001 ? horas(p.horas) : '', qtd].filter(Boolean).join(' · '),
        valor: p.valor,
      }));
    }
  } else if (trabalho > 0.004 || horasMes > 0.001) {
    linhas.push(linhaExtrato({
      nome: linhasPartes[0]?.nome || 'Trabalho',
      detalhe: horasMes > 0.001 ? horas(horasMes) : '',
      valor: trabalho,
    }));
  }

  const gruposBonus = grupos || agrupaBonus(bonusEntries);
  for (const g of gruposBonus) {
    if (!(g.total > 0.004)) continue;
    linhas.push(linhaExtrato({
      nome: g.title,
      detalhe: g.count > 1 ? `${g.count}× ${money(g.unit)}` : '',
      valor: g.total,
    }));
  }

  const pago = pagoMes != null
    ? +pagoMes || 0
    : (pagamentos || []).reduce((s, pg) => s + (+pg.amount || 0), 0);
  const qtdPg = qtdPagamentos != null ? qtdPagamentos : (pagamentos || []).length;
  if (pago > 0.004) {
    linhas.push(linhaExtrato({
      nome: 'Já pago',
      detalhe: qtdPg > 1 ? `${qtdPg} pagamentos` : '',
      valor: -pago,
      sentido: 'menos',
    }));
  }

  if (!linhas.length) {
    return `
      <div class="extrato-saldo">
        <p class="extrato-titulo">${esc(titulo)}</p>
        <p class="apagado" style="margin:0">Ainda não entrou trabalho nem bônus em ${esc(mesNome || 'neste mês')}.</p>
      </div>`;
  }

  const credito = saldo < -0.5;
  const rotuloFim = credito ? 'Crédito' : (saldo > 0.5 ? 'Disponível' : 'Em dia');
  const valorFim = credito ? -saldo : Math.max(0, saldo);

  return `
    <div class="extrato-saldo">
      <p class="extrato-titulo">${esc(titulo)}</p>
      <ul class="extrato-linhas">${linhas.join('')}</ul>
      <div class="extrato-pe">
        <span>${esc(rotuloFim)}</span>
        <span class="num">${esc(money(valorFim))}</span>
      </div>
    </div>`;
}

/** Menu Conta · Pagamentos · Histórico — mesma tela, três recortes. */
export function htmlSubnavConta(aba = 'conta') {
  const itens = [
    { id: 'conta', nome: 'Conta' },
    { id: 'pagamentos', nome: 'Pagamentos' },
    { id: 'historico', nome: 'Histórico' },
  ];
  return `
    <div class="pg-filtros visao-subnav" role="tablist" aria-label="O que ver">
      ${itens.map((it) => `
        <button type="button" class="pg-filtro ${aba === it.id ? 'on' : ''}"
                data-visao-aba="${esc(it.id)}" role="tab"
                aria-selected="${aba === it.id}">${esc(it.nome)}</button>`).join('')}
    </div>`;
}

export function htmlBarraPago({ pago, total, falta }) {
  const pct = total > 0 ? Math.min(100, Math.max(0, (pago / total) * 100)) : 0;
  const aMais = falta < -0.5;
  return `
    <div class="barra-pago">
      <div class="barra-pago-topo">
        <span>Já recebido</span>
        <span class="num">${esc(money(pago))} <span class="apagado">de ${esc(money(total))}</span></span>
      </div>
      <div class="barra-pago-trilha">
        <div class="barra-pago-preenche" style="width:${pct}%"></div>
      </div>
      <p class="barra-pago-nota ${aMais ? 'mais' : ''}">
        ${aMais
          ? `Recebeu ${esc(money(-falta))} a mais que o total deste mês (abate o saldo anterior).`
          : Math.abs(falta) < 0.5
            ? 'Tudo o que entrou neste mês já foi pago.'
            : `Deste mês ainda não pago: ${esc(money(falta))}.`}
      </p>
    </div>`;
}

/** Card de uma pessoa no relatório — hierarquia clara, bônus unidos. */
export function htmlReciboPessoa({
  p, horasMes, dias = 0, trabalho, grupos, total, pago = 0, id = '', clicavel = false,
  horasExtra = 0,
}) {
  const extra = clicavel
    ? ` class="recibo recibo-clicavel" data-pessoa="${esc(id || p.id)}" tabindex="0"`
    : ' class="recibo"';
  const sub = [
    horasMes > 0.001 ? horas(horasMes) : null,
    dias ? `${dias} ${dias === 1 ? 'dia' : 'dias'}` : null,
    horasExtra >= 15 / 60 ? `${horas(horasExtra)} extra` : null,
  ].filter(Boolean).join(' · ') || 'sem registro neste mês';

  return `
    <article${extra}>
      <header class="recibo-topo">
        <span class="avatar recibo-avatar">${esc(iniciais(p.full_name))}</span>
        <div class="recibo-quem">
          <div class="item-titulo">${esc(p.full_name)}</div>
          <div class="item-sub">${esc(sub)}</div>
        </div>
        <div class="recibo-total">
          <div class="recibo-total-rotulo">total</div>
          <div class="num recibo-total-valor">${esc(money(total))}</div>
        </div>
      </header>
      ${htmlRecibo({ horasMes, trabalho, grupos, total, pago })}
    </article>`;
}

export function htmlPizzas({ porTurno = false, payMode = 'hourly' } = {}) {
  const porTarefa = payMode === 'task';
  const tituloQtd = porTurno || payMode === 'shift' ? 'Turnos no mês'
    : porTarefa ? 'Tarefas no mês'
    : 'Horas por tarefa';
  const subQtd = porTurno || payMode === 'shift' ? 'Manhã, tarde e noite'
    : porTarefa ? 'Quantas vezes cada uma'
    : 'Onde o tempo foi';
  const tituloVal = porTurno || payMode === 'shift' ? 'Valor por turno'
    : porTarefa ? 'Valor por tarefa'
    : 'De onde vem o valor';
  const subVal = porTurno || payMode === 'shift' ? 'Quanto cada período rende'
    : porTarefa ? 'Valor fixo de cada uma'
    : 'Trabalho + bônus';
  return `
    <div class="grade-pizzas">
      <div class="pizza-bloco">
        <h3 class="pizza-titulo">${tituloQtd}</h3>
        <p class="pizza-sub">${subQtd}</p>
        <div class="grafico" id="g-pizza-horas"></div>
      </div>
      <div class="pizza-bloco">
        <h3 class="pizza-titulo">${tituloVal}</h3>
        <p class="pizza-sub">${subVal}</p>
        <div class="grafico" id="g-pizza-valor"></div>
      </div>
    </div>`;
}

export function pintaPizzas(raiz, porTarefa, grupos, { porTurno = false, payMode = 'hourly' } = {}) {
  const fixo = payMode === 'task' || payMode === 'shift' || porTurno;
  const qtdFat = fixo ? fatiasQtd(porTarefa) : fatiasHoras(porTarefa);
  const valorFat = fatiasSalario(porTarefa, grupos);
  const gH = $('#g-pizza-horas', raiz);
  const gV = $('#g-pizza-valor', raiz);
  if (gH) {
    graficoPizza(gH, qtdFat, {
      formato: fixo ? 'qtd' : 'horas',
      rotuloCentro: payMode === 'shift' || porTurno ? 'nos turnos'
        : payMode === 'task' ? 'tarefas'
        : 'nas tarefas',
    });
  }
  if (gV) graficoPizza(gV, valorFat, { formato: 'money', rotuloCentro: 'do mês' });
}

/** Cards de resumo — por turno (Fran) ou por hora (os outros). */
export function htmlGradeMetricas({
  payMode = 'hourly',
  r,
  noMes = [],
  total = 0,
  cmp = null,
  mesAntNome = '',
  periodoTxt = '',
  temAnt = false,
}) {
  const notaHoras = cmp?.diaLimite > 0 && temAnt
    ? `<div class="metrica-nota">${esc(horas(Math.abs(cmp.variacao.horas.abs)))} ${cmp.variacao.horas.abs >= 0 ? 'a mais' : 'a menos'} que em ${esc(mesAntNome)} (${esc(periodoTxt)})</div>`
    : '';
  const notaDias = cmp?.diaLimite > 0 && temAnt
    ? `<div class="metrica-nota">${esc(plural(Math.abs(cmp.variacao.dias.abs), 'dia', 'dias'))} ${cmp.variacao.dias.abs >= 0 ? 'a mais' : 'a menos'} que no mesmo período</div>`
    : '';

  if (payMode === 'shift') {
    const nM = noMes.filter((t) => t.period === 'manha').length;
    const nT = noMes.filter((t) => t.period === 'tarde').length;
    const nN = noMes.filter((t) => t.period === 'noite').length;
    const media = noMes.length ? r.valor / noMes.length : 0;
    const partesPer = [
      nM ? `${nM} manhã${nM === 1 ? '' : 's'}` : null,
      nT ? `${nT} tarde${nT === 1 ? '' : 's'}` : null,
      nN ? `${nN} noite${nN === 1 ? '' : 's'}` : null,
    ].filter(Boolean).join(' · ') || 'sem períodos';
    return `
      <section class="grade-metricas" style="margin-top:16px">
        <div class="metrica">
          <div class="metrica-rotulo">Turnos no mês</div>
          <div class="metrica-valor">${esc(String(noMes.length))}</div>
          <div class="metrica-nota">${esc(partesPer)}</div>
        </div>
        <div class="metrica">
          <div class="metrica-rotulo">Dias trabalhados</div>
          <div class="metrica-valor">${esc(String(r.diasTrabalhados))}</div>
          ${notaDias}
        </div>
        <div class="metrica">
          <div class="metrica-rotulo">Média por turno</div>
          <div class="metrica-valor saldo">${esc(money(media))}</div>
          <div class="metrica-nota">valor fixo do período, não por hora</div>
        </div>
        <div class="metrica">
          <div class="metrica-rotulo">Média por dia</div>
          <div class="metrica-valor">${esc(money(r.mediaValorPorDia))}</div>
          <div class="metrica-nota">só o que entrou de trabalho</div>
        </div>
      </section>`;
  }

  if (payMode === 'task') {
    const media = noMes.length ? r.valor / noMes.length : 0;
    return `
      <section class="grade-metricas" style="margin-top:16px">
        <div class="metrica">
          <div class="metrica-rotulo">Tarefas no mês</div>
          <div class="metrica-valor">${esc(String(noMes.length))}</div>
          <div class="metrica-nota">cada uma com valor fixo</div>
        </div>
        <div class="metrica">
          <div class="metrica-rotulo">Dias trabalhados</div>
          <div class="metrica-valor">${esc(String(r.diasTrabalhados))}</div>
          ${notaDias}
        </div>
        <div class="metrica">
          <div class="metrica-rotulo">Média por tarefa</div>
          <div class="metrica-valor saldo">${esc(money(media))}</div>
          <div class="metrica-nota">não multiplica pelas horas</div>
        </div>
        <div class="metrica">
          <div class="metrica-rotulo">Média por dia</div>
          <div class="metrica-valor">${esc(money(r.mediaValorPorDia))}</div>
          <div class="metrica-nota">só o que entrou de trabalho</div>
        </div>
      </section>`;
  }

  const taxaTrabalho = r.horas > 0.001 ? r.valor / r.horas : 0;
  const taxaGeral = r.horas > 0.001 ? total / r.horas : 0;
  return `
    <section class="grade-metricas" style="margin-top:16px">
      <div class="metrica">
        <div class="metrica-rotulo">Horas no mês</div>
        <div class="metrica-valor">${esc(horas(r.horas))}</div>
        ${notaHoras}
      </div>
      <div class="metrica">
        <div class="metrica-rotulo">Dias trabalhados</div>
        <div class="metrica-valor">${esc(String(r.diasTrabalhados))}</div>
        ${notaDias}
      </div>
      <div class="metrica">
        <div class="metrica-rotulo">Média do trabalho</div>
        <div class="metrica-valor">${esc(money(taxaTrabalho))}<small class="metrica-unid">/h</small></div>
        <div class="metrica-nota">só horas × valor, sem bônus</div>
      </div>
      <div class="metrica">
        <div class="metrica-rotulo">Média com bônus</div>
        <div class="metrica-valor saldo">${esc(money(taxaGeral))}<small class="metrica-unid">/h</small></div>
        <div class="metrica-nota">${esc(money(r.mediaValorPorDia))} de trabalho por dia</div>
      </div>
    </section>`;
}

export function htmlDetalheBonus(entries = []) {
  if (!entries.length) return '';
  return `
    <div class="recibo-detalhe">
      <p class="extrato-titulo" style="margin-top:14px">Cada bônus</p>
      <div class="lista">${entries.map((e) => `
        <div class="item">
          <div class="item-corpo">
            <div class="item-titulo">${esc(e.title)}</div>
            <div class="item-sub">${[
              e.bonus_on ? dataBR(e.bonus_on) : null,
              origemBonus(e),
              e.note,
            ].filter(Boolean).join(' · ')}</div>
          </div>
          <div class="num" style="font-weight:600;color:var(--salvia-alt)">${esc(money(e.amount))}</div>
        </div>`).join('')}
      </div>
    </div>`;
}

export function fatiasPorPessoa(linhas) {
  return linhas
    .filter((l) => l.total > 0.004)
    .map((l, i) => ({
      nome: String(l.p.full_name || '').split(' ')[0],
      valor: l.total,
      cor: PALETA[i % PALETA.length],
    }));
}
