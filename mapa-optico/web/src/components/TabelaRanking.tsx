/** Tabela do ranking: dinheiro primeiro, ligada ao mapa nos dois sentidos. */
import { useEffect, useMemo, useRef, useState } from "react";
import type { Municipio } from "../lib/types";
import { moedaCurta, num, pontos, VAZIO } from "../lib/format";
import { type ModoOrdenacao, ordenarPor, reposicionar } from "../lib/ordenacao";
import { CORES, calcularQuebras } from "./MapaChoropleth";

type Chave =
  | "posicao"
  | "nome"
  | "uf"
  | "potencial_pct"
  | "lucro_estimado"
  | "faturamento_estimado"
  | "consultas_esperadas"
  | "qtd_oticas"
  | "oticas_nota_media"
  | "qtd_oftalmologistas"
  | "distancia_km"
  | "populacao_40mais"
  | "score_total"
  | "confianca";

interface Coluna {
  chave: Chave;
  rotulo: string;
  titulo: string;
  esq?: boolean;
}

const COLUNAS: Coluna[] = [
  { chave: "posicao", rotulo: "#", titulo: "Posição na ordenação atual" },
  { chave: "nome", rotulo: "Município", titulo: "Nome do município", esq: true },
  { chave: "uf", rotulo: "UF", titulo: "Unidade federativa", esq: true },
  {
    chave: "potencial_pct",
    rotulo: "Potencial",
    titulo:
      "Faturamento estimado contra o teto teórico (agenda cheia × conversão máxima × ticket máximo). " +
      "Combina médicos, óticas, notas e renda num número só.",
  },
  { chave: "lucro_estimado", rotulo: "Lucro", titulo: "Margem bruta menos custo do evento e mídia" },
  { chave: "faturamento_estimado", rotulo: "Faturam.", titulo: "Pares vendidos × ticket estimado" },
  {
    chave: "consultas_esperadas",
    rotulo: "Consultas",
    titulo: "Quem senta na cadeira, limitado pela agenda física do médico",
  },
  { chave: "qtd_oticas", rotulo: "Óticas", titulo: "Óticas concorrentes encontradas no Google Places" },
  {
    chave: "oticas_nota_media",
    rotulo: "Nota",
    titulo: "Nota média das óticas locais, ponderada por avaliações. Nota baixa é oportunidade.",
  },
  { chave: "qtd_oftalmologistas", rotulo: "Oftalmo", titulo: "Oftalmologistas únicos no CNES" },
  { chave: "distancia_km", rotulo: "km polo", titulo: "Distância rodoviária ao polo oftalmológico" },
  { chave: "populacao_40mais", rotulo: "Pop 40+", titulo: "População de 40 anos ou mais" },
  { chave: "score_total", rotulo: "Demanda", titulo: "Score de demanda reprimida (0–100)" },
  { chave: "confianca", rotulo: "Conf.", titulo: "Confiança: fração das fontes disponíveis" },
];

interface Props {
  municipios: Municipio[];
  modo: ModoOrdenacao;
  selecionado: string | null;
  destacado: string | null;
  onSelecionar: (codigo: string | null) => void;
  onDestacar: (codigo: string | null) => void;
}

export default function TabelaRanking({
  municipios,
  modo,
  selecionado,
  destacado,
  onSelecionar,
  onDestacar,
}: Props) {
  // null = seguir o modo escolhido na barra; clicar num cabeçalho assume o controle.
  const [ordem, setOrdem] = useState<{ chave: Chave; desc: boolean } | null>(null);
  const corpoRef = useRef<HTMLDivElement>(null);

  // Trocar o modo na barra devolve o controle para a barra.
  useEffect(() => setOrdem(null), [modo]);

  const quebras = useMemo(
    () =>
      calcularQuebras(
        municipios.map((m) => m.potencial_pct).filter((v): v is number => v !== null && v !== undefined),
      ),
    [municipios],
  );

  const ordenados = useMemo(() => {
    if (!ordem) return reposicionar(ordenarPor(municipios, modo));
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
  }, [municipios, ordem, modo]);

  // Selecionou pelo mapa: traz a linha para a área visível.
  useEffect(() => {
    if (!selecionado || !corpoRef.current) return;
    const linha = corpoRef.current.querySelector<HTMLElement>(`[data-codigo="${selecionado}"]`);
    linha?.scrollIntoView({ block: "nearest" });
  }, [selecionado]);

  const cor = (valor: number | null) => {
    if (valor === null || valor === undefined) return "transparent";
    const i = quebras.findIndex((q) => valor < q);
    return CORES[i === -1 ? CORES.length - 1 : i];
  };

  const alternar = (chave: Chave) =>
    setOrdem((o) => (o?.chave === chave ? { chave, desc: !o.desc } : { chave, desc: true }));

  const chaveOrdenada: string = ordem?.chave ?? modo;

  if (municipios.length === 0) {
    return (
      <div className="vazio">
        <h3>Nenhum município atende a esses filtros.</h3>
        <p>
          Reduza o lucro mínimo, desligue “só viáveis” ou amplie a faixa de população. Se acabou de
          rodar o pipeline, confira se a UF filtrada é a mesma de <code>weights.yaml</code>.
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
                aria-sort={
                  chaveOrdenada === c.chave
                    ? ordem
                      ? ordem.desc
                        ? "descending"
                        : "ascending"
                      : "descending"
                    : undefined
                }
                tabIndex={0}
                onClick={() => alternar(c.chave)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    alternar(c.chave);
                  }
                }}
              >
                {c.rotulo}
                {chaveOrdenada === c.chave ? (ordem && !ordem.desc ? " ↑" : " ↓") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody onMouseLeave={() => onDestacar(null)}>
          {ordenados.map((m) => {
            const semProjecao = m.faturamento_estimado === null || m.faturamento_estimado === undefined;
            return (
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
                    <span
                      className="aviso-confianca"
                      title="Confiança baixa: faltam fontes para este município"
                    >
                      ⚠
                    </span>
                  )}
                  {(m.projecao_confianca ?? 1) < 1 && !semProjecao && (
                    <span
                      className="aviso-imputado"
                      title="Projeção usa dado imputado pela mediana — abra a ficha para ver qual"
                    >
                      ~
                    </span>
                  )}
                </td>
                <td className="esq">{m.uf}</td>
                <td className="score" title={semProjecao ? "Sem dado suficiente para projetar" : undefined}>
                  <span className="marcador-score" style={{ background: cor(m.potencial_pct) }} />
                  {pontos(m.potencial_pct, 1)}
                </td>
                <td className={(m.lucro_estimado ?? 0) > 0 ? "bom" : (m.lucro_estimado ?? null) === null ? "" : "ruim"}>
                  {moedaCurta(m.lucro_estimado)}
                </td>
                <td>{moedaCurta(m.faturamento_estimado)}</td>
                <td
                  title={
                    m.projecao?.funil?.limitado_pela_agenda
                      ? `Agenda cheia. A demanda daria para ${m.dias_sugeridos} dias.`
                      : undefined
                  }
                >
                  {num(m.consultas_esperadas)}
                  {m.projecao?.funil?.limitado_pela_agenda ? "*" : ""}
                </td>
                <td>{m.qtd_oticas === null ? VAZIO : num(m.qtd_oticas)}</td>
                <td>{num(m.oticas_nota_media, 1)}</td>
                <td>{m.qtd_oftalmologistas === null ? VAZIO : num(m.qtd_oftalmologistas)}</td>
                <td>{num(m.distancia_km, 1)}</td>
                <td>{num(m.populacao_40mais)}</td>
                <td>{num(m.score_total, 1)}</td>
                <td title={`${Math.round(m.confianca * 100)}% das fontes disponíveis`}>
                  {num(m.confianca, 2)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
