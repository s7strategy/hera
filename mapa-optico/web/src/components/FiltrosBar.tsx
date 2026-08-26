/** Filtros do conjunto. Mudou aqui, muda mapa e tabela ao mesmo tempo. */
import type { Filtros } from "../lib/filtros";
import { MODOS, type ModoOrdenacao, modoPorChave } from "../lib/ordenacao";

interface Props {
  filtros: Filtros;
  ufsDisponiveis: string[];
  modo: ModoOrdenacao;
  onMudarModo: (m: ModoOrdenacao) => void;
  onMudar: (f: Filtros) => void;
  total: number;
  visiveis: number;
  areaAtiva: boolean;
  onLimparArea: () => void;
  onExportar: () => void;
}

export default function FiltrosBar({
  filtros,
  ufsDisponiveis,
  modo,
  onMudarModo,
  onMudar,
  total,
  visiveis,
  areaAtiva,
  onLimparArea,
  onExportar,
}: Props) {
  const set = (parcial: Partial<Filtros>) => onMudar({ ...filtros, ...parcial });

  return (
    <div className="filtros">
      <div className="campo campo-modo">
        <label htmlFor="f-modo">Ordenar por</label>
        <select
          id="f-modo"
          value={modo}
          onChange={(e) => onMudarModo(e.target.value as ModoOrdenacao)}
          title={modoPorChave(modo).responde}
        >
          {MODOS.map((m) => (
            <option key={m.chave} value={m.chave}>
              {m.rotulo}
            </option>
          ))}
        </select>
        <small className="ajuda-modo">{modoPorChave(modo).responde}</small>
      </div>

      <div className="campo">
        <label htmlFor="f-busca">Município</label>
        <input
          id="f-busca"
          type="text"
          placeholder="buscar…"
          value={filtros.busca}
          onChange={(e) => set({ busca: e.target.value })}
          style={{ minWidth: 130 }}
        />
      </div>

      <div className="campo">
        <label htmlFor="f-uf">UF</label>
        <select
          id="f-uf"
          value={filtros.uf}
          onChange={(e) => set({ uf: e.target.value })}
        >
          <option value="">todas</option>
          {ufsDisponiveis.map((uf) => (
            <option key={uf} value={uf}>
              {uf}
            </option>
          ))}
        </select>
      </div>

      <div className="campo">
        <label>População</label>
        <div className="dupla dados">
          <input
            type="number"
            aria-label="População mínima"
            value={filtros.popMin ?? ""}
            placeholder="mín"
            onChange={(e) => set({ popMin: e.target.value === "" ? null : Number(e.target.value) })}
          />
          <span>–</span>
          <input
            type="number"
            aria-label="População máxima"
            value={filtros.popMax ?? ""}
            placeholder="máx"
            onChange={(e) => set({ popMax: e.target.value === "" ? null : Number(e.target.value) })}
          />
        </div>
      </div>

      <div className="campo">
        <label htmlFor="f-lucro">Lucro mínimo</label>
        <input
          id="f-lucro"
          className="dados"
          type="number"
          step={500}
          placeholder="R$ —"
          value={filtros.lucroMin ?? ""}
          onChange={(e) => set({ lucroMin: e.target.value === "" ? null : Number(e.target.value) })}
          style={{ width: 90 }}
        />
      </div>

      <div className="campo campo-caixas">
        <label>
          <input
            type="checkbox"
            checked={filtros.apenasViaveis}
            onChange={(e) => set({ apenasViaveis: e.target.checked })}
          />
          <span title="Esconde municípios cuja projeção não paga o custo do evento">só viáveis</span>
        </label>
        <label>
          <input
            type="checkbox"
            checked={filtros.apenasProjecaoConfiavel}
            onChange={(e) => set({ apenasProjecaoConfiavel: e.target.checked })}
          />
          <span title="Esconde municípios cuja projeção depende de dado imputado pela mediana">
            só dado completo
          </span>
        </label>
      </div>

      <div className="campo">
        <label htmlFor="f-score">Score mínimo: {filtros.scoreMin}</label>
        <input
          id="f-score"
          type="range"
          min={0}
          max={100}
          step={1}
          value={filtros.scoreMin}
          onChange={(e) => set({ scoreMin: Number(e.target.value) })}
        />
      </div>

      <div className="campo">
        <label htmlFor="f-conf">Confiança mín.: {filtros.confiancaMin.toFixed(2)}</label>
        <input
          id="f-conf"
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={filtros.confiancaMin}
          onChange={(e) => set({ confiancaMin: Number(e.target.value) })}
        />
      </div>

      {areaAtiva && (
        <button className="btn btn-sutil" onClick={onLimparArea} title="Remover o recorte feito no mapa">
          ✕ área do mapa
        </button>
      )}

      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
        <span className="dados" style={{ color: "var(--txt-2)", fontSize: 12 }}>
          {visiveis}/{total}
        </span>
        <button className="btn btn-acento" onClick={onExportar}>
          Exportar CSV
        </button>
      </div>
    </div>
  );
}
