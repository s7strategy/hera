/* ==========================================================================
   S7 PONTO — as contas. Todo número que aparece na tela nasce aqui.
   Regra: horas e dinheiro sempre vêm dos TRECHOS (segments), porque é neles
   que mora o valor da hora congelado no momento em que o trabalho aconteceu.
   ========================================================================== */
import {
  diaChave, inicioDoMes, fimDoMes, somaMeses, inicioDaSemana, somaDias,
  inicioDoDia, mesAno, nomeMes, horasEntre,
} from './util.js';
import { corDaSerie } from './charts.js';

/** Um trecho vale (horas × R$/h). Trecho aberto conta até "agora". */
export const horasDoTrecho = (t, agora = new Date()) =>
  horasEntre(t.started_at, t.ended_at || agora);
export const valorDoTrecho = (t, agora = new Date()) =>
  horasDoTrecho(t, agora) * (+t.hourly_rate || 0);

export const horasDoTurno = (turno, agora = new Date()) =>
  (turno.segments || []).reduce((s, t) => s + horasDoTrecho(t, agora), 0);
export const valorDoTurno = (turno, agora = new Date()) =>
  (turno.segments || []).reduce((s, t) => s + valorDoTrecho(t, agora), 0);

/* ==========================================================================
   Agregação de um conjunto de turnos
   ========================================================================== */

/**
 * @returns {{
 *   horas, valor, turnos,
 *   porDia: Map<'AAAA-MM-DD', {horas, valor, data}>,
 *   porTarefa: Map<nome, {nome, horas, valor, cor}>,
 *   porPessoa: Map<user_id, {horas, valor, turnos}>
 * }}
 */
export function agrega(turnos, agora = new Date()) {
  const porDia = new Map();
  const porTarefa = new Map();
  const porPessoa = new Map();
  let horas = 0, valor = 0;

  for (const turno of turnos) {
    const dia = diaChave(turno.started_at);
    if (!porDia.has(dia)) porDia.set(dia, { horas: 0, valor: 0, data: inicioDoDia(turno.started_at) });
    if (!porPessoa.has(turno.user_id)) porPessoa.set(turno.user_id, { horas: 0, valor: 0, turnos: 0 });
    porPessoa.get(turno.user_id).turnos += 1;

    for (const trecho of turno.segments || []) {
      const h = horasDoTrecho(trecho, agora);
      const v = h * (+trecho.hourly_rate || 0);
      horas += h; valor += v;

      const d = porDia.get(dia); d.horas += h; d.valor += v;
      const p = porPessoa.get(turno.user_id); p.horas += h; p.valor += v;

      const nome = trecho.task_name || 'Sem tarefa';
      if (!porTarefa.has(nome)) porTarefa.set(nome, { nome, horas: 0, valor: 0, cor: null });
      const t = porTarefa.get(nome); t.horas += h; t.valor += v;
      if (!t.cor && trecho.cor) t.cor = trecho.cor;
    }
  }

  // cor: usa a da tarefa quando existe; senão, a próxima da ordem fixa
  [...porTarefa.values()]
    .sort((a, b) => b.horas - a.horas)
    .forEach((t, i) => { t.cor ??= corDaSerie(i); });

  return { horas, valor, turnos: turnos.length, porDia, porTarefa, porPessoa };
}

/** Pinta cada trecho com a cor cadastrada da tarefa, quando ela ainda existe. */
export function pintaTrechos(turnos, tarefas) {
  const porId = new Map(tarefas.map((t) => [t.id, t]));
  const porNome = new Map(tarefas.map((t) => [t.name, t]));
  for (const turno of turnos) {
    for (const trecho of turno.segments || []) {
      const t = porId.get(trecho.task_id) || porNome.get(trecho.task_name);
      trecho.cor = t?.color || null;
    }
  }
  return turnos;
}

/* ==========================================================================
   Resumo de um mês, já comparado com o mês anterior
   ========================================================================== */

export function resumoDoMes(turnos, mesRef, agora = new Date()) {
  const ini = inicioDoMes(mesRef), fim = fimDoMes(mesRef);
  const iniAnt = inicioDoMes(somaMeses(mesRef, -1)), fimAnt = fimDoMes(somaMeses(mesRef, -1));

  const noPeriodo = (de, ate) => turnos.filter((t) => {
    const d = new Date(t.started_at);
    return d >= de && d <= ate;
  });

  const mes = agrega(noPeriodo(ini, fim), agora);
  const ant = agrega(noPeriodo(iniAnt, fimAnt), agora);

  const diasTrabalhados = [...mes.porDia.values()].filter((d) => d.horas > 0).length;
  const diasAnt = [...ant.porDia.values()].filter((d) => d.horas > 0).length;

  // semanas efetivamente cobertas pelo mês — pra média de dias por semana
  const semanas = new Set([...mes.porDia.values()].filter((d) => d.horas > 0)
    .map((d) => diaChave(inicioDaSemana(d.data)))).size || 1;

  const varia = (novo, velho) => {
    if (!velho) return { abs: novo, pct: null };
    return { abs: novo - velho, pct: ((novo - velho) / velho) * 100 };
  };

  return {
    mesRef: ini,
    horas: mes.horas,
    valor: mes.valor,
    turnos: mes.turnos,
    diasTrabalhados,
    mediaHorasPorDia: diasTrabalhados ? mes.horas / diasTrabalhados : 0,
    mediaDiasPorSemana: diasTrabalhados / semanas,
    mediaValorPorDia: diasTrabalhados ? mes.valor / diasTrabalhados : 0,
    porDia: mes.porDia,
    porTarefa: [...mes.porTarefa.values()].sort((a, b) => b.horas - a.horas),
    anterior: {
      horas: ant.horas, valor: ant.valor, diasTrabalhados: diasAnt,
      mediaHorasPorDia: diasAnt ? ant.horas / diasAnt : 0,
    },
    variacao: {
      valor: varia(mes.valor, ant.valor),
      horas: varia(mes.horas, ant.horas),
      dias:  varia(diasTrabalhados, diasAnt),
    },
  };
}

/* ==========================================================================
   Séries prontas para os gráficos
   ========================================================================== */

/** Todos os dias do mês, inclusive os zerados — o buraco também informa. */
export function serieDoMes(mesRef, porDia) {
  const ini = inicioDoMes(mesRef), fim = fimDoMes(mesRef);
  const hoje = new Date();
  const fimReal = fim > hoje ? hoje : fim;
  const saida = [];
  for (let d = new Date(ini); d <= fimReal; d = somaDias(d, 1)) {
    const reg = porDia.get(diaChave(d));
    saida.push({ data: new Date(d), horas: reg?.horas || 0, valor: reg?.valor || 0 });
  }
  return saida;
}

/** Os últimos N meses de ganhos, terminando no mês de referência. */
export function serieDeMeses(turnos, mesRef, quantos = 6, agora = new Date()) {
  const saida = [];
  for (let i = quantos - 1; i >= 0; i--) {
    const m = somaMeses(mesRef, -i);
    const ini = inicioDoMes(m), fim = fimDoMes(m);
    const a = agrega(turnos.filter((t) => {
      const d = new Date(t.started_at);
      return d >= ini && d <= fim;
    }), agora);
    saida.push({
      rotulo: nomeMes(m).slice(0, 3),
      rotuloLongo: mesAno(m),
      valor: a.valor, horas: a.horas, atual: i === 0,
    });
  }
  return saida;
}

/** A semana da data, de segunda a domingo. */
export function serieDaSemana(refData, porDia) {
  const ini = inicioDaSemana(refData);
  return Array.from({ length: 7 }, (_, i) => {
    const d = somaDias(ini, i);
    const reg = porDia.get(diaChave(d));
    return { data: d, horas: reg?.horas || 0, valor: reg?.valor || 0 };
  });
}

/** Total da semana corrente — o "e esta semana?" da tela inicial. */
export function resumoDaSemana(turnos, refData = new Date(), agora = new Date()) {
  const ini = inicioDaSemana(refData);
  const fim = somaDias(ini, 7);
  const a = agrega(turnos.filter((t) => {
    const d = new Date(t.started_at);
    return d >= ini && d < fim;
  }), agora);
  const dias = [...a.porDia.values()].filter((d) => d.horas > 0).length;
  return { horas: a.horas, valor: a.valor, dias, inicio: ini };
}

/** Total do dia — o "e hoje?" da tela inicial. */
export function resumoDoDia(turnos, refData = new Date(), agora = new Date()) {
  const chave = diaChave(refData);
  const a = agrega(turnos.filter((t) => diaChave(t.started_at) === chave), agora);
  return { horas: a.horas, valor: a.valor, turnos: a.turnos };
}
