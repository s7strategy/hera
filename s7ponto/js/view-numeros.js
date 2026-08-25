/* ==========================================================================
   S7 PONTO — "Meus números": quanto entrou, quantas horas, e como ficou
   comparado com o mesmo período do mês passado. Trabalho + bônus no total.
   ========================================================================== */
import { store } from './store.js';
import {
  esc, money, moneyShort, horas, horasCurto, pct, mesAno, dataLonga,
  dataCurta, hora, somaMeses, inicioDoMes, fimDoMes, plural,
  dataBR, maiuscula, nomeMes, chaveMes, nomePeriodo,
} from './util.js';
import { $, $$, ICONE, carregando, vazio } from './ui.js';
import { graficoDias, graficoMeses, tabelaDeApoio, PALETA } from './charts.js';
import {
  pintaTrechos, resumoDoMes, serieDoMes, serieDeMeses,
  horasDoTurno, valorDoTurno, somaBonus, totalComBonus, somaPagamentos,
  agrupaBonus, comparaSaldo, saldosPorPessoa,
} from './metricas.js';
import { htmlRecibo, htmlPizzas, pintaPizzas, htmlDetalheBonus } from './extrato.js';
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
    try {
      const [doMes] = await Promise.all([
        store.listaBonusMes({ userId: usuario.id, yearMonth: ym }),
        store.listaBonusMes({ userId: usuario.id, yearMonth: ymAnt }).catch(() => []),
      ]);
      bonusMes = doMes;
      const todos = await store.listaBonusPessoa(usuario.id);
      const porId = new Map((todos || []).map((e) => [e.id, e]));
      for (const e of bonusMes) porId.set(e.id, e);
      bonusTodos = [...porId.values()];
    } catch {
      bonusMes = [];
      bonusTodos = [];
    }
  }

  async function desenha() {
    turnos = pintaTrechos(
      await store.listaTurnos({ userId: usuario.id }),
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
    const taxaTrabalho = r.horas > 0.001 ? r.valor / r.horas : 0;
    const taxaGeral = r.horas > 0.001 ? total / r.horas : 0;
    const bancoExtra = extraDoPeriodo(noMes);

    const falta = Math.max(0, total - pago);
    const emDia = total > 0.004 && falta < 0.5;
    const ehMesCorrente = chaveMes(mesRef) === chaveMes(new Date());
    const saldoGeral = saldosPorPessoa({
      pessoas: [usuario], turnos, bonus: bonusTodos, pagamentos: pagsTodos,
    })[0];
    const outrosAbertos = (saldoGeral?.abertoPassado || 0) + (saldoGeral?.abertoAntes || 0);
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
      <nav class="mes-nav barra-mes-sticky" aria-label="Escolher o mês">
        <button class="mes-nav-btn" data-mes="-1" ${podeVoltar ? '' : 'disabled'} aria-label="Mês anterior">${ICONE.esquerda}</button>
        <label class="mes-nav-escolhe">
          <select class="mes-nav-titulo" data-mes-escolhe aria-label="Ver outro mês">
            ${meses.map((m) => `<option value="${esc(chaveMes(m))}" ${chaveMes(m) === chaveMes(mesRef) ? 'selected' : ''}>${esc(maiuscula(mesAno(m)))}</option>`).join('')}
          </select>
        </label>
        <button class="mes-nav-btn" data-mes="1" ${podeAvancar ? '' : 'disabled'} aria-label="Próximo mês">${ICONE.direita}</button>
      </nav>

      <section class="cartao">
        <div class="heroi">
          <p class="heroi-rotulo">${emDia
            ? (ehMesCorrente ? 'Tudo recebido neste mês' : `Tudo recebido em ${esc(nomeMes(mesRef))}`)
            : (ehMesCorrente ? 'Você tem a receber' : `A receber de ${esc(nomeMes(mesRef))}`)}</p>
          <p class="heroi-valor saldo">${esc(money(emDia ? total : falta))}</p>
          <div class="heroi-nota">
            <span class="ficha ficha-neutra">${esc(horas(r.horas))} trabalhadas</span>
            ${total > 0.004 ? `<span class="ficha ficha-neutra">ganhou ${esc(money(total))}${pago > 0.004 ? ` · recebeu ${esc(money(pago))}` : ''}</span>` : ''}
            ${htmlRecadoExtraPessoa(bancoExtra, { compacto: true })}
            ${fichaVar}
          </div>
          ${cmp.parcial ? `<p class="apagado" style="font-size:12.5px;margin-top:10px">Comparado até o dia ${esc(String(cmp.diaLimite))} (ontem), com bônus e extras — o dia de hoje fica de fora enquanto puder estar em aberto.</p>` : ''}
        </div>
        ${htmlRecibo({ horasMes: r.horas, trabalho: r.valor, grupos, total, pago })}
        ${htmlDetalheBonus(bonusMes)}
      </section>

      ${htmlRecadoExtraPessoa(bancoExtra, { nomeMes: nomeMes(mesRef) })}
      ${ehMesCorrente && outrosAbertos > 0.5 ? `
        <div class="recado info" style="margin-top:14px">
          <span class="recado-emoji">💸</span>
          <span>Ainda tem <strong>${esc(money(outrosAbertos))}</strong> a receber de meses anteriores.</span>
        </div>` : ''}

      <section class="cartao" style="margin-top:16px">
        <div class="cartao-topo">
          <h2 class="cartao-titulo">Seus turnos</h2>
          <span class="apagado">${esc(plural(noMes.length, 'turno', 'turnos'))}</span>
        </div>
        ${noMes.length ? `<div class="lista">${noMes.map(linhaDoTurno).join('')}</div>`
          : vazio({ emoji: '🌱', titulo: 'Nenhum turno neste mês',
                    texto: 'Quando a administração lançar ou você bater o ponto, aparece aqui.' })}
      </section>

      <section class="grade-metricas" style="margin-top:16px">
        <div class="metrica">
          <div class="metrica-rotulo">Horas no mês</div>
          <div class="metrica-valor">${esc(horas(r.horas))}</div>
          ${cmp.diaLimite > 0 && temAnt ? `<div class="metrica-nota">${esc(horas(Math.abs(cmp.variacao.horas.abs)))} ${cmp.variacao.horas.abs >= 0 ? 'a mais' : 'a menos'} que em ${esc(nomeMes(somaMeses(mesRef, -1)))} (${esc(periodoTxt)})</div>` : ''}
        </div>
        <div class="metrica">
          <div class="metrica-rotulo">Dias trabalhados</div>
          <div class="metrica-valor">${esc(String(r.diasTrabalhados))}</div>
          ${cmp.diaLimite > 0 && temAnt ? `<div class="metrica-nota">${esc(plural(Math.abs(cmp.variacao.dias.abs), 'dia', 'dias'))} ${cmp.variacao.dias.abs >= 0 ? 'a mais' : 'a menos'} que no mesmo período</div>` : ''}
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
      </section>

      <section class="cartao" style="margin-top:16px">
        ${htmlPizzas()}
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

      <section class="cartao" style="margin-top:16px">
        <div class="cartao-topo">
          <h2 class="cartao-titulo">Horas por dia</h2>
          <span class="apagado" style="font-size:13px">${esc(plural(r.turnos, 'turno', 'turnos'))} no mês</span>
        </div>
        <div class="grafico" id="g-dias"></div>
        <div id="t-dias"></div>
      </section>

      <section class="cartao">
        <div class="cartao-topo"><h2 class="cartao-titulo">Mês a mês</h2>
          <span class="apagado" style="font-size:13px">trabalho + bônus · toque na barra</span></div>
        <div class="grafico" id="g-meses"></div>
      </section>`;

    const serieD = serieDoMes(mesRef, r.porDia);
    graficoDias($('#g-dias', raiz), serieD, { cor: PALETA[0] });
    $('#t-dias', raiz).innerHTML = tabelaDeApoio(
      serieD.filter((d) => d.horas > 0).map((d) => [dataCurta(d.data), horasCurto(d.horas), money(d.valor)]),
      ['Dia', 'Horas', 'Valor'],
    );
    graficoMeses($('#g-meses', raiz), serieDeMeses(turnos, mesRef, 6, new Date(), bonusTodos));
    pintaPizzas(raiz, r.porTarefa, grupos);

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
    const nomes = t.period
      ? `Turno ${nomePeriodo(t.period)}`
      : ([...new Set((t.segments || []).map((s) => s.task_name))].join(', ') || 'sem tarefa');
    const cor = t.segments?.[0]?.cor || PALETA[0];
    return `
      <div class="item">
        <span class="item-faixa" style="background:${esc(cor)}"></span>
        <div class="item-corpo">
          <div class="item-titulo">${esc(maiuscula(dataLonga(t.started_at)))}</div>
          <div class="item-sub">
            ${esc(hora(t.started_at))} → ${t.ended_at ? esc(hora(t.ended_at)) : '<em>em aberto</em>'}
            ${t.company_name ? ` · ${esc(t.company_name)}` : ''}
            · ${esc(nomes)}
            ${t.source === 'import' ? ' · importado' : t.source === 'manual' ? ' · lançado na mão' : ''}
          </div>
        </div>
        <div class="item-fim">
          <div class="num" style="font-weight:600">${esc(horasCurto(h))}</div>
          <div class="num apagado" style="font-size:13px">${esc(money(v))}</div>
        </div>
      </div>`;
  }

  await desenha();
  return { destruir() {} };
}
