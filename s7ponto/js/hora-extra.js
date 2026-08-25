/* ==========================================================================
   S7 PONTO — hora extra.

   Não existe jornada cadastrada: cada dia “escolhe” a jornada mais
   provável (5h, 6h, 7h…) a partir das horas reais.

   Exemplos:
     7:10 e 6:57 → jornada de 7h
     5:40 e 6:20 → jornada de 6h
     7:28        → jornada de 7h + 28 min extra (não “vira” 8h)

   O banco do mês soma os dias: saiu mais cedo num dia e ficou noutro
   se compensam. Só conta extra se o saldo do período passou do previsto.
   ========================================================================== */
import { diaChave, horas, esc, plural, chaveMes } from './util.js';
import { horasDoTurno } from './metricas.js';

/** Abaixo disso o dia não parece uma jornada (saiu rápido, esqueceu, etc.). */
export const MINIMO_JORNADA = 2.5;

/** Janela em minutos para “é esta jornada” (22 min ≈ 7:10 ainda é 7h). */
export const JANELA_MIN = 22;

/** Alerta a partir de 15 min líquidos no período (já compensado). */
export const LIMIAR_EXTRA = 15 / 60;

export const TEXTO_AVISO_GESTOR =
  'Atenção, você está passando da sua hora. Teve autorização? Estamos enviando um aviso para seu gestor.';

/**
 * Infere a jornada prevista de um dia a partir das horas trabalhadas.
 * Perto de uma hora redonda (±22 min) assume aquela jornada; no meio
 * do caminho (ex.: 7:28) fica na hora de baixo e o resto é extra.
 */
export function jornadaDoDia(h) {
  const horasDia = Math.max(0, Number(h) || 0);
  if (horasDia < MINIMO_JORNADA) {
    return { horas: horasDia, previsto: 0, extra: 0, ignorado: true };
  }
  const janela = JANELA_MIN / 60;
  const piso = Math.floor(horasDia + 1e-9);
  const resto = horasDia - piso;
  let previsto = piso;
  if (resto <= janela + 1e-9) previsto = piso;
  else if (resto >= 1 - janela - 1e-9) previsto = piso + 1;
  else previsto = piso;
  if (previsto < 1) previsto = 0;
  return {
    horas: horasDia,
    previsto,
    extra: horasDia - previsto,
    ignorado: previsto === 0,
  };
}

/** Soma as horas de cada dia (vários turnos no mesmo dia entram juntos). */
export function horasPorDia(turnos, agora = new Date()) {
  const mapa = new Map();
  for (const t of turnos || []) {
    const k = diaChave(t.started_at);
    mapa.set(k, (mapa.get(k) || 0) + horasDoTurno(t, agora));
  }
  return [...mapa.entries()]
    .map(([dia, h]) => ({ dia, ...jornadaDoDia(h) }))
    .sort((a, b) => a.dia.localeCompare(b.dia));
}

/**
 * Banco de horas extra de um conjunto de turnos (em geral, o mês).
 * extra pode ser negativo se no total ainda falta hora — aí não alerta.
 */
export function extraDoPeriodo(turnos, agora = new Date()) {
  const dias = horasPorDia(turnos, agora);
  let trabalhado = 0;
  let previsto = 0;
  let diasContados = 0;
  for (const d of dias) {
    trabalhado += d.horas;
    if (!d.ignorado) {
      previsto += d.previsto;
      diasContados += 1;
    }
  }
  const extra = trabalhado - previsto;
  return {
    trabalhado,
    previsto,
    extra,
    dias,
    diasContados,
    temExtra: extra >= LIMIAR_EXTRA - 1e-9,
  };
}

/** Filtra turnos de um mês (AAAA-MM). */
export function turnosDoMes(turnos, yearMonth, agora = new Date()) {
  const ym = yearMonth || chaveMes(agora);
  return (turnos || []).filter((t) => chaveMes(t.started_at) === ym);
}

export function extraPorPessoa(turnos, pessoas = [], agora = new Date()) {
  const porUser = new Map();
  for (const t of turnos || []) {
    if (!porUser.has(t.user_id)) porUser.set(t.user_id, []);
    porUser.get(t.user_id).push(t);
  }
  const ids = pessoas.length ? pessoas.map((p) => p.id) : [...porUser.keys()];
  const porId = new Map((pessoas || []).map((p) => [p.id, p]));
  const out = [];
  for (const id of ids) {
    const ts = porUser.get(id) || [];
    if (!ts.length) continue;
    const banco = extraDoPeriodo(ts, agora);
    const p = porId.get(id);
    out.push({
      user_id: id,
      nome: p?.full_name || 'Alguém',
      username: p?.username || '',
      ...banco,
    });
  }
  return out.sort((a, b) => b.extra - a.extra);
}

export function htmlRecadoExtraPessoa(banco, { nomeMes = '', compacto = false } = {}) {
  if (!banco?.temExtra) return '';
  const qtd = horas(banco.extra);
  if (compacto) {
    return `<span class="ficha ficha-baixa" data-extra>+${esc(qtd)} extra</span>`;
  }
  return `
    <div class="recado ruim" style="margin-top:14px">
      <span class="recado-emoji">⏱️</span>
      <span><strong>${esc(qtd)} de hora extra</strong>${nomeMes ? ` em ${esc(nomeMes)}` : ''}.
            Já entra a compensação: um dia mais curto anula outro mais longo.
            Previsto ${esc(horas(banco.previsto))} · feito ${esc(horas(banco.trabalhado))}.</span>
    </div>`;
}

export function htmlAlertaExtra(lista, { tituloMes = '', avisos = 0 } = {}) {
  const com = (lista || []).filter((x) => x.temExtra);
  if (!com.length) return '';
  const total = com.reduce((s, x) => s + x.extra, 0);
  const quem = com.map((x) => `${esc(x.nome)} <strong>${esc(horas(x.extra))}</strong>`).join(' · ');
  const avisoTxt = avisos > 0
    ? ` ${esc(plural(avisos, 'aviso enviado', 'avisos enviados'))} do ponto para o gestor.`
    : '';
  return `
    <div class="recado ruim alerta-hora-extra" style="margin-bottom:16px">
      <span class="recado-emoji">⏱️</span>
      <span>
        <strong>${esc(plural(com.length, 'pessoa com hora extra', 'pessoas com hora extra'))}</strong>
        ${tituloMes ? `em ${esc(tituloMes)}` : ''}:
        <strong>${esc(horas(total))}</strong> no total
        (já compensando quem saiu mais cedo noutro dia).
        <span class="alerta-hora-extra-lista">${quem}.</span>
        ${avisoTxt}
      </span>
    </div>`;
}

export function htmlAlertaLiberdade({ horasExtra = 0 } = {}) {
  return `
    <div class="recado ruim alerta-liberdade" id="alerta-extra" hidden>
      <span class="recado-emoji">⚠️</span>
      <span>
        <strong>Atenção, você está passando da sua hora.</strong>
        Teve autorização? Estamos enviando um aviso para seu gestor.
        ${horasExtra > 0
          ? `<span class="alerta-liberdade-qtd"> No mês, depois de compensar os dias, já são <strong id="alerta-extra-qtd">${esc(horas(horasExtra))}</strong> a mais.</span>`
          : '<span class="alerta-liberdade-qtd"> No mês, depois de compensar os dias, já são <strong id="alerta-extra-qtd">—</strong> a mais.</span>'}
      </span>
    </div>`;
}
