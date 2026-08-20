/**
 * Porte do modelo de score do pipeline (score/model.py) para o navegador.
 *
 * Por que duplicar: a tela de ajuste de pesos precisa recalcular o ranking ao
 * vivo enquanto o usuario arrasta os sliders — ida e volta ao Python mataria a
 * interacao. A duplicacao e deliberada e vigiada: `conferirComPipeline()`
 * recalcula com os pesos originais do snapshot e compara com os scores que o
 * Python gravou. Divergiu, a interface avisa em vez de mentir.
 *
 * Qualquer mudanca em score/model.py tem que ser espelhada aqui.
 */
import type { Componentes, FatorCfg, Municipio, Pesos } from "./types";

export const COLUNA_POR_FATOR: Record<string, keyof Municipio> = {
  distancia_polo: "distancia_km",
  ausencia_oftalmo: "oftalmo_equivalente",
  populacao_40mais: "populacao_40mais",
  concorrencia_oticas: "qtd_oticas",
  renda: "renda_mediana",
};

export const FONTE_POR_FATOR: Record<string, string> = {
  distancia_polo: "distancia_polo",
  ausencia_oftalmo: "cnes",
  populacao_40mais: "ibge_populacao",
  concorrencia_oticas: "places",
  renda: "ibge_populacao",
};

export const ROTULO_FATOR: Record<string, string> = {
  distancia_polo: "Distância ao polo",
  ausencia_oftalmo: "Ausência de oftalmologista",
  populacao_40mais: "População 40+",
  concorrencia_oticas: "Concorrência de óticas",
  renda: "Renda",
};

const ehNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Rank percentual 0–100, media nos empates, ignorando nulos (igual ao pandas rank(pct=True)). */
export function rankPct(valores: (number | null)[]): (number | null)[] {
  const indices = valores
    .map((v, i) => ({ v, i }))
    .filter((x): x is { v: number; i: number } => ehNum(x.v));
  const n = indices.length;
  const saida: (number | null)[] = valores.map(() => null);
  if (n === 0) return saida;
  const distintos = new Set(indices.map((x) => x.v));
  if (distintos.size === 1) {
    indices.forEach((x) => (saida[x.i] = 50));
    return saida;
  }
  indices.sort((a, b) => a.v - b.v);
  let k = 0;
  while (k < n) {
    let j = k;
    while (j + 1 < n && indices[j + 1].v === indices[k].v) j += 1;
    const rankMedio = (k + 1 + (j + 1)) / 2; // ranks 1-based
    for (let m = k; m <= j; m += 1) saida[indices[m].i] = (rankMedio / n) * 100;
    k = j + 1;
  }
  return saida;
}

export function curvaFaixaOtima(
  valor: number | null,
  minimo: number,
  maximo: number,
  decaimento: number,
): number | null {
  if (!ehNum(valor)) return null;
  const largura = Math.max(maximo - minimo, 1e-9);
  let fora = 0;
  if (valor < minimo) fora = minimo - valor;
  else if (valor > maximo) fora = valor - maximo;
  else return 100;
  return Math.max(0, 100 * (1 - decaimento * (fora / largura)));
}

export function aplicarFiltros(municipios: Municipio[], pesos: Pesos): Municipio[] {
  const f = pesos.filtros ?? {};
  const ufs = (f.ufs ?? []).map((u) => u.toUpperCase());
  return municipios.filter((m) => {
    if (ufs.length && !ufs.includes((m.uf ?? "").toUpperCase())) return false;
    const pop = m.populacao_total;
    // Municipio sem populacao conhecida NAO e descartado: some justamente quem
    // tem coleta pior, e isso enviesaria o ranking. Ele fica com confianca baixa.
    if (ehNum(pop)) {
      if (ehNum(f.populacao_min) && pop < f.populacao_min) return false;
      if (ehNum(f.populacao_max) && pop > f.populacao_max) return false;
    }
    return true;
  });
}

function valoresBrutos(municipios: Municipio[], nome: string, cfg: FatorCfg): (number | null)[] {
  return municipios.map((m) => {
    if (nome === "ausencia_oftalmo") {
      const usarEq = cfg.usar_equivalente !== false;
      const principal = usarEq ? m.oftalmo_equivalente : m.qtd_oftalmologistas;
      const alternativa = usarEq ? m.qtd_oftalmologistas : m.oftalmo_equivalente;
      return ehNum(principal) ? principal : ehNum(alternativa) ? alternativa : null;
    }
    if (nome === "concorrencia_oticas") {
      const qtd = m.qtd_oticas;
      if (!ehNum(qtd)) return null;
      if (!cfg.per_capita) return qtd;
      const pop = m.populacao_total;
      return ehNum(pop) && pop > 0 ? (qtd / pop) * 10000 : null;
    }
    const chave = COLUNA_POR_FATOR[nome];
    const v = chave ? (m[chave] as unknown) : null;
    return ehNum(v) ? v : null;
  });
}

function normalizar(municipios: Municipio[], nome: string, cfg: FatorCfg): (number | null)[] {
  let brutos = valoresBrutos(municipios, nome, cfg);

  if (cfg.tipo === "faixa_otima") {
    return brutos.map((v) =>
      curvaFaixaOtima(v, cfg.faixa_min ?? 0, cfg.faixa_max ?? 1, cfg.decaimento ?? 0.6),
    );
  }
  if (nome === "distancia_polo" && ehNum(cfg.saturacao_km)) {
    const teto = cfg.saturacao_km;
    brutos = brutos.map((v) => (ehNum(v) ? Math.min(v, teto) : null));
  }
  let pct = rankPct(brutos);
  if (cfg.tipo === "inverso") pct = pct.map((p) => (ehNum(p) ? 100 - p : null));
  if (nome === "ausencia_oftalmo" && ehNum(cfg.bonus_zero)) {
    const bonus = cfg.bonus_zero;
    pct = pct.map((p, i) => (ehNum(p) && brutos[i] === 0 ? Math.min(100, p + bonus) : p));
  }
  return pct;
}

export interface ResultadoScore {
  municipios: Municipio[];
  fora: number;
}

/** Recalcula score, componentes, confianca e posicao. Mesma semantica do Python. */
export function calcularScore(todos: Municipio[], pesos: Pesos): ResultadoScore {
  const universo = aplicarFiltros(todos, pesos);
  const fatores = Object.entries(pesos.fatores ?? {});
  const normalizados: Record<string, (number | null)[]> = {};
  fatores.forEach(([nome, cfg]) => (normalizados[nome] = normalizar(universo, nome, cfg)));

  const pesosFonte = pesos.confianca?.peso_por_fonte ?? {};
  const totalFonte = Object.values(pesosFonte).reduce((a, b) => a + b, 0) || 1;
  const minimoConf = pesos.confianca?.minimo_para_ranquear ?? 0;

  const calculados = universo.map((m, idx) => {
    const componentes: Componentes = {} as Componentes;
    const fontesOk: Record<string, boolean> = {};
    let pesoDisponivel = 0;
    let soma = 0;

    fatores.forEach(([nome, cfg]) => {
      const norm = normalizados[nome][idx];
      const chave = COLUNA_POR_FATOR[nome];
      const bruto = chave ? (m[chave] as unknown) : null;
      const tem = ehNum(norm);
      const fonte = FONTE_POR_FATOR[nome];
      fontesOk[fonte] = fontesOk[fonte] || tem;
      componentes[nome] = {
        valor_bruto: ehNum(bruto) ? bruto : null,
        normalizado: tem ? Math.round(norm * 100) / 100 : null,
        peso: cfg.peso,
        tipo: cfg.tipo,
        disponivel: tem,
        contribuicao: 0,
      };
      if (tem) {
        pesoDisponivel += cfg.peso;
        soma += cfg.peso * norm;
      }
    });

    let score: number | null = null;
    if (pesoDisponivel > 0) {
      score = Math.round((soma / pesoDisponivel) * 100) / 100;
      fatores.forEach(([nome]) => {
        const c = componentes[nome];
        if (c.disponivel && c.normalizado !== null) {
          c.contribuicao = Math.round(((c.normalizado * c.peso) / pesoDisponivel) * 100) / 100;
          c.peso_efetivo = Math.round((c.peso / pesoDisponivel) * 1000) / 10;
        }
      });
    }

    const confianca =
      Math.round(
        (Object.entries(pesosFonte).reduce((acc, [fonte, peso]) => acc + (fontesOk[fonte] ? peso : 0), 0) /
          totalFonte) *
          1000,
      ) / 1000;

    componentes._meta = {
      peso_disponivel: pesoDisponivel,
      peso_total: fatores.reduce((a, [, cfg]) => a + cfg.peso, 0),
      fontes: fontesOk,
    };

    return {
      ...m,
      score_total: score,
      confianca,
      ranqueavel: confianca >= minimoConf && score !== null,
      componentes,
      versao_modelo: pesos.versao,
    };
  });

  calculados.sort((a, b) => (b.score_total ?? -1) - (a.score_total ?? -1));
  calculados.forEach((m, i) => (m.posicao = i + 1));
  return { municipios: calculados, fora: todos.length - universo.length };
}

/** Diferenca maxima entre o score recalculado no navegador e o gravado pelo pipeline. */
export function conferirComPipeline(originais: Municipio[], pesos: Pesos): number {
  const { municipios } = calcularScore(originais, pesos);
  const porCodigo = new Map(originais.map((m) => [m.codigo_ibge, m.score_total]));
  let maior = 0;
  municipios.forEach((m) => {
    const antes = porCodigo.get(m.codigo_ibge);
    if (ehNum(antes) && ehNum(m.score_total)) maior = Math.max(maior, Math.abs(antes - m.score_total));
  });
  return Math.round(maior * 100) / 100;
}

/** Municipios do topo perto demais um do outro — mesmo criterio do pipeline. */
export function paresCanibalizacao(municipios: Municipio[], pesos: Pesos) {
  const raio = pesos.canibalizacao?.raio_km ?? 30;
  const topN = pesos.canibalizacao?.top_n ?? 20;
  const topo = municipios.filter((m) => m.ranqueavel && ehNum(m.lat) && ehNum(m.lon)).slice(0, topN);
  const pares: { a: Municipio; b: Municipio; km: number }[] = [];
  for (let i = 0; i < topo.length; i += 1) {
    for (let j = i + 1; j < topo.length; j += 1) {
      const km = haversineKm(topo[i].lat!, topo[i].lon!, topo[j].lat!, topo[j].lon!);
      if (km <= raio) pares.push({ a: topo[i], b: topo[j], km: Math.round(km * 10) / 10 });
    }
  }
  return pares.sort((x, y) => x.km - y.km);
}

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371.0088;
  const rad = (g: number) => (g * Math.PI) / 180;
  const dLat = rad(lat2 - lat1);
  const dLon = rad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}
