/**
 * Modos de ordenação do ranking.
 *
 * "Melhor cidade" muda de significado conforme a pergunta, e o produto precisa
 * assumir isso em vez de eleger uma resposta única: a cidade que mais fatura
 * raramente é a que dá mais retorno sobre a mídia, e nenhuma das duas é
 * necessariamente a que cabe na agenda do médico.
 */
import type { Municipio } from "./types";

export type ModoOrdenacao =
  | "lucro_estimado"
  | "potencial_pct"
  | "faturamento_estimado"
  | "retorno_sobre_custo"
  | "score_total";

export interface Modo {
  chave: ModoOrdenacao;
  rotulo: string;
  /** O que essa ordenação responde, em uma frase. Vai no title e na ajuda. */
  responde: string;
  quando: string;
}

export const MODOS: Modo[] = [
  {
    chave: "lucro_estimado",
    rotulo: "Lucro estimado",
    responde: "Onde sobra mais depois de todos os custos",
    quando: "O padrão. É o que decide se vale ir.",
  },
  {
    chave: "potencial_pct",
    rotulo: "Potencial %",
    responde: "Quanto do máximo teórico a cidade entrega",
    quando: "Comparar regiões sem olhar valor absoluto.",
  },
  {
    chave: "faturamento_estimado",
    rotulo: "Faturamento",
    responde: "Onde entra mais dinheiro no caixa",
    quando: "Quando a meta é volume, não margem.",
  },
  {
    chave: "retorno_sobre_custo",
    rotulo: "Retorno",
    responde: "Quanto cada real investido devolve",
    quando: "Quando o caixa está curto.",
  },
  {
    chave: "score_total",
    rotulo: "Demanda reprimida",
    responde: "Onde o acesso ao oftalmologista é pior",
    quando: "Leitura de mercado, independente de preço.",
  },
];

export const MODO_PADRAO: ModoOrdenacao = "lucro_estimado";

export function modoPorChave(chave: ModoOrdenacao): Modo {
  return MODOS.find((m) => m.chave === chave) ?? MODOS[0];
}

/** Ordena decrescente pelo modo, com nulos sempre no fim e desempate por score. */
export function ordenarPor(municipios: Municipio[], modo: ModoOrdenacao): Municipio[] {
  const valor = (m: Municipio): number | null => {
    const v = m[modo];
    return typeof v === "number" && Number.isFinite(v) ? v : null;
  };
  return [...municipios].sort((a, b) => {
    const va = valor(a);
    const vb = valor(b);
    if (va === null && vb === null) return (b.score_total ?? 0) - (a.score_total ?? 0);
    if (va === null) return 1;
    if (vb === null) return -1;
    if (vb !== va) return vb - va;
    return (b.score_total ?? 0) - (a.score_total ?? 0);
  });
}

/** Reatribui posicao 1..n na ordem atual — a coluna "#" precisa acompanhar o modo. */
export function reposicionar(municipios: Municipio[]): Municipio[] {
  return municipios.map((m, i) => ({ ...m, posicao: i + 1 }));
}
