const nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Traço em vez de zero: dado ausente nunca vira número. */
export const VAZIO = "—";

export const num = (v: number | null | undefined, casas: 0 | 1 | 2 = 0): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return VAZIO;
  return (casas === 0 ? nf0 : casas === 1 ? nf1 : nf2).format(v);
};

export const moeda = (v: number | null | undefined): string =>
  v === null || v === undefined || Number.isNaN(v) ? VAZIO : `R$ ${nf0.format(v)}`;

/** Dinheiro compacto para caber em coluna de tabela: R$ 27 mil, R$ 1,2 mi. */
export const moedaCurta = (v: number | null | undefined): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return VAZIO;
  const sinal = v < 0 ? "-" : "";
  const a = Math.abs(v);
  if (a >= 1_000_000) return `${sinal}R$ ${nf1.format(a / 1_000_000)} mi`;
  if (a >= 1_000) return `${sinal}R$ ${nf0.format(a / 1_000)} mil`;
  return `${sinal}R$ ${nf0.format(a)}`;
};

/** Percentual a partir de um valor ja em 0-100 (o pct() espera 0-1). */
export const pontos = (v: number | null | undefined, casas: 0 | 1 = 0): string =>
  v === null || v === undefined || Number.isNaN(v) ? VAZIO : `${(casas === 0 ? nf0 : nf1).format(v)}%`;

export const pct = (v: number | null | undefined): string =>
  v === null || v === undefined || Number.isNaN(v) ? VAZIO : `${nf0.format(v * 100)}%`;

export const km = (v: number | null | undefined): string =>
  v === null || v === undefined || Number.isNaN(v) ? VAZIO : `${nf1.format(v)} km`;

export const dataHora = (iso: string): string => {
  try {
    return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
};
