/* ==========================================================================
   S7 PONTO — "Meus números": quanto entrou, quantas horas, e como ficou
   comparado com o mesmo período do mês passado. Trabalho + bônus no total.
   ========================================================================== */
import { store } from './store.js';
import {
  esc, money, moneyShort, horas, horasCurto, pct, mesAno, dataLonga,
  dataCurta, hora, somaMeses, inicioDoMes, fimDoMes, plural,
  dataBR, maiuscula, nomeMes, chaveMes, nomePeriodo, pagamentoFixo,
} from './util.js';
import { $, $$, ICONE, carregando, vazio } from './ui.js';
import { graficoDias, graficoMeses, tabelaDeApoio, PALETA } from './charts.js';
import {
  pintaTrechos, resumoDoMes, serieDoMes, serieDeMeses,
  horasDoTurno, valorDoTurno, somaBonus, totalComBonus, somaPagamentos,
  agrupaBonus, comparaSaldo, saldosPorPessoa,
} from './metricas.js';
import { htmlRecibo, htmlPizzas, pintaPizzas, htmlGradeMetricas, htmlExtratoSaldo } from './extrato.js';
import { extraDoPeriodo, htmlRecadoExtraPessoa } from './hora-extra.js';

export async function telaDeNumeros(raiz, ctx) {
  const { usuario } = ctx;
  let mesRef = inicioDoMes(new Date());
  let turnos = [];
  let bonusMes = [];
  let bonusTodos = [];

  raiz.innerHTML = carregando('Somando suas horas…');
  let primeiroTurno = inicioDoMes(new Date());

  function mesesDoSeletor() {
    const fim = inicioDoMes(new Date());
    let ini = primeiroTurno < fim ? primeiroTurno : fim;
    const out = [];
    for (let m = new Date(fim); m >= ini; m = somaMeses(m, -1)) out.push(new Date(m));
    return out;
  }

  async function carregaBonus() {
    const ym = chaveMes(mesRef);
    const ymAnt = chaveMes(somaMeses(mesRef, -1));
    bonusMes = [];
    bonusTodos = [];
    try {
      bonusMes = await store.listaBonusMes({ userId: usuario.id, yearMonth: ym });
    } catch { bonusMes = []; }
    try {
      await store.listaBonusMes({ userId: usuario.id, yearMonth: ymAnt });
    } catch { /* mês anterior só gera automático; o saldo usa a lista da pessoa */ }
    try {
      const todos = await store.listaBonusPessoa(usuario.id);
      const porId = new Map((todos || []).map((e) => [e.id, e]));
      for (const e of bonusMes) porId.set(e.id, e);
      bonusTodos = [...porId.values()];
    } catch {
      bonusTodos = bonusMes.slice();
    }
  }

  async function desenha() {
    turnos = pintaTrechos(
      await store.listaTurnos({
        userId: usuario.id,
      }),
      await store.listaTarefas(true),
    );
    primeiroTurno = turnos.length
      ? inicioDoMes(turnos[turnos.length - 1].started_at)
      : inicioDoMes(new Date());
    await carregaBonus();
    let pagamentos = [];
    let pagsTodos = [];
    try {
      pagsTodos = await store.listaPagamentos({ userId: usuario.id });
      pagamentos = pagsTodos.filter((x) => x.year_month === chaveMes(mesRef));
    } catch { pagamentos = []; pagsTodos = []; }
    const r = resumoDoMes(turnos, mesRef);
    const grupos = agrupaBonus(bonusMes);
    const total = totalComBonus(r.valor, bonusMes);
    const pago = somaPagamentos(pagamentos);
    const noMes = turnos.filter((t) => {
      const d = new Date(t.started_at);
      return d >= inicioDoMes(mesRef) && d <= fimDoMes(mesRef);
    });
    const porTurno = usuario.pay_mode === 'shift' || noMes.some((t) => t.period);
    const fixo = pagamentoFixo(usuario.pay_mode);
    const bancoExtra = fixo ? { temExtra: false } : extraDoPeriodo(noMes);
    const fichaTrabalho = fixo
      ? `<span class="ficha ficha-neutra">${esc(plural(r.turnos, usuario.pay_mode === 'shift' ? 'turno' : 'tarefa', usuario.pay_mode === 'shift' ? 'turnos' : 'tarefas'))}</span>`
      : `<span class="ficha ficha-neutra">${esc(horas(r.horas))} trabalhadas</span>`;

    const faltaMes = Math.max(0, total - pago);
    const ehMesCorrente = chaveMes(mesRef) === chaveMes(new Date());
    const saldoGeral = saldosPorPessoa({
      pessoas: [usuario], turnos, bonus: bonusTodos, pagamentos: pagsTodos,
    })[0];
    const disponivel = Math.max(0, saldoGeral?.saldo || 0);
    const credito = (saldoGeral?.saldo || 0) < -0.5;
    const falta = ehMesCorrente ? disponivel : faltaMes;
    const emDia = ehMesCorrente
      ? disponivel < 0.5 && !credito
      : total > 0.004 && faltaMes < 0.5;
    let heroiRotulo;
    let heroiValor;
    if (ehMesCorrente && credito) {
      heroiRotulo = 'Você tem crédito';
      heroiValor = -saldoGeral.saldo;
    } else if (emDia) {
      heroiRotulo = ehMesCorrente ? 'Tudo recebido neste mês' : `Tudo recebido em ${nomeMes(mesRef)}`;
      heroiValor = total;
    } else {
      heroiRotulo = ehMesCorrente ? 'Você tem a receber' : `A receber de ${nomeMes(mesRef)}`;
      heroiValor = falta;
    }
    const cmp = comparaSaldo(turnos, bonusTodos, mesRef);
    const dv = cmp.variacao.total;
    const temAnt = cmp.diaLimite > 0 && (cmp.anterior.total > 0.004 || cmp.atual.total > 0.004);
    const periodoTxt = `1–${cmp.diaLimite}`;
    const fichaVar = cmp.diaLimite < 1
      ? '<span class="ficha ficha-neutra">passa o primeiro dia do mês para comparar</span>'
      : !temAnt
        ? '<span class="ficha ficha-neutra">primeiro período com registro</span>'
        : `<span class="ficha ${dv.abs >= 0 ? 'ficha-alta' : 'ficha-baixa'}">
             ${dv.abs >= 0 ? ICONE.cima : ICONE.baixo}
             ${esc(money(Math.abs(dv.abs)))}${dv.pct !== null ? ` · ${esc(pct(dv.pct))}` : ''}
           </span>
           <span class="ficha ficha-neutra">${esc(nomeMes(somaMeses(mesRef, -1)))} ${esc(periodoTxt)}: ${esc(moneyShort(cmp.anterior.total))}</span>`;

    const podeAvancar = somaMeses(mesRef, 1) <= inicioDoMes(new Date());
    const podeVoltar = somaMeses(mesRef, -1) >= somaMeses(primeiroTurno, -1);
    const meses = mesesDoSeletor();

    raiz.innerHTML = `
      <div class="barra-mes-sticky">
        <nav class="mes-nav" aria-label="Escolher o mês">
          <button class="mes-nav-btn" data-mes="-1" ${podeVoltar ? '' : 'disabled'} aria-label="Mês anterior">${ICONE.esquerda}</button>
          <label class="mes-nav-escolhe">
            <select class="mes-nav-titulo" data-mes-escolhe aria-label="Ver outro mês">
              ${meses.map((m) => `<option value="${esc(chaveMes(m))}" ${chaveMes(m) === chaveMes(mesRef) ? 'selected' : ''}>${esc(maiuscula(mesAno(m)))}</option>`).join('')}
            </select>
          </label>
          <button class="mes-nav-btn" data-mes="1" ${podeAvancar ? '' : 'disabled'} aria-label="Próximo mês">${ICONE.direita}</button>
        </nav>
      </div>

      <section class="cartao">
        <div class="heroi">
          <p class="heroi-rotulo">${esc(heroiRotulo)}</p>
          <p class="heroi-valor saldo">${esc(money(heroiValor))}</p>
          <div class="heroi-nota">
            ${fichaTrabalho}
            ${total > 0.004 ? `<span class="ficha ficha-neutra">neste mês ${esc(money(total))}${somaBonus(bonusMes) > 0.004 ? ` · bônus ${esc(money(somaBonus(bonusMes)))}` : ''}${pago > 0.004 ? ` · recebeu ${esc(money(pago))}` : ''}</span>` : ''}
            ${ehMesCorrente && Math.abs(saldoGeral?.carregado || 0) > 0.5
              ? `<span class="ficha ficha-neutra">já puxa ${esc(money(saldoGeral.carregado))} do mês anterior</span>` : ''}
            ${htmlRecadoExtraPessoa(bancoExtra, { compacto: true })}
            ${fichaVar}
          </div>
          ${cmp.parcial ? `<p class="apagado" style="font-size:12.5px;margin-top:10px">Comparado até o dia ${esc(String(cmp.diaLimite))} (ontem), com bônus e extras — o dia de hoje fica de fora enquanto puder estar em aberto.</p>` : ''}
        </div>
        ${htmlExtratoSaldo({
          mesNome: nomeMes(mesRef),
          mesAntNome: nomeMes(somaMeses(mesRef, -1)),
          saldoAnterior: (saldoGeral?.meses || []).find((m) => m.ym === chaveMes(mesRef))?.saldoAnterior
            ?? (ehMesCorrente ? (saldoGeral?.carregado || 0) : 0),
          partes: fixo ? r.porTarefa.map((p) => ({ ...p, horas: 0 })) : r.porTarefa,
          trabalho: r.valor,
          horasMes: fixo ? 0 : r.horas,
          bonusEntries: bonusMes,
          pagamentos,
          saldo: ehMesCorrente
            ? (saldoGeral?.saldo || 0)
            : ((saldoGeral?.meses || []).find((m) => m.ym === chaveMes(mesRef))?.disponivel || 0),
          titulo: ehMesCorrente ? 'Como chegou no disponível' : `Conta de ${nomeMes(mesRef)}`,
        })}
        <p class="extrato-titulo" style="margin-top:18px">O que entrou em ${esc(nomeMes(mesRef))}</p>
        ${htmlRecibo({
          horasMes: fixo ? 0 : r.horas,
          trabalho: r.valor, grupos, total, pago, ocultarPago: true,
          partes: fixo ? r.porTarefa.map((p) => ({ ...p, horas: 0 })) : r.porTarefa,
        })}
      </section>

      ${htmlRecadoExtraPessoa(bancoExtra, { nomeMes: nomeMes(mesRef) })}
      ${ehMesCorrente && Math.abs(saldoGeral?.carregado || 0) > 0.5 && (disponivel > 0.5 || credito) ? `
        <div class="recado info" style="margin-top:14px">
          <span class="recado-emoji">📒</span>
          <span>O valor de cima já inclui o saldo do mês anterior, como o <strong>Disponível</strong> da última aba da planilha — não é a soma dos meses.</span>
        </div>` : ''}

      <section class="cartao" style="margin-top:16px">
        ${htmlPizzas({ porTurno, payMode: usuario.pay_mode })}
      </section>

      ${htmlGradeMetricas({
        payMode: usuario.pay_mode,
        r, noMes, total, cmp, temAnt,
        mesAntNome: nomeMes(somaMeses(mesRef, -1)),
        periodoTxt,
      })}

      <section class="cartao" style="margin-top:16px">
        <div class="cartao-topo">
          <h2 class="cartao-titulo">${fixo ? (usuario.pay_mode === 'shift' ? 'Turnos por dia' : 'Tarefas por dia') : 'Horas por dia'}</h2>
          <span class="apagado" style="font-size:13px">${esc(plural(r.turnos, usuario.pay_mode === 'shift' ? 'turno' : (fixo ? 'tarefa' : 'turno'), usuario.pay_mode === 'shift' ? 'turnos' : (fixo ? 'tarefas' : 'turnos')))} no mês</span>
        </div>
        <div class="grafico" id="g-dias"></div>
        <div id="t-dias"></div>
      </section>

      <section class="cartao">
        <div class="cartao-topo"><h2 class="cartao-titulo">Mês a mês</h2>
          <span class="apagado" style="font-size:13px">trabalho + bônus · toque na barra</span></div>
        <div class="grafico" id="g-meses"></div>
      </section>

      <section class="cartao" style="margin-top:16px">
        <div class="cartao-topo">
          <h2 class="cartao-titulo">Seus turnos</h2>
          <span class="apagado">${esc(plural(noMes.length, 'turno', 'turnos'))}</span>
        </div>
        ${noMes.length ? `<div class="lista">${noMes.map(linhaDoTurno).join('')}</div>`
          : vazio({ emoji: '🌱', titulo: 'Nenhum turno neste mês',
                    texto: 'Quando a administração lançar ou você bater o ponto, aparece aqui.' })}
      </section>

      ${pagamentos.length ? `
        <section class="cartao" style="margin-top:16px">
          <div class="cartao-topo">
            <h2 class="cartao-titulo">Pagamentos recebidos</h2>
            <span class="apagado num" style="font-size:14px">${esc(money(pago))}</span>
          </div>
          <div class="lista">${pagamentos.map((pg, i) => `
            <div class="item"${i >= 4 ? ' hidden data-pag-extra' : ''}>
              <div class="item-corpo">
                <div class="item-titulo">${esc(pg.title)}</div>
                <div class="item-sub">${esc(dataBR(pg.paid_on))}${pg.note ? ` · ${esc(String(pg.note).slice(0, 80))}` : ''}</div>
              </div>
              <div class="item-fim">
                <div class="num" style="font-weight:600">${esc(money(pg.amount))}</div>
              </div>
            </div>`).join('')}</div>
          ${pagamentos.length > 4 ? `
            <button class="btn btn-pequeno btn-fantasma" data-mais-pag style="width:100%;margin-top:10px">
              Ver mais ${esc(String(pagamentos.length - 4))}
            </button>
            <button class="btn btn-pequeno btn-fantasma" data-menos-pag hidden style="width:100%;margin-top:10px">
              Ver menos
            </button>` : ''}
        </section>` : ''}
    `;

    const serieD = serieDoMes(mesRef, r.porDia);
    const metricaDia = fixo ? 'qtd' : 'horas';
    try { graficoDias($('#g-dias', raiz), serieD, { cor: PALETA[0], metrica: metricaDia }); } catch { /* gráfico opcional */ }
    $('#t-dias', raiz).innerHTML = tabelaDeApoio(
      serieD.filter((d) => (fixo ? d.qtd : d.horas) > 0).map((d) => [
        dataCurta(d.data),
        fixo ? String(d.qtd || 0) : horasCurto(d.horas),
        money(d.valor),
      ]),
      ['Dia', fixo ? (usuario.pay_mode === 'shift' ? 'Turnos' : 'Tarefas') : 'Horas', 'Valor'],
    );
    try { graficoMeses($('#g-meses', raiz), serieDeMeses(turnos, mesRef, 6, new Date(), bonusTodos)); } catch { /* gráfico opcional */ }
    try { pintaPizzas(raiz, r.porTarefa, grupos, { porTurno, payMode: usuario.pay_mode }); } catch { /* gráfico opcional */ }

    const recarregaMes = async () => {
      raiz.innerHTML = carregando('Somando suas horas…');
      await desenha();
      raiz.scrollIntoView({ block: 'start', behavior: 'smooth' });
    };

    $$('[data-mes]', raiz).forEach((b) => b.addEventListener('click', async () => {
      mesRef = somaMeses(mesRef, +b.dataset.mes);
      await recarregaMes();
    }));
    $('[data-mes-escolhe]', raiz)?.addEventListener('change', async (ev) => {
      const [y, mo] = ev.target.value.split('-').map(Number);
      mesRef = inicioDoMes(new Date(y, mo - 1, 1));
      await recarregaMes();
    });

    $('[data-mais-pag]', raiz)?.addEventListener('click', () => {
      $$('[data-pag-extra]', raiz).forEach((el) => { el.hidden = false; });
      $('[data-mais-pag]', raiz).hidden = true;
      $('[data-menos-pag]', raiz).hidden = false;
    });
    $('[data-menos-pag]', raiz)?.addEventListener('click', () => {
      $$('[data-pag-extra]', raiz).forEach((el) => { el.hidden = true; });
      $('[data-mais-pag]', raiz).hidden = false;
      $('[data-menos-pag]', raiz).hidden = true;
    });
  }

  function linhaDoTurno(t) {
    const h = horasDoTurno(t);
    const v = valorDoTurno(t);
    const fixo = pagamentoFixo(t.pay_mode);
    const nomes = t.period
      ? `Turno ${nomePeriodo(t.period)}`
      : ([...new Set((t.segments || []).map((s) => s.task_name))].join(', ') || 'sem tarefa');
    const cor = t.segments?.[0]?.cor || PALETA[0];
    const quando = fixo
      ? `${hora(t.started_at)} · concluído`
      : `${hora(t.started_at)} → ${t.ended_at ? hora(t.ended_at) : 'em aberto'}`;
    return `
      <div class="item">
        <span class="item-faixa" style="background:${esc(cor)}"></span>
        <div class="item-corpo">
          <div class="item-titulo">${esc(maiuscula(dataLonga(t.started_at)))}</div>
          <div class="item-sub">
            ${esc(quando)}
            ${t.company_name ? ` · ${esc(t.company_name)}` : ''}
            · ${esc(nomes)}
            ${t.source === 'import' ? ' · importado' : t.source === 'manual' ? ' · lançado na mão' : ''}
          </div>
        </div>
        <div class="item-fim">
          ${fixo
            ? `<div class="num" style="font-weight:600">${esc(money(v))}</div>`
            : `<div class="num" style="font-weight:600">${esc(horasCurto(h))}</div>
               <div class="num apagado" style="font-size:13px">${esc(money(v))}</div>`}
        </div>
      </div>`;
  }

  await desenha();
  return { destruir() {} };
}
