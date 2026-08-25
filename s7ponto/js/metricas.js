/* ==========================================================================
   S7 PONTO — as contas. Todo número que aparece na tela nasce aqui.
   Regra: horas e dinheiro sempre vêm dos TRECHOS (segments), porque é neles
   que mora o valor da hora congelado no momento em que o trabalho aconteceu.
   ========================================================================== */
import {
  diaChave, inicioDoMes, fimDoMes, somaMeses, inicioDaSemana, somaDias,
  inicioDoDia, mesAno, nomeMes, horasEntre, chaveMes, deDiaChave,
} from './util.js';
import { corDaSerie, PALETA } from './charts.js';

/** Um trecho vale (horas × R$/h) — ou o valor FIXO se flat_amount estiver preenchido. */
export const horasDoTrecho = (t, agora = new Date()) =>
  horasEntre(t.started_at, t.ended_at || agora);
export const valorDoTrecho = (t, agora = new Date()) => {
  if (t.flat_amount != null && t.flat_amount !== '') return +t.flat_amount || 0;
  return horasDoTrecho(t, agora) * (+t.hourly_rate || 0);
};

export const horasDoTurno = (turno, agora = new Date()) =>
  (turno.segments || []).reduce((s, t) => s + horasDoTrecho(t, agora), 0);
export const valorDoTurno = (turno, agora = new Date()) => {
  // pago por turno (manhã/tarde/noite): valor fixo do turno inteiro
  if ((turno.pay_mode === 'shift' || turno.flat_amount != null) && turno.flat_amount != null && turno.flat_amount !== '') {
    return +turno.flat_amount || 0;
  }
  return (turno.segments || []).reduce((s, t) => s + valorDoTrecho(t, agora), 0);
};

/** Soma dos bônus de um mês (lista de entries). */
export const somaBonus = (entries = []) =>
  (entries || []).reduce((s, e) => s + (+e.amount || 0), 0);

/** Total a receber = trabalho do mês + bônus. */
export const totalComBonus = (valorTrabalho, entries = []) =>
  (+valorTrabalho || 0) + somaBonus(entries);

export const somaPagamentos = (payments = []) =>
  (payments || []).reduce((s, p) => s + (+p.amount || 0), 0);

/** Junta lançamentos iguais (ex.: 5× Noite R$100 → um item R$500). */
export function agrupaBonus(entries = []) {
  const mapa = new Map();
  for (const e of entries || []) {
    const title = String(e.title || 'Bônus').replace(/\s+/g, ' ').trim() || 'Bônus';
    const k = title.toLocaleLowerCase('pt-BR');
    if (!mapa.has(k)) mapa.set(k, { title, count: 0, total: 0, unit: 0, items: [] });
    const g = mapa.get(k);
    g.count += 1;
    g.total += +e.amount || 0;
    g.items.push(e);
  }
  for (const g of mapa.values()) g.unit = g.count ? g.total / g.count : 0;
  return [...mapa.values()].sort((a, b) => b.total - a.total);
}

/** Fatias de pizza: horas por tarefa (ignora item só de valor, sem hora). */
export function fatiasHoras(porTarefa = []) {
  return (porTarefa || [])
    .filter((t) => (t.horas || 0) > 0.001)
    .map((t) => ({ nome: t.nome, valor: t.horas, cor: t.cor }));
}

/** Fatias de pizza: de onde veio o dinheiro (tarefas + grupos de bônus). */
export function fatiasSalario(porTarefa = [], grupos = []) {
  const fatias = [];
  for (const t of porTarefa || []) {
    if ((t.valor || 0) > 0.004) fatias.push({ nome: t.nome, valor: t.valor, cor: t.cor });
  }
  (grupos || []).forEach((g, i) => {
    if ((g.total || 0) > 0.004) {
      fatias.push({ nome: g.title, valor: g.total, cor: corDaSerie(fatias.length + i) });
    }
  });
  return fatias.sort((a, b) => b.valor - a.valor);
}

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
      const v = valorDoTrecho(trecho, agora);
      // em pay_mode=shift o valor vem do turno, não dos trechos
      const vConta = (turno.pay_mode === 'shift') ? 0 : v;
      horas += h; valor += vConta;

      const d = porDia.get(dia); d.horas += h; d.valor += vConta;
      const p = porPessoa.get(turno.user_id); p.horas += h; p.valor += vConta;

      const nome = trecho.task_name || 'Sem tarefa';
      if (!porTarefa.has(nome)) porTarefa.set(nome, { nome, horas: 0, valor: 0, cor: null });
      const t = porTarefa.get(nome); t.horas += h; t.valor += vConta;
      if (!t.cor && trecho.cor) t.cor = trecho.cor;
    }
    if (turno.pay_mode === 'shift' && turno.flat_amount != null) {
      const v = +turno.flat_amount || 0;
      valor += v;
      porDia.get(dia).valor += v;
      porPessoa.get(turno.user_id).valor += v;
      const nome = turno.period === 'manha' ? 'Turno Manhã'
        : turno.period === 'tarde' ? 'Turno Tarde'
        : turno.period === 'noite' ? 'Turno Noite' : 'Turno';
      if (!porTarefa.has(nome)) porTarefa.set(nome, { nome, horas: 0, valor: 0, cor: null });
      porTarefa.get(nome).valor += v;
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

function dataDoBonus(e) {
  if (e?.bonus_on) return deDiaChave(String(e.bonus_on).slice(0, 10));
  if (e?.created_at) return inicioDoDia(e.created_at);
  return null;
}

/** Último dia fechado: ontem. Evita comparar com turno ainda aberto hoje. */
export function diaLimiteComparacao(mesRef, agora = new Date()) {
  const ehCorrente = chaveMes(mesRef) === chaveMes(agora);
  if (!ehCorrente) return new Date(fimDoMes(mesRef)).getDate();
  const ontem = somaDias(inicioDoDia(agora), -1);
  if (chaveMes(ontem) !== chaveMes(mesRef)) return 0;
  return ontem.getDate();
}

function janelaMesAteDia(mesRef, diaLimite) {
  const ini = inicioDoMes(mesRef);
  const fimMes = fimDoMes(mesRef);
  if (diaLimite < 1) return { ini, ate: new Date(ini.getTime() - 1) };
  const ate = new Date(ini.getFullYear(), ini.getMonth(), diaLimite, 23, 59, 59, 999);
  return { ini, ate: ate > fimMes ? fimMes : ate };
}

function bonusNaJanela(entries, ini, ate) {
  return (entries || []).filter((e) => {
    const d = dataDoBonus(e);
    if (!d) return true;
    return d >= ini && d <= ate;
  });
}

/**
 * Compara o saldo TOTAL (trabalho + bônus) do mesmo trecho do mês:
 * dia 1 até ontem × dia 1 até o mesmo dia do mês anterior.
 */
export function comparaSaldo(turnos, bonusEntries, mesRef, agora = new Date()) {
  const diaLimite = diaLimiteComparacao(mesRef, agora);
  const mesAnt = somaMeses(mesRef, -1);
  const ym = chaveMes(mesRef);
  const ymAnt = chaveMes(mesAnt);
  const ja = janelaMesAteDia(mesRef, diaLimite);
  const jb = janelaMesAteDia(mesAnt, diaLimite);

  const noPeriodo = (de, ate) => (turnos || []).filter((t) => {
    const d = new Date(t.started_at);
    return d >= de && d <= ate;
  });
  const bonusDoMes = (lista, chave) => (lista || []).filter((e) => e.year_month === chave);

  const atualAg = agrega(noPeriodo(ja.ini, ja.ate), agora);
  const antAg = agrega(noPeriodo(jb.ini, jb.ate), agora);
  const bonusAtual = bonusNaJanela(bonusDoMes(bonusEntries, ym), ja.ini, ja.ate);
  const bonusAnt = bonusNaJanela(bonusDoMes(bonusEntries, ymAnt), jb.ini, jb.ate);

  const atual = {
    trabalho: atualAg.valor,
    bonus: somaBonus(bonusAtual),
    total: atualAg.valor + somaBonus(bonusAtual),
    horas: atualAg.horas,
    dias: [...atualAg.porDia.values()].filter((d) => d.horas > 0).length,
  };
  const anterior = {
    trabalho: antAg.valor,
    bonus: somaBonus(bonusAnt),
    total: antAg.valor + somaBonus(bonusAnt),
    horas: antAg.horas,
    dias: [...antAg.porDia.values()].filter((d) => d.horas > 0).length,
  };

  const varia = (novo, velho) => {
    if (!velho) return { abs: novo, pct: null };
    return { abs: novo - velho, pct: ((novo - velho) / velho) * 100 };
  };

  return {
    diaLimite,
    parcial: chaveMes(mesRef) === chaveMes(agora) && diaLimite > 0,
    atual,
    anterior,
    variacao: {
      total: varia(atual.total, anterior.total),
      horas: varia(atual.horas, anterior.horas),
      dias: varia(atual.dias, anterior.dias),
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

/** Os últimos N meses de ganhos (trabalho + bônus), terminando no mês de referência. */
export function serieDeMeses(turnos, mesRef, quantos = 6, agora = new Date(), bonusEntries = []) {
  const meses = [];
  const nomesBonus = [];
  for (let i = quantos - 1; i >= 0; i--) {
    const m = somaMeses(mesRef, -i);
    const ini = inicioDoMes(m), fim = fimDoMes(m);
    const ym = chaveMes(m);
    const a = agrega(turnos.filter((t) => {
      const d = new Date(t.started_at);
      return d >= ini && d <= fim;
    }), agora);
    const grupos = agrupaBonus((bonusEntries || []).filter((e) => e.year_month === ym));
    grupos.forEach((g) => { if (!nomesBonus.includes(g.title)) nomesBonus.push(g.title); });
    meses.push({ m, a, grupos, atual: i === 0 });
  }
  const corDe = (nome, i) => (nome === 'Trabalho' ? PALETA[0] : corDaSerie(i + 1));
  const idxBonus = new Map(nomesBonus.map((n, i) => [n, i]));

  return meses.map(({ m, a, grupos, atual }) => {
    const partes = [
      { nome: 'Trabalho', valor: a.valor, cor: PALETA[0] },
      ...grupos.map((g) => ({
        nome: g.title, valor: g.total, cor: corDe(g.title, idxBonus.get(g.title) || 0),
      })),
    ].filter((p) => p.valor > 0.004);
    const total = partes.reduce((s, p) => s + p.valor, 0);
    return {
      rotulo: nomeMes(m).slice(0, 3),
      rotuloLongo: mesAno(m),
      valor: total,
      total,
      horas: a.horas,
      atual,
      partes,
    };
  });
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
