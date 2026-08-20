import type { Municipio } from "./types";
import { ROTULO_FATOR } from "./score";

const COLUNAS: { chave: string; rotulo: string; valor: (m: Municipio) => unknown }[] = [
  { chave: "posicao", rotulo: "#", valor: (m) => m.posicao },
  { chave: "codigo_ibge", rotulo: "Código IBGE", valor: (m) => m.codigo_ibge },
  { chave: "nome", rotulo: "Município", valor: (m) => m.nome },
  { chave: "uf", rotulo: "UF", valor: (m) => m.uf },
  // Dinheiro primeiro: e a coluna que o comercial abre a planilha para ver.
  { chave: "potencial_pct", rotulo: "Potencial %", valor: (m) => m.potencial_pct },
  { chave: "faturamento_estimado", rotulo: "Faturamento estimado", valor: (m) => m.faturamento_estimado },
  { chave: "lucro_estimado", rotulo: "Lucro estimado", valor: (m) => m.lucro_estimado },
  { chave: "retorno_sobre_custo", rotulo: "Retorno sobre custo", valor: (m) => m.retorno_sobre_custo },
  { chave: "consultas_esperadas", rotulo: "Consultas esperadas", valor: (m) => m.consultas_esperadas },
  { chave: "vendas_esperadas", rotulo: "Pares vendidos", valor: (m) => m.vendas_esperadas },
  { chave: "ocupacao_agenda", rotulo: "Ocupação da agenda", valor: (m) => m.ocupacao_agenda },
  { chave: "conversao", rotulo: "Conversão", valor: (m) => m.conversao },
  { chave: "ticket_estimado", rotulo: "Ticket estimado", valor: (m) => m.ticket_estimado },
  { chave: "custo_evento", rotulo: "Custo do evento", valor: (m) => m.custo_evento },
  { chave: "ponto_equilibrio_vendas", rotulo: "Equilíbrio (pares)", valor: (m) => m.ponto_equilibrio_vendas },
  { chave: "dias_sugeridos", rotulo: "Dias sugeridos", valor: (m) => m.dias_sugeridos },
  { chave: "projecao_confianca", rotulo: "Confiança da projeção", valor: (m) => m.projecao_confianca },
  { chave: "score_total", rotulo: "Score demanda", valor: (m) => m.score_total },
  { chave: "confianca", rotulo: "Confiança", valor: (m) => m.confianca },
  { chave: "populacao_total", rotulo: "População", valor: (m) => m.populacao_total },
  { chave: "populacao_40mais", rotulo: "População 40+", valor: (m) => m.populacao_40mais },
  { chave: "qtd_oftalmologistas", rotulo: "Oftalmologistas", valor: (m) => m.qtd_oftalmologistas },
  { chave: "oftalmo_equivalente", rotulo: "Oftalmo equivalente 40h", valor: (m) => m.oftalmo_equivalente },
  { chave: "distancia_km", rotulo: "Distância ao polo (km)", valor: (m) => m.distancia_km },
  { chave: "tempo_minutos", rotulo: "Tempo ao polo (min)", valor: (m) => m.tempo_minutos },
  { chave: "polo_nome", rotulo: "Polo", valor: (m) => m.polo_nome },
  { chave: "qtd_oticas", rotulo: "Óticas", valor: (m) => m.qtd_oticas },
  { chave: "oticas_nota_media", rotulo: "Nota média das óticas", valor: (m) => m.oticas_nota_media },
  { chave: "oticas_avaliacoes", rotulo: "Avaliações das óticas", valor: (m) => m.oticas_avaliacoes },
  { chave: "renda_mediana", rotulo: "Renda", valor: (m) => m.renda_mediana },
  { chave: "circuito", rotulo: "Circuito", valor: (m) => m.circuito },
  { chave: "microrregiao", rotulo: "Microrregião", valor: (m) => m.microrregiao },
];

function celula(v: unknown): string {
  if (v === null || v === undefined) return "";
  const texto = typeof v === "number" ? String(v).replace(".", ",") : String(v);
  return /[";\n]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
}

/**
 * CSV com separador ";" e BOM: abre direto no Excel em pt-BR sem passo de importação.
 * O XLSX de verdade sai do pipeline (`out/ranking-v1.xlsx`) — no navegador não vale
 * carregar uma biblioteca de planilha só para isso.
 */
export function baixarCSV(municipios: Municipio[], nomeArquivo = "mapa-optico-ranking.csv"): void {
  const cabecalho = COLUNAS.map((c) => c.rotulo);
  const fatores = Object.keys(ROTULO_FATOR);
  fatores.forEach((f) => cabecalho.push(`Contribuição: ${ROTULO_FATOR[f]}`));

  const linhas = municipios.map((m) => {
    const base = COLUNAS.map((c) => celula(c.valor(m)));
    fatores.forEach((f) => base.push(celula(m.componentes?.[f]?.contribuicao ?? null)));
    return base.join(";");
  });

  const conteudo = "﻿" + [cabecalho.join(";"), ...linhas].join("\r\n");
  const blob = new Blob([conteudo], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nomeArquivo;
  a.click();
  URL.revokeObjectURL(url);
}
