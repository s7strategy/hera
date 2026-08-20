/**
 * Porte da projecao financeira do pipeline (score/projecao.py) para o navegador.
 *
 * Mesma razao do porte do score: a tela de parametros do negocio precisa
 * recalcular faturamento e lucro enquanto o usuario arrasta os controles.
 * `conferirProjecaoComPipeline()` recalcula com os parametros originais do
 * snapshot e compara com o que o Python gravou — divergiu, a interface avisa.
 *
 * Qualquer mudanca em score/projecao.py tem que ser espelhada aqui.
 */
import type { Municipio, Negocio, Projecao } from "./types";

const ehNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const num = (v: unknown): number | null => (ehNum(v) ? v : null);
const limitar = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));

/** Penalidade de confianca por entrada imputada — igual ao PENALIDADE do Python. */
export const PENALIDADE: Record<string, number> = {
  distancia_km: 0.3,
  qtd_oticas: 0.3,
  reputacao_oticas: 0.1,
  renda_mediana: 0.1,
};

export const ROTULO_IMPUTADO: Record<string, string> = {
  distancia_km: "distância até o polo",
  qtd_oticas: "óticas concorrentes",
  reputacao_oticas: "notas e avaliações das óticas",
  renda_mediana: "renda da cidade",
};

function mediana(valores: (number | null)[]): number | null {
  const v = valores.filter(ehNum).sort((a, b) => a - b);
  if (!v.length) return null;
  const meio = Math.floor(v.length / 2);
  return v.length % 2 ? v[meio] : (v[meio - 1] + v[meio]) / 2;
}

/** Fracao do ticket que vai para o fornecedor. Vende 1800 e paga 600 → 1/3. */
export function cmvFracao(n: Negocio): number {
  const ticket = num(n.venda?.ticket_medio) ?? 0;
  const custo = num(n.venda?.custo_produto) ?? 0;
  return ticket > 0 ? limitar(custo / ticket, 0, 0.95) : 0;
}

export function ticketDaCidade(
  renda: number | null,
  venda: Negocio["venda"],
): { ticket: number; imputado: boolean } {
  const base = num(venda?.ticket_medio) ?? 0;
  if (!ehNum(renda)) return { ticket: base, imputado: true };
  const referencia = num(venda?.renda_referencia) ?? 0;
  if (referencia <= 0) return { ticket: base, imputado: false };
  const elasticidade = num(venda?.elasticidade_renda) ?? 0;
  const ajustado = base * (1 + elasticidade * (renda / referencia - 1));
  return {
    ticket: limitar(ajustado, num(venda?.ticket_min) ?? 0, num(venda?.ticket_max) ?? base),
    imputado: false,
  };
}

export function capacidadeLocalAnual(
  horasSemanais: number | null,
  oftalmoEquivalente: number | null,
  d: Negocio["demanda"],
): number {
  const semanas = num(d?.semanas_por_ano) ?? 44;
  const porHora = num(d?.consultas_refracao_por_hora) ?? 2.5;
  const fracao = num(d?.fracao_tempo_em_refracao) ?? 0.45;
  let horas = horasSemanais;
  if (!ehNum(horas) || horas <= 0) {
    horas = (oftalmoEquivalente ?? 0) * (num(d?.horas_semanais_fallback) ?? 20);
  }
  return Math.max(0, horas * semanas * porHora * fracao);
}

/** Fracao da demanda nao atendida que NAO se resolve viajando ate o polo. */
export function atritoDeslocamento(distanciaKm: number | null, d: Negocio["demanda"]): number | null {
  if (!ehNum(distanciaKm)) return null;
  const saturacao = num(d?.atrito_saturacao_km) ?? 120;
  const minimo = num(d?.atrito_minimo) ?? 0;
  if (saturacao <= 0) return 1;
  return minimo + (1 - minimo) * limitar(distanciaKm / saturacao, 0, 1);
}

export interface DetalheConcorrencia {
  saturacao: { valor: number | null; fator: number };
  reputacao: { valor: number | null; fator: number };
  presenca: { valor: number | null; fator: number };
  conversao: number;
}

export function forcaConcorrencia(
  oticasPor10k: number | null,
  notaMedia: number | null,
  avaliacoesPorMil: number | null,
  cfg: Negocio["conversao"],
): { conversao: number; detalhe: DetalheConcorrencia } {
  const base = num(cfg?.base) ?? 0.4;

  const refSat = num(cfg?.saturacao_referencia) ?? 4;
  const fSat = ehNum(oticasPor10k) && refSat > 0 ? limitar(oticasPor10k / refSat, 0, 1) : 0;

  const neutra = num(cfg?.nota_neutra) ?? 4;
  const fRep = ehNum(notaMedia) ? limitar((notaMedia - (neutra - 1)) / 2, 0, 1) : 0;

  const refAval = num(cfg?.avaliacoes_referencia) ?? 40;
  const fPres = ehNum(avaliacoesPorMil) && refAval > 0 ? limitar(avaliacoesPorMil / refAval, 0, 1) : 0;

  let conversao = base;
  conversao *= 1 - (num(cfg?.peso_saturacao) ?? 0) * fSat;
  conversao *= 1 - (num(cfg?.peso_reputacao) ?? 0) * fRep;
  conversao *= 1 - (num(cfg?.peso_presenca) ?? 0) * fPres;
  conversao = limitar(conversao, num(cfg?.minimo) ?? 0, num(cfg?.maximo) ?? 1);

  return {
    conversao,
    detalhe: {
      saturacao: { valor: oticasPor10k, fator: fSat },
      reputacao: { valor: notaMedia, fator: fRep },
      presenca: { valor: avaliacoesPorMil, fator: fPres },
      conversao,
    },
  };
}

export function custoDoEvento(evento: Negocio["evento"]) {
  const dias = num(evento?.dias) ?? 1;
  const medico = (num(evento?.custo_medico_dia) ?? 0) * dias;
  const estrutura = (num(evento?.custo_estrutura_dia) ?? 0) * dias;
  const cidades = Math.max(1, num(evento?.cidades_por_circuito) ?? 1);
  const deslocamento = (num(evento?.custo_deslocamento) ?? 0) / cidades;
  const midia = num(evento?.investimento_midia) ?? 0;
  return { medico, estrutura, deslocamento, midia, total: medico + estrutura + deslocamento + midia };
}

/** Faturamento de uma cidade perfeita — o denominador do "% de possibilidade". */
export function tetoFaturamento(n: Negocio): number {
  const capacidade = (num(n.evento?.dias) ?? 1) * (num(n.evento?.consultas_por_dia) ?? 1);
  const convMax = num(n.conversao?.maximo) ?? 1;
  const ticketMax = num(n.venda?.ticket_max) ?? 1;
  return Math.max(1e-9, capacidade * convMax * ticketMax);
}

export type MunicipioProjetado = Municipio & Projecao;

/**
 * Recalcula a projecao de todos os municipios. Mesma semantica do Python,
 * incluindo a imputacao pela mediana do universo e a penalidade de confianca.
 */
export function projetar(municipios: Municipio[], n: Negocio): MunicipioProjetado[] {
  const evento = n.evento ?? {};
  const demandaCfg = n.demanda ?? {};
  const captacao = n.captacao ?? {};

  const oticas10k = municipios.map((m) => {
    const q = num(m.qtd_oticas);
    const pop = num(m.populacao_total);
    return ehNum(q) && ehNum(pop) && pop > 0 ? (q / pop) * 10000 : null;
  });
  const avaliacoesMil = municipios.map((m) => {
    const a = num(m.oticas_avaliacoes);
    const pop = num(m.populacao_total);
    return ehNum(a) && ehNum(pop) && pop > 0 ? (a / pop) * 1000 : null;
  });
  const medOticas = mediana(oticas10k);
  const medAvaliacoes = mediana(avaliacoesMil);
  const medNota = mediana(municipios.map((m) => num(m.oticas_nota_media)));
  const medDistancia = mediana(municipios.map((m) => num(m.distancia_km)));

  const custos = custoDoEvento(evento);
  const cmv = cmvFracao(n);
  const porDia = num(evento.consultas_por_dia) ?? 1;
  const diasCfg = num(evento.dias) ?? 1;
  const capacidadeEvento = diasCfg * porDia;
  const midia = num(evento.investimento_midia) ?? 0;
  const alcance = Math.min(
    num(captacao.alcance_maximo) ?? 1,
    (num(captacao.alcance_por_mil_reais) ?? 0) * (midia / 1000),
  );
  const teto = tetoFaturamento(n);
  const convMax = num(n.conversao?.maximo) ?? 1;
  const ticketMax = num(n.venda?.ticket_max) ?? 1;

  return municipios.map((m, i) => {
    const imputados: string[] = [];
    const pop40 = num(m.populacao_40mais);
    const qtdOft = num(m.qtd_oftalmologistas);
    const oftEq = num(m.oftalmo_equivalente);
    const horas = num(m.horas_semanais_total);

    const faltando: string[] = [];
    if (!ehNum(pop40)) faltando.push("populacao_40mais");
    if (!ehNum(qtdOft) && !ehNum(oftEq)) faltando.push("cnes");
    if (faltando.length) {
      return {
        ...m,
        demanda_anual: null,
        capacidade_local_ano: null,
        demanda_nao_atendida: null,
        demanda_represada: null,
        publico_evento: null,
        agendamentos_esperados: null,
        consultas_esperadas: null,
        capacidade_evento: null,
        ocupacao_agenda: null,
        conversao: null,
        vendas_esperadas: null,
        ticket_estimado: null,
        faturamento_estimado: null,
        margem_bruta: null,
        custo_evento: null,
        lucro_estimado: null,
        retorno_sobre_custo: null,
        ponto_equilibrio_vendas: null,
        dias_sugeridos: null,
        demanda_nao_capturada: null,
        potencial_pct: null,
        projecao_confianca: null,
        projecao: { disponivel: false, faltando },
      } as MunicipioProjetado;
    }

    const demandaAnual =
      pop40! * (num(demandaCfg.prevalencia_40mais) ?? 0) * (num(demandaCfg.renovacao_anual) ?? 0);
    const capacidadeLocal = capacidadeLocalAnual(horas, ehNum(oftEq) ? oftEq : qtdOft, demandaCfg);
    const naoAtendida = Math.max(0, demandaAnual - capacidadeLocal);

    let distancia = num(m.distancia_km);
    if (!ehNum(distancia) && ehNum(medDistancia)) {
      distancia = medDistancia;
      imputados.push("distancia_km");
    }
    let atrito = atritoDeslocamento(distancia, demandaCfg);
    if (!ehNum(atrito)) {
      atrito = 1;
      if (!imputados.includes("distancia_km")) imputados.push("distancia_km");
    }

    const represada = naoAtendida * atrito;
    const backlog = num(demandaCfg.backlog_anos) ?? 1;
    const publico = represada * backlog;

    const alcancados = publico * alcance;
    const agendamentos = alcancados * (num(captacao.taxa_agendamento) ?? 0);
    const comparecimentos = agendamentos * (num(captacao.taxa_comparecimento) ?? 0);
    const consultas = Math.min(comparecimentos, capacidadeEvento);
    const ocupacao = capacidadeEvento ? limitar(comparecimentos / capacidadeEvento, 0, 1) : 0;
    const diasSugeridos = porDia > 0 ? Math.max(diasCfg, Math.ceil(comparecimentos / porDia)) : diasCfg;
    const naoCapturada = Math.max(0, comparecimentos - capacidadeEvento);

    let o10k = oticas10k[i];
    if (!ehNum(o10k) && ehNum(medOticas)) {
      o10k = medOticas;
      imputados.push("qtd_oticas");
    }
    let nota = num(m.oticas_nota_media);
    let avalMil = avaliacoesMil[i];
    // Cidade sem ótica não tem reputação de concorrente para imputar: a ausência
    // aqui é informação, não buraco. Imputar a mediana puniria a cidade virgem.
    const semConcorrente = o10k === 0 && !imputados.includes("qtd_oticas");
    if (!semConcorrente) {
      if (!ehNum(nota) && ehNum(medNota) && !imputados.includes("qtd_oticas")) {
        nota = medNota;
        imputados.push("reputacao_oticas");
      }
      if (!ehNum(avalMil) && ehNum(medAvaliacoes) && !imputados.includes("qtd_oticas")) {
        avalMil = medAvaliacoes;
        if (!imputados.includes("reputacao_oticas")) imputados.push("reputacao_oticas");
      }
    }
    const { conversao, detalhe } = forcaConcorrencia(o10k, nota, avalMil, n.conversao ?? {});
    const vendas = consultas * conversao;

    const { ticket, imputado: ticketImputado } = ticketDaCidade(num(m.renda_mediana), n.venda ?? {});
    if (ticketImputado) imputados.push("renda_mediana");
    const faturamento = vendas * ticket;
    const margem = faturamento * (1 - cmv);
    const lucro = margem - custos.total;
    const retorno = custos.total > 0 ? lucro / custos.total : null;
    const margemUnitaria = ticket * (1 - cmv);
    const equilibrio = margemUnitaria > 0 ? custos.total / margemUnitaria : null;

    const potencial = limitar((100 * faturamento) / teto, 0, 100);
    const confianca = Math.max(
      0,
      1 - imputados.reduce((acc, i2) => acc + (PENALIDADE[i2] ?? 0), 0),
    );

    return {
      ...m,
      demanda_anual: demandaAnual,
      capacidade_local_ano: capacidadeLocal,
      demanda_nao_atendida: naoAtendida,
      demanda_represada: represada,
      publico_evento: publico,
      agendamentos_esperados: agendamentos,
      consultas_esperadas: consultas,
      capacidade_evento: capacidadeEvento,
      ocupacao_agenda: ocupacao,
      conversao,
      vendas_esperadas: vendas,
      ticket_estimado: ticket,
      faturamento_estimado: faturamento,
      margem_bruta: margem,
      custo_evento: custos.total,
      lucro_estimado: lucro,
      retorno_sobre_custo: retorno,
      ponto_equilibrio_vendas: equilibrio,
      dias_sugeridos: diasSugeridos,
      demanda_nao_capturada: naoCapturada,
      potencial_pct: potencial,
      projecao_confianca: Math.round(confianca * 1000) / 1000,
      projecao: {
        disponivel: true,
        imputados,
        fatores: {
          ocupacao_agenda: ocupacao,
          forca_conversao: convMax ? conversao / convMax : null,
          nivel_ticket: ticketMax ? ticket / ticketMax : null,
        },
        funil: {
          populacao_40mais: pop40!,
          demanda_anual: demandaAnual,
          capacidade_local_ano: capacidadeLocal,
          demanda_nao_atendida: naoAtendida,
          atrito_deslocamento: atrito,
          demanda_represada: represada,
          backlog_anos: backlog,
          publico_evento: publico,
          alcance_midia: alcance,
          alcancados,
          agendamentos,
          comparecimentos,
          capacidade_evento: capacidadeEvento,
          consultas,
          limitado_pela_agenda: comparecimentos > capacidadeEvento,
          demanda_nao_capturada: naoCapturada,
          dias_sugeridos: diasSugeridos,
        },
        concorrencia: detalhe,
        dinheiro: {
          vendas,
          ticket,
          faturamento,
          cmv_fracao: cmv,
          margem_bruta: margem,
          custos,
          lucro,
          ponto_equilibrio_vendas: equilibrio,
        },
        teto_faturamento: teto,
        confianca,
      },
    } as MunicipioProjetado;
  });
}

export interface CircuitoProjetado {
  circuito: number;
  municipios: number;
  nomes: string[];
  codigos: string[];
  faturamento: number;
  lucro: number;
  consultas: number;
  potencial_medio: number;
}

/** Soma o circuito pagando o deslocamento uma vez so — como a viagem acontece. */
export function projetarCircuitos(municipios: MunicipioProjetado[], n: Negocio): CircuitoProjetado[] {
  const deslocamento = num(n.evento?.custo_deslocamento) ?? 0;
  const cidadesCfg = Math.max(1, num(n.evento?.cidades_por_circuito) ?? 1);
  const grupos = new Map<number, MunicipioProjetado[]>();
  municipios.forEach((m) => {
    if (!ehNum(m.circuito) || m.circuito < 0) return;
    const lista = grupos.get(m.circuito) ?? [];
    lista.push(m);
    grupos.set(m.circuito, lista);
  });

  return Array.from(grupos.entries())
    .map(([circuito, lista]) => {
      const correcao = (deslocamento / cidadesCfg) * lista.length - deslocamento;
      const soma = (chave: keyof MunicipioProjetado) =>
        lista.reduce((a, m) => a + (num(m[chave]) ?? 0), 0);
      return {
        circuito,
        municipios: lista.length,
        nomes: lista.map((m) => m.nome),
        codigos: lista.map((m) => m.codigo_ibge),
        faturamento: soma("faturamento_estimado"),
        lucro: soma("lucro_estimado") + correcao,
        consultas: soma("consultas_esperadas"),
        potencial_medio: soma("potencial_pct") / lista.length,
      };
    })
    .sort((a, b) => b.lucro - a.lucro);
}

/** Maior diferenca entre o faturamento recalculado aqui e o gravado pelo pipeline. */
export function conferirProjecaoComPipeline(originais: Municipio[], n: Negocio): number {
  const recalculado = projetar(originais, n);
  let maior = 0;
  recalculado.forEach((m, i) => {
    const antes = num((originais[i] as MunicipioProjetado).faturamento_estimado);
    const agora = num(m.faturamento_estimado);
    if (ehNum(antes) && ehNum(agora)) maior = Math.max(maior, Math.abs(antes - agora));
  });
  return Math.round(maior * 100) / 100;
}
