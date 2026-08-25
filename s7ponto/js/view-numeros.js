/* ==========================================================================
   S7 PONTO — "Meus números": quanto entrou, quantas horas, e como ficou
   comparado com o mês passado.
   ========================================================================== */
import { store } from './store.js';
import {
  esc, money, moneyShort, horas, horasCurto, num, pct, mesAno, dataLonga,
  dataCurta, hora, somaMeses, inicioDoMes, fimDoMes, diaChave, plural,
  baixaArquivo, csvLinha, dataBR, maiuscula, nomeMes,
} from './util.js';
import { $, $$, ICONE, carregando, vazio, torrada } from './ui.js';
import { graficoDias, graficoMeses, graficoTarefas, tabelaDeApoio, PALETA } from './charts.js';
import {
  pintaTrechos, resumoDoMes, serieDoMes, serieDeMeses,
  horasDoTurno, valorDoTurno,
} from './metricas.js';

export async function telaDeNumeros(raiz, ctx) {
  const { usuario } = ctx;
  let mesRef = inicioDoMes(new Date());
  let turnos = [];

  raiz.innerHTML = carregando('Somando suas horas…');
  turnos = pintaTrechos(
    await store.listaTurnos({ userId: usuario.id }),
    await store.listaTarefas(true),
  );

  const primeiroTurno = turnos.length
    ? inicioDoMes(turnos[turnos.length - 1].started_at)
    : inicioDoMes(new Date());

  function desenha() {
    const r = resumoDoMes(turnos, mesRef);
    const noMes = turnos.filter((t) => {
      const d = new Date(t.started_at);
      return d >= inicioDoMes(mesRef) && d <= fimDoMes(mesRef);
    });

    const ehMesCorrente = diaChave(mesRef).slice(0, 7) === diaChave(new Date()).slice(0, 7);
    const temAnterior = r.anterior.valor > 0 || r.anterior.horas > 0;
    const dv = r.variacao.valor;
    const fichaVar = !temAnterior
      ? '<span class="ficha ficha-neutra">primeiro mês com registro</span>'
      : `<span class="ficha ${dv.abs >= 0 ? 'ficha-alta' : 'ficha-baixa'}">
           ${dv.abs >= 0 ? ICONE.cima : ICONE.baixo}
           ${esc(money(Math.abs(dv.abs)))}${dv.pct !== null ? ` · ${esc(pct(dv.pct))}` : ''}
         </span>
         <span class="ficha ficha-neutra">${esc(nomeMes(somaMeses(mesRef, -1)))}: ${esc(moneyShort(r.anterior.valor))}</span>`;

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
          <p class="heroi-valor" style="color:var(--salvia-alt)">${esc(money(r.valor))}</p>
          <div class="heroi-nota">${fichaVar}</div>
        </div>
      </section>

      <section class="grade-metricas" style="margin-top:16px">
        <div class="metrica">
          <div class="metrica-rotulo">Horas trabalhadas</div>
          <div class="metrica-valor">${esc(horas(r.horas))}</div>
          ${temAnterior ? `<div class="metrica-nota">${esc(horas(Math.abs(r.variacao.horas.abs)))} ${r.variacao.horas.abs >= 0 ? 'a mais' : 'a menos'} que em ${esc(nomeMes(somaMeses(mesRef, -1)))}</div>` : ''}
        </div>
        <div class="metrica">
          <div class="metrica-rotulo">Média por dia trabalhado</div>
          <div class="metrica-valor">${esc(horas(r.mediaHorasPorDia))}</div>
          <div class="metrica-nota">${esc(money(r.mediaValorPorDia))} por dia</div>
        </div>
        <div class="metrica">
          <div class="metrica-rotulo">Dias trabalhados</div>
          <div class="metrica-valor">${esc(String(r.diasTrabalhados))}</div>
          ${temAnterior ? `<div class="metrica-nota">${esc(plural(Math.abs(r.variacao.dias.abs), 'dia', 'dias'))} ${r.variacao.dias.abs >= 0 ? 'a mais' : 'a menos'} que no mês passado</div>` : ''}
        </div>
        <div class="metrica">
          <div class="metrica-rotulo">Dias por semana</div>
          <div class="metrica-valor">${esc(num(r.mediaDiasPorSemana, 1))}</div>
          <div class="metrica-nota">na média do mês</div>
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
          <span class="apagado" style="font-size:13px">últimos 6 meses</span></div>
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

    /* gráficos */
    const serieD = serieDoMes(mesRef, r.porDia);
    graficoDias($('#g-dias', raiz), serieD, { cor: PALETA[0] });
    $('#t-dias', raiz).innerHTML = tabelaDeApoio(
      serieD.filter((d) => d.horas > 0).map((d) => [dataCurta(d.data), horasCurto(d.horas), money(d.valor)]),
      ['Dia', 'Horas', 'Valor'],
    );
    graficoTarefas($('#g-tarefas', raiz), r.porTarefa);
    graficoMeses($('#g-meses', raiz), serieDeMeses(turnos, mesRef, 6), { cor: PALETA[0] });

    /* navegação */
    $$('[data-mes]', raiz).forEach((b) => b.addEventListener('click', () => {
      mesRef = somaMeses(mesRef, +b.dataset.mes);
      desenha();
      raiz.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }));

    $('[data-exporta]', raiz)?.addEventListener('click', () => exporta(noMes, r));
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

  function exporta(lista, r) {
    if (!lista.length) { torrada('Não há turnos neste mês para baixar.', 'ruim'); return; }
    const linhas = [csvLinha(['Data', 'Entrada', 'Saída', 'Tarefa', 'Horas', 'R$/h', 'Valor'])];
    for (const t of lista) {
      for (const s of t.segments || []) {
        const h = (new Date(s.ended_at || new Date()) - new Date(s.started_at)) / 3600000;
        linhas.push(csvLinha([
          dataBR(s.started_at), hora(s.started_at), s.ended_at ? hora(s.ended_at) : '',
          s.task_name, num(h, 2), num(+s.hourly_rate, 2), num(h * (+s.hourly_rate || 0), 2),
        ]));
      }
    }
    linhas.push('');
    linhas.push(csvLinha(['TOTAL', '', '', '', num(r.horas, 2), '', num(r.valor, 2)]));
    baixaArquivo(`s7ponto-${usuario.username}-${diaChave(mesRef).slice(0, 7)}.csv`, linhas.join('\n'));
    torrada('Extrato baixado.', 'bom');
  }

  desenha();
  return { destruir() {} };
}
