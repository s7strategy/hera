/* ==========================================================================
   S7 PONTO — "Meus números": quanto entrou, quantas horas, e como ficou
   comparado com o mês passado. Trabalho + bônus (separados e no total).
   ========================================================================== */
import { store } from './store.js';
import {
  esc, money, moneyShort, horas, horasCurto, num, pct, mesAno, dataLonga,
  dataCurta, hora, somaMeses, inicioDoMes, fimDoMes, diaChave, plural,
  baixaArquivo, csvLinha, dataBR, maiuscula, nomeMes, chaveMes,
} from './util.js';
import { $, $$, ICONE, carregando, vazio, torrada } from './ui.js';
import { graficoDias, graficoMeses, graficoTarefas, tabelaDeApoio, PALETA } from './charts.js';
import {
  pintaTrechos, resumoDoMes, serieDoMes, serieDeMeses,
  horasDoTurno, valorDoTurno, somaBonus, totalComBonus, somaPagamentos,
} from './metricas.js';

export async function telaDeNumeros(raiz, ctx) {
  const { usuario } = ctx;
  let mesRef = inicioDoMes(new Date());
  let turnos = [];
  let bonusMes = [];

  raiz.innerHTML = carregando('Somando suas horas…');
  turnos = pintaTrechos(
    await store.listaTurnos({ userId: usuario.id }),
    await store.listaTarefas(true),
  );

  const primeiroTurno = turnos.length
    ? inicioDoMes(turnos[turnos.length - 1].started_at)
    : inicioDoMes(new Date());

  async function carregaBonus() {
    try {
      bonusMes = await store.listaBonusMes({
        userId: usuario.id, yearMonth: chaveMes(mesRef),
      });
    } catch {
      bonusMes = [];
    }
  }

  async function desenha() {
    await carregaBonus();
    let pagamentos = [];
    try {
      pagamentos = await store.listaPagamentos({
        userId: usuario.id, yearMonth: chaveMes(mesRef),
      });
    } catch { pagamentos = []; }
    const r = resumoDoMes(turnos, mesRef);
    const bonus = somaBonus(bonusMes);
    const total = totalComBonus(r.valor, bonusMes);
    const pago = somaPagamentos(pagamentos);
    const noMes = turnos.filter((t) => {
      const d = new Date(t.started_at);
      return d >= inicioDoMes(mesRef) && d <= fimDoMes(mesRef);
    });

    const ehMesCorrente = chaveMes(mesRef) === chaveMes(new Date());
    const temAnterior = r.anterior.valor > 0 || r.anterior.horas > 0;
    const dv = r.variacao.valor;
    const fichaVar = !temAnterior
      ? '<span class="ficha ficha-neutra">primeiro mês com registro</span>'
      : `<span class="ficha ${dv.abs >= 0 ? 'ficha-alta' : 'ficha-baixa'}">
           ${dv.abs >= 0 ? ICONE.cima : ICONE.baixo}
           ${esc(money(Math.abs(dv.abs)))}${dv.pct !== null ? ` · ${esc(pct(dv.pct))}` : ''}
         </span>
         <span class="ficha ficha-neutra">${esc(nomeMes(somaMeses(mesRef, -1)))}: trabalho ${esc(moneyShort(r.anterior.valor))}</span>`;

    const podeAvancar = somaMeses(mesRef, 1) <= inicioDoMes(new Date());
    const podeVoltar = somaMeses(mesRef, -1) >= somaMeses(primeiroTurno, -1);

    raiz.innerHTML = `
      <nav class="mes-nav">
        <button class="mes-nav-btn" data-mes="-1" ${podeVoltar ? '' : 'disabled'} aria-label="Mês anterior">${ICONE.esquerda}</button>
        <div class="mes-nav-titulo">${esc(maiuscula(mesAno(mesRef)))}</div>
        <button class="mes-nav-btn" data-mes="1" ${podeAvancar ? '' : 'disabled'} aria-label="Próximo mês">${ICONE.direita}</button>
      </nav>

      <section class="cartao">
        <div class="heroi">
          <p class="heroi-rotulo">${ehMesCorrente
            ? 'Você recebe neste mês'
            : `Você recebeu em ${esc(nomeMes(mesRef))}`}</p>
          <p class="heroi-valor" style="color:var(--salvia-alt)">${esc(money(total))}</p>
          <div class="heroi-nota">
            <span class="ficha ficha-neutra">trabalho ${esc(money(r.valor))}</span>
            ${bonus ? `<span class="ficha ficha-neutra">bônus ${esc(money(bonus))}</span>` : ''}
            ${pago ? `<span class="ficha ficha-neutra">já recebido ${esc(money(pago))}</span>` : ''}
            ${fichaVar}
          </div>
        </div>
      </section>

      ${bonusMes.length ? `
        <section class="cartao" style="margin-top:16px">
          <div class="cartao-topo">
            <h2 class="cartao-titulo">Bônus do mês</h2>
            <span class="apagado num" style="font-size:14px">${esc(money(bonus))}</span>
          </div>
          <div class="lista">${bonusMes.map((e) => `
            <div class="item">
              <div class="item-corpo">
                <div class="item-titulo">${esc(e.title)}</div>
                ${e.note ? `<div class="item-sub">${esc(e.note)}</div>` : ''}
              </div>
              <div class="item-fim">
                <div class="num" style="font-weight:600;color:var(--salvia-alt)">${esc(money(e.amount))}</div>
              </div>
            </div>`).join('')}</div>
        </section>` : ''}

      ${pagamentos.length ? `
        <section class="cartao" style="margin-top:16px">
          <div class="cartao-topo">
            <h2 class="cartao-titulo">Pagamentos recebidos</h2>
            <span class="apagado num" style="font-size:14px">${esc(money(pago))}</span>
          </div>
          <div class="lista">${pagamentos.map((pg) => `
            <div class="item">
              <div class="item-corpo">
                <div class="item-titulo">${esc(pg.title)}</div>
                <div class="item-sub">${esc(dataBR(pg.paid_on))}${pg.note ? ` · ${esc(String(pg.note).slice(0, 80))}` : ''}</div>
              </div>
              <div class="item-fim">
                <div class="num" style="font-weight:600">${esc(money(pg.amount))}</div>
              </div>
            </div>`).join('')}</div>
        </section>` : ''}

      <section class="grade-metricas" style="margin-top:16px">
        <div class="metrica">
          <div class="metrica-rotulo">Do trabalho</div>
          <div class="metrica-valor" style="color:var(--salvia-alt)">${esc(money(r.valor))}</div>
          <div class="metrica-nota">${esc(horas(r.horas))} trabalhadas</div>
        </div>
        <div class="metrica">
          <div class="metrica-rotulo">Horas trabalhadas</div>
          <div class="metrica-valor">${esc(horas(r.horas))}</div>
          ${temAnterior ? `<div class="metrica-nota">${esc(horas(Math.abs(r.variacao.horas.abs)))} ${r.variacao.horas.abs >= 0 ? 'a mais' : 'a menos'} que em ${esc(nomeMes(somaMeses(mesRef, -1)))}</div>` : ''}
        </div>
        <div class="metrica">
          <div class="metrica-rotulo">Dias trabalhados</div>
          <div class="metrica-valor">${esc(String(r.diasTrabalhados))}</div>
          ${temAnterior ? `<div class="metrica-nota">${esc(plural(Math.abs(r.variacao.dias.abs), 'dia', 'dias'))} ${r.variacao.dias.abs >= 0 ? 'a mais' : 'a menos'} que no mês passado</div>` : ''}
        </div>
        <div class="metrica">
          <div class="metrica-rotulo">Média por dia</div>
          <div class="metrica-valor">${esc(horas(r.mediaHorasPorDia))}</div>
          <div class="metrica-nota">${esc(money(r.mediaValorPorDia))} por dia (trabalho)</div>
        </div>
      </section>

      <section class="cartao" style="margin-top:16px">
        <div class="cartao-topo">
          <h2 class="cartao-titulo">Horas por dia</h2>
          <span class="apagado" style="font-size:13px">${esc(plural(r.turnos, 'turno', 'turnos'))} no mês</span>
        </div>
        <div class="grafico" id="g-dias"></div>
        <div id="t-dias"></div>
      </section>

      <section class="cartao">
        <div class="cartao-topo"><h2 class="cartao-titulo">Onde foram suas horas</h2></div>
        <div class="grafico" id="g-tarefas"></div>
      </section>

      <section class="cartao">
        <div class="cartao-topo"><h2 class="cartao-titulo">Mês a mês</h2>
          <span class="apagado" style="font-size:13px">últimos 6 meses (trabalho)</span></div>
        <div class="grafico" id="g-meses"></div>
      </section>

      <section class="cartao">
        <div class="cartao-topo">
          <h2 class="cartao-titulo">Seus turnos</h2>
          <button class="btn btn-pequeno btn-fantasma" data-exporta>${ICONE.baixar}<span>Baixar extrato</span></button>
        </div>
        ${noMes.length ? `<div class="lista">${noMes.map(linhaDoTurno).join('')}</div>`
          : vazio({ emoji: '🌱', titulo: 'Nenhum turno neste mês',
                    texto: 'Quando você bater o ponto, ele aparece aqui.' })}
      </section>`;

    const serieD = serieDoMes(mesRef, r.porDia);
    graficoDias($('#g-dias', raiz), serieD, { cor: PALETA[0] });
    $('#t-dias', raiz).innerHTML = tabelaDeApoio(
      serieD.filter((d) => d.horas > 0).map((d) => [dataCurta(d.data), horasCurto(d.horas), money(d.valor)]),
      ['Dia', 'Horas', 'Valor'],
    );
    graficoTarefas($('#g-tarefas', raiz), r.porTarefa);
    graficoMeses($('#g-meses', raiz), serieDeMeses(turnos, mesRef, 6), { cor: PALETA[0] });

    $$('[data-mes]', raiz).forEach((b) => b.addEventListener('click', async () => {
      mesRef = somaMeses(mesRef, +b.dataset.mes);
      raiz.innerHTML = carregando('Somando suas horas…');
      await desenha();
      raiz.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }));

    $('[data-exporta]', raiz)?.addEventListener('click', () => exporta(noMes, r, bonusMes, total));
  }

  function linhaDoTurno(t) {
    const h = horasDoTurno(t);
    const v = valorDoTurno(t);
    const nomes = [...new Set((t.segments || []).map((s) => s.task_name))];
    const cor = t.segments?.[0]?.cor || PALETA[0];
    return `
      <div class="item">
        <span class="item-faixa" style="background:${esc(cor)}"></span>
        <div class="item-corpo">
          <div class="item-titulo">${esc(maiuscula(dataLonga(t.started_at)))}</div>
          <div class="item-sub">
            ${esc(hora(t.started_at))} → ${t.ended_at ? esc(hora(t.ended_at)) : '<em>em aberto</em>'}
            ${t.company_name ? ` · ${esc(t.company_name)}` : ''}
            · ${esc(nomes.join(', ') || 'sem tarefa')}
            ${t.source === 'import' ? ' · importado' : t.source === 'manual' ? ' · lançado pelo admin' : ''}
          </div>
        </div>
        <div class="item-fim">
          <div class="num" style="font-weight:600">${esc(horasCurto(h))}</div>
          <div class="num apagado" style="font-size:13px">${esc(money(v))}</div>
        </div>
      </div>`;
  }

  function exporta(lista, r, bons, total) {
    if (!lista.length && !bons.length) {
      torrada('Não há nada neste mês para baixar.', 'ruim');
      return;
    }
    const linhas = [csvLinha(['Tipo', 'Data', 'Entrada', 'Saída', 'Empresa', 'Título', 'Horas', 'Valor'])];
    for (const t of lista) {
      for (const s of t.segments || []) {
        const h = (new Date(s.ended_at || new Date()) - new Date(s.started_at)) / 3600000;
        const v = (s.flat_amount != null && s.flat_amount !== '')
          ? +s.flat_amount
          : h * (+s.hourly_rate || 0);
        linhas.push(csvLinha([
          'trabalho', dataBR(s.started_at), hora(s.started_at), s.ended_at ? hora(s.ended_at) : '',
          t.company_name || '', s.task_name, num(h, 2), num(v, 2),
        ]));
      }
    }
    for (const e of bons) {
      linhas.push(csvLinha(['bônus', chaveMes(mesRef), '', '', '', e.title, '', num(+e.amount, 2)]));
    }
    linhas.push('');
    linhas.push(csvLinha(['TOTAL trabalho', '', '', '', '', '', num(r.horas, 2), num(r.valor, 2)]));
    linhas.push(csvLinha(['TOTAL bônus', '', '', '', '', '', '', num(somaBonus(bons), 2)]));
    linhas.push(csvLinha(['TOTAL geral', '', '', '', '', '', '', num(total, 2)]));
    baixaArquivo(`s7ponto-${usuario.username}-${chaveMes(mesRef)}.csv`, linhas.join('\n'));
    torrada('Extrato baixado.', 'bom');
  }

  await desenha();
  return { destruir() {} };
}
