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
