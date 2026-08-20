/**
 * Cliente da rota /api/sincronizar.
 *
 * O navegador nunca vê o token do GitHub: ele só pede "dispara" e "como está".
 * Toda a decisão de o que pode ser disparado mora na função serverless.
 */

export type EstadoExecucao = "queued" | "in_progress" | "completed" | string;

export interface Execucao {
  id: number;
  estado: EstadoExecucao;
  resultado: "success" | "failure" | "cancelled" | null;
  criado_em: string;
  atualizado_em: string;
  url: string;
}

export interface RespostaEstado {
  configurado: boolean;
  motivo?: string;
  erro?: string;
  execucoes?: Execucao[];
}

export interface OpcoesSincronizacao {
  ufs: string;
  com_places: boolean;
  com_osrm: boolean;
  refresh: boolean;
}

/** Rodando fora da Vercel (vite dev), a rota não existe: isso não é erro. */
const SEM_ROTA =
  "A rota /api/sincronizar não respondeu. Em desenvolvimento local ela não existe — " +
  "ela sobe junto com o deploy na Vercel.";

export async function lerEstado(): Promise<RespostaEstado> {
  let r: Response;
  try {
    r = await fetch("/api/sincronizar", { headers: { Accept: "application/json" } });
  } catch {
    return { configurado: false, motivo: SEM_ROTA };
  }
  if (r.status === 404) return { configurado: false, motivo: SEM_ROTA };
  try {
    return (await r.json()) as RespostaEstado;
  } catch {
    return { configurado: false, motivo: SEM_ROTA };
  }
}

export async function dispararSincronizacao(
  opcoes: OpcoesSincronizacao,
): Promise<{ ok: boolean; erro?: string }> {
  try {
    const r = await fetch("/api/sincronizar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opcoes),
    });
    const corpo = (await r.json().catch(() => ({}))) as { ok?: boolean; erro?: string; motivo?: string };
    if (r.ok && corpo.ok) return { ok: true };
    return { ok: false, erro: corpo.erro ?? corpo.motivo ?? `Resposta ${r.status}` };
  } catch {
    return { ok: false, erro: SEM_ROTA };
  }
}

/* ------------------------------------------------------------------ fontes */

export interface FonteSincronizavel {
  chave: string;
  /** Blocos de proveniência que compõem esta fonte na visão do usuário. */
  blocos: string[];
  rotulo: string;
  origem: string;
  /** Quanto tempo essa fonte aguenta antes de valer a pena atualizar. */
  validadeDias: number;
  custa: boolean;
  explicacao: string;
}

export const FONTES: FonteSincronizavel[] = [
  {
    chave: "cnes",
    blocos: ["cnes_SC", "cnes"],
    rotulo: "Médicos oftalmologistas",
    origem: "CNES / DATASUS",
    validadeDias: 35, // o CNES publica uma competência por mês
    custa: false,
    explicacao: "Quantos oftalmologistas cada cidade tem e quantas horas eles atendem.",
  },
  {
    chave: "populacao",
    blocos: ["populacao", "renda"],
    rotulo: "População e renda",
    origem: "IBGE / SIDRA",
    validadeDias: 365, // Censo; muda de dez em dez anos, mas a projeção é anual
    custa: false,
    explicacao: "População de 40 anos ou mais e renda mediana — o mercado endereçável.",
  },
  {
    chave: "oticas",
    blocos: ["oticas"],
    rotulo: "Óticas concorrentes",
    origem: "Google Places",
    validadeDias: 180,
    custa: true,
    explicacao: "Quantidade, nota média e volume de avaliações das óticas de cada cidade.",
  },
  {
    chave: "distancia_polo",
    blocos: ["distancia_polo"],
    rotulo: "Distância até o polo",
    origem: "OSRM",
    validadeDias: 180,
    custa: false,
    explicacao: "Quanto o morador precisa rodar para conseguir uma receita hoje.",
  },
  {
    chave: "municipios",
    blocos: ["municipios", "malha_SC", "malha"],
    rotulo: "Municípios e malha",
    origem: "IBGE",
    validadeDias: 730,
    custa: false,
    explicacao: "Nomes, códigos e o desenho de cada município no mapa.",
  },
];

export interface DetalheFonte {
  origem?: string;
  atualizado_em?: string | null;
  motivo?: string;
  demo?: boolean;
  [k: string]: unknown;
}

export type Situacao = "atual" | "envelhecendo" | "refazer" | "indisponivel" | "demo";

export interface EstadoFonte {
  fonte: FonteSincronizavel;
  situacao: Situacao;
  atualizadoEm: string | null;
  diasAtras: number | null;
  motivo?: string;
  extras: DetalheFonte;
}

export const ROTULO_SITUACAO: Record<Situacao, string> = {
  atual: "atual",
  envelhecendo: "envelhecendo",
  refazer: "refazer",
  indisponivel: "nunca coletado",
  demo: "sintético",
};

/**
 * Cruza os blocos de proveniência do snapshot com o catálogo de fontes.
 *
 * Um bloco pode variar de nome por UF (`cnes_SC`, `malha_SC`), então casa por
 * prefixo. Fonte sem nenhum bloco correspondente é "nunca coletado" — não
 * "atual", que é o erro que faria o usuário confiar num dado que não existe.
 */
export function estadoDasFontes(
  detalhes: Record<string, DetalheFonte> | undefined,
  agora: Date = new Date(),
): EstadoFonte[] {
  const mapa = detalhes ?? {};
  return FONTES.map((fonte) => {
    const chaves = Object.keys(mapa).filter((k) =>
      fonte.blocos.some((b) => k === b || k.startsWith(`${b}_`)),
    );
    const encontrados = chaves.map((k) => mapa[k]);

    if (!encontrados.length) {
      return { fonte, situacao: "indisponivel" as Situacao, atualizadoEm: null, diasAtras: null, extras: {} };
    }
    if (encontrados.some((d) => d?.demo)) {
      return { fonte, situacao: "demo" as Situacao, atualizadoEm: null, diasAtras: null, extras: encontrados[0] ?? {} };
    }

    const falhou = encontrados.find((d) => d?.origem === "indisponivel");
    if (falhou) {
      return {
        fonte,
        situacao: "indisponivel" as Situacao,
        atualizadoEm: null,
        diasAtras: null,
        motivo: falhou.motivo,
        extras: falhou,
      };
    }

    // Entre vários blocos, o mais VELHO manda: a fonte só está atual se tudo
    // que a compõe estiver atual.
    const datas = encontrados
      .map((d) => d?.atualizado_em)
      .filter((v): v is string => typeof v === "string");
    if (!datas.length) {
      return { fonte, situacao: "indisponivel" as Situacao, atualizadoEm: null, diasAtras: null, extras: encontrados[0] ?? {} };
    }
    const maisVelha = datas.reduce((a, b) => (a < b ? a : b));
    const dias = Math.floor((agora.getTime() - new Date(maisVelha).getTime()) / 86_400_000);
    const situacao: Situacao =
      dias <= fonte.validadeDias ? "atual" : dias <= fonte.validadeDias * 2 ? "envelhecendo" : "refazer";
    return { fonte, situacao, atualizadoEm: maisVelha, diasAtras: dias, extras: encontrados[0] ?? {} };
  });
}

/** Estimativa da conta do Places antes de gastar. Nunca disparar sem mostrar isto. */
export function estimarCustoPlaces(
  municipios: number,
  cfg: { termos?: string[]; custo_por_chamada_usd?: number | null } | undefined,
): { chamadas: number; usd: number; porChamada: number } | null {
  const porChamada = cfg?.custo_por_chamada_usd;
  if (typeof porChamada !== "number" || !Number.isFinite(porChamada)) return null;
  const termos = Math.max(1, cfg?.termos?.length ?? 1);
  const chamadas = municipios * termos;
  return { chamadas, usd: chamadas * porChamada, porChamada };
}

export function tempoRelativo(iso: string | null): string {
  if (!iso) return "nunca";
  const dias = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (dias <= 0) return "hoje";
  if (dias === 1) return "ontem";
  if (dias < 30) return `há ${dias} dias`;
  const meses = Math.round(dias / 30);
  if (meses < 24) return `há ${meses} ${meses === 1 ? "mês" : "meses"}`;
  return `há ${Math.round(meses / 12)} anos`;
}
