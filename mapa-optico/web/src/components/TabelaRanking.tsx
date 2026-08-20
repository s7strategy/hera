/** Tabela do ranking: colunas ordenáveis, ligada ao mapa nos dois sentidos. */
import { useEffect, useMemo, useRef, useState } from "react";
import type { Municipio } from "../lib/types";
import { num, VAZIO } from "../lib/format";
import { CORES, calcularQuebras } from "./MapaChoropleth";

type Chave =
  | "posicao"
  | "nome"
  | "uf"
  | "score_total"
  | "populacao_40mais"
  | "qtd_oftalmologistas"
  | "distancia_km"
  | "qtd_oticas"
  | "confianca";

const COLUNAS: { chave: Chave; rotulo: string; titulo: string; esq?: boolean }[] = [
  { chave: "posicao", rotulo: "#", titulo: "Posição no ranking" },
  { chave: "nome", rotulo: "Município", titulo: "Nome do município", esq: true },
  { chave: "uf", rotulo: "UF", titulo: "Unidade federativa", esq: true },
  { chave: "score_total", rotulo: "Score", titulo: "Score do modelo (0–100)" },
  { chave: "populacao_40mais", rotulo: "Pop 40+", titulo: "População de 40 anos ou mais" },
  { chave: "qtd_oftalmologistas", rotulo: "Oftalmo", titulo: "Oftalmologistas únicos no CNES" },
  { chave: "distancia_km", rotulo: "km polo", titulo: "Distância rodoviária ao polo oftalmológico" },
  { chave: "qtd_oticas", rotulo: "Óticas", titulo: "Óticas encontradas no Google Places" },
  { chave: "confianca", rotulo: "Conf.", titulo: "Confiança: fração das fontes disponíveis" },
];

interface Props {
  municipios: Municipio[];
  selecionado: string | null;
  destacado: string | null;
  onSelecionar: (codigo: string | null) => void;
  onDestacar: (codigo: string | null) => void;
}

export default function TabelaRanking({
  municipios,
  selecionado,
  destacado,
  onSelecionar,
  onDestacar,
}: Props) {
  const [ordem, setOrdem] = useState<{ chave: Chave; desc: boolean }>({
    chave: "score_total",
    desc: true,
  });
  const corpoRef = useRef<HTMLDivElement>(null);

  const quebras = useMemo(
    () => calcularQuebras(municipios.map((m) => m.score_total).filter((v): v is number => v !== null)),
    [municipios],
  );

  const ordenados = useMemo(() => {
    const copia = [...municipios];
    copia.sort((a, b) => {
      const va = a[ordem.chave] as unknown;
      const vb = b[ordem.chave] as unknown;
      if (va === null || va === undefined) return 1; // nulos sempre no fim
      if (vb === null || vb === undefined) return -1;
      const cmp =
        typeof va === "number" && typeof vb === "number"
          ? va - vb
          : String(va).localeCompare(String(vb), "pt-BR");
      return ordem.desc ? -cmp : cmp;
    });
    return copia;
  }, [municipios, ordem]);

  // Selecionou pelo mapa: traz a linha para a área visível.
  useEffect(() => {
    if (!selecionado || !corpoRef.current) return;
    const linha = corpoRef.current.querySelector<HTMLElement>(`[data-codigo="${selecionado}"]`);
    linha?.scrollIntoView({ block: "nearest" });
  }, [selecionado]);

  const cor = (score: number | null) => {
    if (score === null) return "transparent";
    const i = quebras.findIndex((q) => score < q);
    return CORES[i === -1 ? CORES.length - 1 : i];
  };

  if (municipios.length === 0) {
    return (
      <div className="vazio">
        <h3>Nenhum município atende a esses filtros.</h3>
        <p>
          Reduza o score mínimo ou amplie a faixa de população. Se acabou de rodar o pipeline,
          confira se a UF filtrada é a mesma de <code>weights.yaml</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="rolagem" ref={corpoRef}>
      <table className="ranking dados">
        <thead>
          <tr>
            {COLUNAS.map((c) => (
              <th
                key={c.chave}
                className={c.esq ? "esq" : ""}
                title={c.titulo}
                aria-sort={ordem.chave === c.chave ? (ordem.desc ? "descending" : "ascending") : undefined}
                tabIndex={0}
                onClick={() =>
                  setOrdem((o) =>
                    o.chave === c.chave ? { chave: c.chave, desc: !o.desc } : { chave: c.chave, desc: true },
                  )
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setOrdem((o) =>
                      o.chave === c.chave
                        ? { chave: c.chave, desc: !o.desc }
                        : { chave: c.chave, desc: true },
                    );
                  }
                }}
              >
                {c.rotulo}
                {ordem.chave === c.chave ? (ordem.desc ? " ↓" : " ↑") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody onMouseLeave={() => onDestacar(null)}>
          {ordenados.map((m) => (
            <tr
              key={m.codigo_ibge}
              data-codigo={m.codigo_ibge}
              className={
                (m.codigo_ibge === selecionado ? "selecionada " : "") +
                (m.codigo_ibge === destacado ? "destacada" : "")
              }
              onMouseEnter={() => onDestacar(m.codigo_ibge)}
              onClick={() => onSelecionar(m.codigo_ibge)}
            >
              <td>{m.posicao}</td>
              <td className="esq nome" title={m.nome}>
                {m.nome}
                {!m.ranqueavel && (
                  <span className="aviso-confianca" title="Confiança baixa: faltam fontes para este município">
                    ⚠
                  </span>
                )}
              </td>
              <td className="esq">{m.uf}</td>
              <td className="score">
                <span className="marcador-score" style={{ background: cor(m.score_total) }} />
                {num(m.score_total, 1)}
              </td>
              <td>{num(m.populacao_40mais)}</td>
              <td>{m.qtd_oftalmologistas === null ? VAZIO : num(m.qtd_oftalmologistas)}</td>
              <td>{num(m.distancia_km, 1)}</td>
              <td>{m.qtd_oticas === null ? VAZIO : num(m.qtd_oticas)}</td>
              <td title={`${Math.round(m.confianca * 100)}% das fontes disponíveis`}>
                {num(m.confianca, 2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
