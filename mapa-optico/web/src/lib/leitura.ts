/**
 * A cidade explicada em português, a partir dos próprios números dela.
 *
 * POR QUE ISTO EXISTE: a tabela mostra doze colunas e um percentual, e quem
 * olha não sabe o que está pesando. "Potencial 4,9%" não diz nada; "Garopaba
 * fica a 30 km e tem 12 oftalmologistas — a maioria já se atende lá" diz tudo.
 *
 * Nada aqui é calculado de novo. Cada frase é uma leitura de um número que a
 * projeção já produziu, para que a explicação nunca possa divergir da conta.
 */
import type { Municipio } from "./types";
import { moeda, num as fmtNum } from "./format";

export type Veredito = "vale" | "talvez" | "nao" | "sem-dado";

export interface Leitura {
  veredito: Veredito;
  /** Uma linha, em caixa alta na tela. */
  titulo: string;
  /** As razões, na ordem em que pesam. A primeira é sempre a decisiva. */
  motivos: string[];
}

const ROTULO: Record<Veredito, string> = {
  vale: "Vale ir",
  talvez: "Fica no limite",
  nao: "Não compensa",
  "sem-dado": "Sem dado suficiente",
};

/** Distância a partir da qual a cidade deixa de orbitar o polo vizinho. */
const KM_ORBITA = 35;

export function leituraDaCidade(m: Municipio): Leitura {
  const lucro = m.lucro_estimado;
  const motivos: string[] = [];

  if (lucro === null || m.populacao_40mais === null) {
    return {
      veredito: "sem-dado",
      titulo: ROTULO["sem-dado"],
      motivos: ["Falta dado de população, CNES ou distância para projetar esta cidade."],
    };
  }

  // ---------------------------------------------------------------- tamanho
  motivos.push(
    `${fmtNum(m.populacao_total)} moradores, ${fmtNum(m.populacao_40mais)} com mais de 40 anos ` +
      "— é este segundo número que compra óculos de leitura.",
  );

  // ------------------------------------------------- o fator que mais decide
  const km = m.distancia_km;
  const polo = m.polo_nome;
  if (km !== null && polo) {
    if (km < KM_ORBITA) {
      motivos.push(
        `${polo} fica a apenas ${Math.round(km)} km. Quem precisa de óculos já resolve lá — ` +
          "é o que mais derruba esta cidade.",
      );
    } else {
      motivos.push(
        `O atendimento mais próximo é ${polo}, a ${Math.round(km)} km. ` +
          "Longe o suficiente para muita gente adiar — e é aí que está a procura represada.",
      );
    }
  }

  // ------------------------------------------------------------- concorrência
  if (m.qtd_oftalmologistas !== null) {
    motivos.push(
      m.qtd_oftalmologistas === 0
        ? "Nenhum oftalmologista na cidade."
        : `${m.qtd_oftalmologistas} oftalmologista${m.qtd_oftalmologistas > 1 ? "s" : ""} ` +
          "na cidade — parte da procura já é atendida aqui.",
    );
  }

  // ------------------------------------------------------------------ agenda
  const consultas = m.consultas_esperadas;
  const ocupacao = m.ocupacao_agenda;
  if (consultas !== null && ocupacao !== null) {
    if (ocupacao >= 0.99) {
      const sobra = m.demanda_nao_capturada ?? 0;
      motivos.push(
        `A agenda enche: ${fmtNum(consultas)} consultas, e ainda sobra procura` +
          (sobra > 0 ? ` para mais ${fmtNum(sobra)}` : "") +
          `. Vale considerar ${m.dias_sugeridos ?? "mais"} dias, ou levar outro médico.`,
      );
    } else {
      motivos.push(
        `A agenda não enche: ${fmtNum(consultas)} consultas para ` +
          `${Math.round(ocupacao * 100)}% da capacidade. Aqui o que falta é gente, não dia.`,
      );
    }
  }

  // ----------------------------------------------------------------- a conta
  const equilibrio = m.ponto_equilibrio_vendas;
  const vendas = m.vendas_esperadas;
  if (lucro > 0) {
    motivos.push(
      `Sobra ${moeda(lucro)} depois de todos os custos` +
        (equilibrio !== null && vendas !== null
          ? ` — precisa vender ${fmtNum(equilibrio)} pares para empatar, e a projeção é de ${fmtNum(vendas)}.`
          : "."),
    );
  } else {
    motivos.push(
      `A conta fecha em ${moeda(lucro)}` +
        (equilibrio !== null && vendas !== null
          ? `: precisaria de ${fmtNum(equilibrio)} pares para empatar e a projeção é de só ${fmtNum(vendas)}.`
          : "."),
    );
  }

  return { veredito: vereditoDe(m), titulo: ROTULO[vereditoDe(m)], motivos };
}

/**
 * O veredito olha o lucro contra o próprio custo do evento, não contra um
 * valor fixo: R$ 2 mil de sobra é ótimo num evento de R$ 8 mil e irrelevante
 * num de R$ 40 mil.
 */
export function vereditoDe(m: Municipio): Veredito {
  const lucro = m.lucro_estimado;
  if (lucro === null) return "sem-dado";
  const custo = m.custo_evento;
  if (lucro <= 0) return "nao";
  if (custo === null || custo <= 0) return "talvez";
  return lucro / custo >= 0.5 ? "vale" : "talvez";
}

export function rotuloDoVeredito(v: Veredito): string {
  return ROTULO[v];
}
