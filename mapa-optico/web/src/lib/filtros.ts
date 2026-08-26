import type { Municipio } from "./types";

export interface Filtros {
  busca: string;
  uf: string;
  popMin: number | null;
  popMax: number | null;
  scoreMin: number;
  confiancaMin: number;
  /** Lucro estimado mínimo, em reais. Null = sem piso. */
  lucroMin: number | null;
  /** Esconde municípios cuja projeção não fecha a conta. */
  apenasViaveis: boolean;
  /** Esconde municípios cuja projeção depende de dado imputado. */
  apenasProjecaoConfiavel: boolean;
  area: string[] | null; // recorte feito no mapa (shift + arrastar)
}

export const FILTROS_INICIAIS: Filtros = {
  busca: "",
  uf: "",
  popMin: null,
  popMax: null,
  scoreMin: 0,
  confiancaMin: 0,
  lucroMin: null,
  apenasViaveis: false,
  apenasProjecaoConfiavel: false,
  area: null,
};

const semAcento = (s: string) =>
  s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

export function aplicar(municipios: Municipio[], f: Filtros): Municipio[] {
  const area = f.area ? new Set(f.area) : null;
  const busca = semAcento(f.busca.trim());
  return municipios.filter((m) => {
    if (area && !area.has(m.codigo_ibge)) return false;
    if (f.uf && m.uf !== f.uf) return false;
    if (busca && !semAcento(m.nome ?? "").includes(busca)) return false;
    if (m.populacao_total !== null) {
      if (f.popMin !== null && m.populacao_total < f.popMin) return false;
      if (f.popMax !== null && m.populacao_total > f.popMax) return false;
    }
    if (f.scoreMin > 0 && (m.score_total ?? -1) < f.scoreMin) return false;
    if (f.confiancaMin > 0 && m.confianca < f.confiancaMin) return false;
    // Município sem projeção não é "lucro zero" — é lucro desconhecido, e some
    // apenas quando o usuário pede explicitamente um piso de lucro.
    if (f.lucroMin !== null && (m.lucro_estimado ?? Number.NEGATIVE_INFINITY) < f.lucroMin) return false;
    if (f.apenasViaveis && !((m.lucro_estimado ?? 0) > 0)) return false;
    if (f.apenasProjecaoConfiavel && (m.projecao_confianca ?? 0) < 1) return false;
    return true;
  });
}
