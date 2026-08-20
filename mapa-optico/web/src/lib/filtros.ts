import type { Municipio } from "./types";

export interface Filtros {
  busca: string;
  uf: string;
  popMin: number | null;
  popMax: number | null;
  scoreMin: number;
  confiancaMin: number;
  area: string[] | null; // recorte feito no mapa (shift + arrastar)
}

export const FILTROS_INICIAIS: Filtros = {
  busca: "",
  uf: "",
  popMin: null,
  popMax: null,
  scoreMin: 0,
  confiancaMin: 0,
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
    return true;
  });
}
