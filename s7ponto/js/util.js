/* ==========================================================================
   S7 PONTO — utilidades: dinheiro, horas, datas, texto.
   ========================================================================== */
import { CONFIG } from './config.js';

const L = CONFIG.LOCALE;

/* ---------- dinheiro e números ------------------------------------------ */

const moneyFmt = new Intl.NumberFormat(L, {
  style: 'currency', currency: CONFIG.CURRENCY,
  minimumFractionDigits: 2, maximumFractionDigits: 2,
});
export const money = (n) => moneyFmt.format(Number.isFinite(+n) ? +n : 0);

/** "R$ 1.842" — sem centavos, para números grandes de destaque. */
export const moneyShort = (n) =>
  new Intl.NumberFormat(L, { style: 'currency', currency: CONFIG.CURRENCY,
    maximumFractionDigits: 0 }).format(Number.isFinite(+n) ? +n : 0);

export const num = (n, casas = 1) =>
  new Intl.NumberFormat(L, { minimumFractionDigits: casas, maximumFractionDigits: casas })
    .format(Number.isFinite(+n) ? +n : 0);

export const pct = (n) =>
  `${n > 0 ? '+' : ''}${new Intl.NumberFormat(L, { maximumFractionDigits: 1 }).format(n)}%`;

/* ---------- horas -------------------------------------------------------- */

/** 7.5 -> "7h 30min" · 0.4 -> "24min" · 0 -> "0min" */
export function horas(h) {
  const total = Math.max(0, Math.round((Number(h) || 0) * 60));
  const hh = Math.floor(total / 60), mm = total % 60;
  if (hh && mm) return `${hh}h ${String(mm).padStart(2, '0')}min`;
  if (hh) return `${hh}h`;
  return `${mm}min`;
}

/** 7.5 -> "7:30" — compacto, para tabelas e eixos. */
export function horasCurto(h) {
  const total = Math.max(0, Math.round((Number(h) || 0) * 60));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

/** milissegundos -> "07:32:11" para o cronômetro ao vivo. */
export function cronometro(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60]
    .map((v) => String(v).padStart(2, '0')).join(':');
}

export const horasEntre = (inicio, fim) =>
  Math.max(0, (new Date(fim).getTime() - new Date(inicio).getTime()) / 3600000);

/* ---------- datas -------------------------------------------------------- */

export const hoje = () => new Date();

/** Chave local 'AAAA-MM-DD' (nunca usar toISOString: ele joga pro UTC). */
export function diaChave(d) {
  const x = new Date(d);
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;
}
export const mesChave = (d) => diaChave(d).slice(0, 7);

export const inicioDoDia = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; };
export const fimDoDia     = (d) => { const x = new Date(d); x.setHours(23, 59, 59, 999); return x; };
export const inicioDoMes  = (d) => { const x = new Date(d); x.setDate(1); x.setHours(0, 0, 0, 0); return x; };
export const fimDoMes     = (d) => { const x = new Date(d); x.setMonth(x.getMonth() + 1, 0); x.setHours(23, 59, 59, 999); return x; };
export const somaMeses    = (d, n) => { const x = inicioDoMes(d); x.setMonth(x.getMonth() + n); return x; };
export const somaDias     = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };

/** Segunda-feira da semana da data (semana brasileira: seg → dom). */
export function inicioDaSemana(d) {
  const x = inicioDoDia(d);
  const diff = (x.getDay() + 6) % 7;   // 0 = segunda
  x.setDate(x.getDate() - diff);
  return x;
}

const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
  'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
export const nomeMes      = (d) => MESES[new Date(d).getMonth()];
export const mesAno       = (d) => `${nomeMes(d)} de ${new Date(d).getFullYear()}`;
export const mesAnoCurto  = (d) => `${nomeMes(d).slice(0, 3)}/${String(new Date(d).getFullYear()).slice(2)}`;
/** Chave AAAA-MM a partir de uma data (ou string já no formato). */
export const chaveMes = (d) => {
  if (typeof d === 'string' && /^\d{4}-\d{2}$/.test(d)) return d;
  const x = new Date(d);
  const m = String(x.getMonth() + 1).padStart(2, '0');
  return `${x.getFullYear()}-${m}`;
};

const DIAS = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado'];
export const nomeDia    = (d) => DIAS[new Date(d).getDay()];
export const letraDia   = (d) => ['D', 'S', 'T', 'Q', 'Q', 'S', 'S'][new Date(d).getDay()];

/** "seg, 12 de agosto" */
export const dataLonga = (d) =>
  `${nomeDia(d).slice(0, 3)}, ${new Date(d).getDate()} de ${nomeMes(d)}`;
/** "12/08" */
export const dataCurta = (d) => {
  const x = new Date(d);
  return `${String(x.getDate()).padStart(2, '0')}/${String(x.getMonth() + 1).padStart(2, '0')}`;
};
/** "12/08/2026" */
export const dataBR = (d) => `${dataCurta(d)}/${new Date(d).getFullYear()}`;
/** "08:15" */
export const hora = (d) => {
  const x = new Date(d);
  return `${String(x.getHours()).padStart(2, '0')}:${String(x.getMinutes()).padStart(2, '0')}`;
};

/** Valor para <input type="datetime-local">, no fuso do navegador. */
export const paraInputLocal = (d) => `${diaChave(d)}T${hora(d)}`;
export const deInputLocal   = (s) => (s ? new Date(s) : null);

export function saudacao(d = new Date()) {
  const h = new Date(d).getHours();
  if (h < 5)  return 'Boa madrugada';
  if (h < 12) return 'Bom dia';
  if (h < 18) return 'Boa tarde';
  return 'Boa noite';
}

/* ---------- leitura solta de planilha ------------------------------------ */

/** Aceita 12/08/2026, 12-08-26, 2026-08-12 e o número serial do Excel. */
export function leData(v) {
  if (v == null || v === '') return null;
  if (v instanceof Date && !isNaN(v)) return v;

  const s = String(v).trim();

  // serial do Excel (dias desde 30/12/1899)
  if (/^\d{5}(\.\d+)?$/.test(s)) {
    const d = new Date(Date.UTC(1899, 11, 30) + Math.round(parseFloat(s)) * 86400000);
    return new Date(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  }
  let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return new Date(+m[1], +m[2] - 1, +m[3]);

  m = s.match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})/);
  if (m) {
    let ano = +m[3];
    if (ano < 100) ano += ano < 70 ? 2000 : 1900;
    return new Date(ano, +m[2] - 1, +m[1]);       // dia/mês/ano — padrão BR
  }
  const d = new Date(s);
  return isNaN(d) ? null : d;
}

/** Aceita "8:30", "08h30", "8", "1830" e a fração de dia do Excel. */
export function leHora(v) {
  if (v == null || v === '') return null;
  if (v instanceof Date && !isNaN(v)) return { h: v.getHours(), m: v.getMinutes() };

  const s = String(v).trim();

  if (/^0?\.\d+$/.test(s)) {                       // fração de dia do Excel
    const mins = Math.round(parseFloat(s) * 1440);
    return { h: Math.floor(mins / 60) % 24, m: mins % 60 };
  }
  let m = s.match(/^(\d{1,2})\s*[:hH.]\s*(\d{1,2})/);
  if (m) return { h: +m[1], m: +m[2] };
  if (/^\d{3,4}$/.test(s)) return { h: +s.slice(0, s.length - 2), m: +s.slice(-2) };
  if (/^\d{1,2}$/.test(s)) return { h: +s, m: 0 };
  return null;
}

/** Junta data + hora numa Date local. */
export function juntaDataHora(data, horaObj) {
  if (!data) return null;
  const d = new Date(data);
  if (horaObj) d.setHours(horaObj.h, horaObj.m, 0, 0);
  return d;
}

/** "R$ 1.234,56", "1234.56" e "1.234,56" viram 1234.56. */
export function leNumero(v) {
  if (v == null || v === '') return null;
  if (typeof v === 'number') return v;
  let s = String(v).replace(/[^\d,.\-]/g, '').trim();
  if (!s) return null;
  if (s.includes(',') && s.includes('.')) s = s.replace(/\./g, '').replace(',', '.');
  else if (s.includes(',')) s = s.replace(',', '.');
  const n = parseFloat(s);
  return isNaN(n) ? null : n;
}

/* ---------- texto -------------------------------------------------------- */

/** Só a primeira letra em maiúscula — "agosto de 2026" -> "Agosto de 2026". */
export const maiuscula = (s) => {
  const t = String(s ?? '');
  return t.charAt(0).toUpperCase() + t.slice(1);
};

export const esc = (s) => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

/** Sem acento, minúsculo — para comparar nomes de coluna e de tarefa. */
export const chave = (s) => String(s ?? '').normalize('NFD')
  .replace(/[̀-ͯ]/g, '').toLowerCase().trim();

export const iniciais = (nome) => String(nome || '?').trim().split(/\s+/)
  .slice(0, 2).map((p) => p[0] || '').join('').toUpperCase();

/** Senha inicial padrão: usuário + 321*  (ex.: david321*). */
export const senhaPadrao = (username) =>
  `${String(username || '').trim().toLowerCase()}321*`;

export const uid = () => (crypto.randomUUID
  ? crypto.randomUUID()
  : 'id-' + Math.random().toString(36).slice(2) + Date.now().toString(36));

export const plural = (n, um, muitos) => `${n} ${n === 1 ? um : muitos}`;

/** Baixa um texto como arquivo (usado no exportar CSV / backup). */
export function baixaArquivo(nome, conteudo, tipo = 'text/csv;charset=utf-8') {
  const url = URL.createObjectURL(new Blob(['﻿' + conteudo], { type: tipo }));
  const a = Object.assign(document.createElement('a'), { href: url, download: nome });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const csvLinha = (campos) => campos
  .map((c) => { const s = String(c ?? ''); return /[";\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; })
  .join(';');

/* ---------- períodos de trabalho (manhã / tarde / noite) ----------------- */

export const PERIODOS = [
  { id: 'manha', nome: 'Manhã',  dica: 'até 11:59' },
  { id: 'tarde', nome: 'Tarde',  dica: '12:00 às 17:59' },
  { id: 'noite', nome: 'Noite',  dica: 'a partir das 18:00' },
];

/** Horários padrão ao lançar um período na mão (o valor em si é fixo). */
export const HORARIOS_PERIODO = {
  manha: { ini: '08:00', fim: '12:00' },
  tarde: { ini: '13:00', fim: '18:00' },
  noite: { ini: '18:00', fim: '22:00' },
};

export const nomePeriodo = (id) =>
  PERIODOS.find((p) => p.id === id)?.nome || id || '—';

/** Por hora cronometra; por tarefa ou por turno o valor é fixo, sem início/fim. */
export const pagamentoFixo = (modo) => modo === 'task' || modo === 'shift';

/** `2026-08-25` → Date local, sem fuso atrapalhando. */
export const deDiaChave = (k) => {
  const [y, m, d] = String(k).split('-').map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
};

/** Junta um dia com `08:00` no fuso do aparelho. */
export function juntaDiaHora(dia, hhmm) {
  const d = new Date(dia);
  const [h, min] = String(hhmm || '00:00').split(':').map((x) => parseInt(x, 10) || 0);
  d.setHours(h, min, 0, 0);
  return d;
}

/** Sugere o período a partir do horário atual (ou de uma data). */
export function sugerePeriodo(quando = new Date()) {
  const h = new Date(quando).getHours() + new Date(quando).getMinutes() / 60;
  if (h < 12) return 'manha';
  if (h < 18) return 'tarde';
  return 'noite';
}