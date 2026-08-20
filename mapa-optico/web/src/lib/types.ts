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

export interface Municipio {
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
  score_total: number | null;
  confianca: number;
  ranqueavel: boolean;
  posicao: number;
  circuito: number | null;
  componentes: Componentes;
  versao_modelo: string;
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

export interface Snapshot {
  gerado_em: string;
  versao_modelo: string;
  pesos: Pesos;
  proveniencia: { fontes?: Record<string, string>; avisos?: string[]; demo?: boolean };
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
