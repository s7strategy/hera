export interface Componente {
  valor_bruto: number | null;
  normalizado: number | null;
  peso: number;
  tipo: string;
  disponivel: boolean;
  contribuicao: number;
  peso_efetivo?: number;
}

export interface MetaComponentes {
  peso_disponivel: number;
  peso_total: number;
  fontes: Record<string, boolean>;
}

export type Componentes = Record<string, Componente> & { _meta?: MetaComponentes };

export interface Municipio extends Projecao {
  codigo_ibge: string;
  nome: string;
  uf: string;
  microrregiao: string | null;
  mesorregiao: string | null;
  lat: number | null;
  lon: number | null;
  area_km2: number | null;
  populacao_total: number | null;
  populacao_40mais: number | null;
  renda_mediana: number | null;
  qtd_oftalmologistas: number | null;
  oftalmo_equivalente: number | null;
  horas_semanais_total: number | null;
  competencia_cnes: string | null;
  polo_codigo_ibge: string | null;
  polo_nome: string | null;
  distancia_km: number | null;
  tempo_minutos: number | null;
  qtd_oticas: number | null;
  /** Nota media das oticas locais, ponderada pelo numero de avaliacoes. Null = sem otica ou sem consulta. */
  oticas_nota_media: number | null;
  /** Soma das avaliacoes das oticas — proxy de quanto comercio otico a cidade movimenta. */
  oticas_avaliacoes: number | null;
  score_total: number | null;
  confianca: number;
  ranqueavel: boolean;
  posicao: number;
  circuito: number | null;
  componentes: Componentes;
  versao_modelo: string;
}

/* ------------------------------------------------------------------ negocio */

export interface NegocioVenda {
  ticket_medio?: number;
  custo_produto?: number;
  renda_referencia?: number;
  elasticidade_renda?: number;
  ticket_min?: number;
  ticket_max?: number;
}

export interface NegocioEvento {
  dias?: number;
  consultas_por_dia?: number;
  custo_medico_dia?: number;
  custo_estrutura_dia?: number;
  custo_deslocamento?: number;
  investimento_midia?: number;
  cidades_por_circuito?: number;
}

export interface NegocioDemanda {
  prevalencia_40mais?: number;
  renovacao_anual?: number;
  consultas_refracao_por_hora?: number;
  fracao_tempo_em_refracao?: number;
  semanas_por_ano?: number;
  horas_semanais_fallback?: number;
  atrito_saturacao_km?: number;
  atrito_minimo?: number;
  backlog_anos?: number;
}

export interface NegocioCaptacao {
  alcance_por_mil_reais?: number;
  alcance_maximo?: number;
  taxa_agendamento?: number;
  taxa_comparecimento?: number;
}

export interface NegocioConversao {
  base?: number;
  peso_saturacao?: number;
  saturacao_referencia?: number;
  peso_reputacao?: number;
  nota_neutra?: number;
  peso_presenca?: number;
  avaliacoes_referencia?: number;
  minimo?: number;
  maximo?: number;
}

export interface Negocio {
  versao?: string;
  venda?: NegocioVenda;
  evento?: NegocioEvento;
  demanda?: NegocioDemanda;
  captacao?: NegocioCaptacao;
  conversao?: NegocioConversao;
}

/** Rastro completo da projecao — e o que a ficha do municipio abre. */
export interface DetalheProjecao {
  disponivel: boolean;
  faltando?: string[];
  imputados?: string[];
  /** Os tres fatores cujo produto x100 e exatamente o potencial_pct. */
  fatores?: {
    ocupacao_agenda: number;
    forca_conversao: number | null;
    nivel_ticket: number | null;
  };
  funil?: {
    populacao_40mais: number;
    demanda_anual: number;
    capacidade_local_ano: number;
    demanda_nao_atendida: number;
    atrito_deslocamento: number;
    demanda_represada: number;
    backlog_anos: number;
    publico_evento: number;
    alcance_midia: number;
    alcancados: number;
    agendamentos: number;
    comparecimentos: number;
    capacidade_evento: number;
    consultas: number;
    limitado_pela_agenda: boolean;
    demanda_nao_capturada: number;
    dias_sugeridos: number;
  };
  concorrencia?: {
    saturacao: { valor: number | null; fator: number };
    reputacao: { valor: number | null; fator: number };
    presenca: { valor: number | null; fator: number };
    conversao: number;
  };
  dinheiro?: {
    vendas: number;
    ticket: number;
    faturamento: number;
    cmv_fracao: number;
    margem_bruta: number;
    custos: { medico: number; estrutura: number; deslocamento: number; midia: number; total: number };
    lucro: number;
    ponto_equilibrio_vendas: number | null;
  };
  teto_faturamento?: number;
  confianca?: number;
}

/** Colunas que a projecao acrescenta ao municipio. */
export interface Projecao {
  demanda_anual: number | null;
  capacidade_local_ano: number | null;
  demanda_nao_atendida: number | null;
  demanda_represada: number | null;
  publico_evento: number | null;
  agendamentos_esperados: number | null;
  consultas_esperadas: number | null;
  capacidade_evento: number | null;
  ocupacao_agenda: number | null;
  conversao: number | null;
  vendas_esperadas: number | null;
  ticket_estimado: number | null;
  faturamento_estimado: number | null;
  margem_bruta: number | null;
  custo_evento: number | null;
  lucro_estimado: number | null;
  retorno_sobre_custo: number | null;
  ponto_equilibrio_vendas: number | null;
  dias_sugeridos: number | null;
  demanda_nao_capturada: number | null;
  potencial_pct: number | null;
  projecao_confianca: number | null;
  projecao: DetalheProjecao;
}

export interface FatorCfg {
  peso: number;
  tipo: "crescente" | "inverso" | "faixa_otima";
  saturacao_km?: number;
  bonus_zero?: number;
  usar_equivalente?: boolean;
  per_capita?: boolean;
  faixa_min?: number;
  faixa_max?: number;
  decaimento?: number;
}

export interface Pesos {
  versao: string;
  filtros: { populacao_min?: number; populacao_max?: number; ufs?: string[] };
  polo?: { min_oftalmologistas: number };
  fatores: Record<string, FatorCfg>;
  confianca?: {
    peso_por_fonte?: Record<string, number>;
    minimo_para_ranquear?: number;
  };
  circuitos?: { eps_km: number; min_municipios: number };
  canibalizacao?: { raio_km: number; top_n: number };
}

export interface ParCanibalizacao {
  a: string;
  a_nome: string;
  b: string;
  b_nome: string;
  distancia_km: number;
}

export interface Otica {
  place_id: string;
  codigo_ibge: string;
  nome: string | null;
  endereco: string | null;
  rating: number | null;
  total_ratings: number | null;
  lat: number | null;
  lon: number | null;
}

export interface CircuitoSnapshot {
  circuito: number;
  municipios: number;
  nomes: string[];
  codigos: string[];
  faturamento: number;
  lucro: number;
  consultas: number;
  potencial_medio: number;
}

export interface Snapshot {
  gerado_em: string;
  versao_modelo: string;
  versao_negocio?: string;
  pesos: Pesos;
  negocio?: Negocio;
  circuitos?: CircuitoSnapshot[];
  proveniencia: {
    fontes?: Record<string, string>;
    /** Um bloco por fonte, com carimbo de tempo — alimenta a tela de sincronização. */
    detalhes?: Record<string, { origem?: string; atualizado_em?: string | null; motivo?: string; demo?: boolean }>;
    avisos?: string[];
    demo?: boolean;
  };
  /** Config das fontes embutida no snapshot para a tela estimar custo sem duplicar número. */
  fontes_config?: { places?: { termos?: string[]; custo_por_chamada_usd?: number | null } };
  avisos: string[];
  canibalizacao: ParCanibalizacao[];
  oticas: Otica[];
  municipios: Municipio[];
}

export interface Nota {
  codigo_ibge: string;
  texto: string;
  fila_sus_dias: number | null;
  criado_em: string;
}
