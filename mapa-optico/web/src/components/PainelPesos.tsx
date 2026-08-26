/**
 * Ajuste de pesos: sliders, recálculo ao vivo e comparação lado a lado.
 *
 * O recálculo roda no navegador (lib/score.ts, porte de score/model.py). O selo
 * de conferência no topo recalcula com os pesos originais e compara com o que o
 * pipeline gravou: se os dois modelos divergirem, a tela avisa em vez de fingir
 * que está tudo certo.
 */
import { useMemo, useState } from "react";
import type { Municipio, Pesos } from "../lib/types";
import { num } from "../lib/format";
import { ROTULO_FATOR, calcularScore, conferirComPipeline } from "../lib/score";

interface Props {
  pesosBase: Pesos;
  pesos: Pesos;
  municipios: Municipio[];
  rankingBase: Municipio[];
  onMudar: (p: Pesos) => void;
  onRestaurar: () => void;
}

const AJUDA: Record<string, string> = {
  distancia_polo: "Peso do custo de acesso: quanto o morador precisa se deslocar para conseguir receita.",
  ausencia_oftalmo: "Peso da falta de oferta local, já ponderada por carga horária.",
  populacao_40mais: "Peso do mercado endereçável (presbiopia).",
  concorrencia_oticas: "Peso das óticas já instaladas.",
  renda: "Peso da faixa ótima de renda.",
};

export default function PainelPesos({
  pesosBase,
  pesos,
  municipios,
  rankingBase,
  onMudar,
  onRestaurar,
}: Props) {
  const [quantidade, setQuantidade] = useState(20);

  const divergencia = useMemo(
    () => conferirComPipeline(municipios, pesosBase),
    [municipios, pesosBase],
  );

  const { municipios: rankingNovo } = useMemo(
    () => calcularScore(municipios, pesos),
    [municipios, pesos],
  );

  const posicaoBase = useMemo(
    () => new Map(rankingBase.map((m) => [m.codigo_ibge, m.posicao])),
    [rankingBase],
  );
  const scoreBase = useMemo(
    () => new Map(rankingBase.map((m) => [m.codigo_ibge, m.score_total])),
    [rankingBase],
  );

  const somaPesos = Object.values(pesos.fatores).reduce((a, f) => a + f.peso, 0);

  const mudarFator = (nome: string, campo: string, valor: number) =>
    onMudar({
      ...pesos,
      fatores: {
        ...pesos.fatores,
        [nome]: { ...pesos.fatores[nome], [campo]: valor },
      },
    });

  return (
    <div className="tela-pesos">
      <div className="pesos-grade">
        <div className="cartao">
          <h3>Pesos do modelo</h3>
          {Object.entries(pesos.fatores).map(([nome, cfg]) => (
            <div className="slider-linha" key={nome}>
              <div className="slider-linha-topo">
                <label htmlFor={`p-${nome}`}>{ROTULO_FATOR[nome] ?? nome}</label>
                <span className="dados">
                  {cfg.peso} <span style={{ color: "var(--txt-3)" }}>({num((cfg.peso / somaPesos) * 100, 0)}%)</span>
                </span>
              </div>
              <input
                id={`p-${nome}`}
                type="range"
                min={0}
                max={50}
                step={1}
                value={cfg.peso}
                onChange={(e) => mudarFator(nome, "peso", Number(e.target.value))}
              />
              <div className="slider-ajuda">{AJUDA[nome]}</div>

              {nome === "distancia_polo" && (
                <div className="slider-linha-topo" style={{ marginTop: 6 }}>
                  <label htmlFor="p-sat" style={{ fontSize: 11, color: "var(--txt-2)" }}>
                    Saturação (km)
                  </label>
                  <input
                    id="p-sat"
                    type="number"
                    className="dados"
                    style={{ width: 78, background: "var(--bg-2)", border: "1px solid var(--linha-forte)", borderRadius: 4, padding: "2px 6px" }}
                    value={cfg.saturacao_km ?? 150}
                    onChange={(e) => mudarFator(nome, "saturacao_km", Number(e.target.value))}
                  />
                </div>
              )}
              {nome === "ausencia_oftalmo" && (
                <div className="slider-linha-topo" style={{ marginTop: 6 }}>
                  <label htmlFor="p-bonus" style={{ fontSize: 11, color: "var(--txt-2)" }}>
                    Bônus para zero oftalmologista
                  </label>
                  <input
                    id="p-bonus"
                    type="number"
                    className="dados"
                    style={{ width: 78, background: "var(--bg-2)", border: "1px solid var(--linha-forte)", borderRadius: 4, padding: "2px 6px" }}
                    value={cfg.bonus_zero ?? 0}
                    onChange={(e) => mudarFator(nome, "bonus_zero", Number(e.target.value))}
                  />
                </div>
              )}
              {nome === "renda" && (
                <div className="slider-linha-topo" style={{ marginTop: 6, gap: 6 }}>
                  <label style={{ fontSize: 11, color: "var(--txt-2)" }}>Faixa ótima (R$)</label>
                  <span className="dupla dados">
                    <input
                      type="number"
                      aria-label="Renda mínima da faixa ótima"
                      style={{ width: 72, background: "var(--bg-2)", border: "1px solid var(--linha-forte)", borderRadius: 4, padding: "2px 6px" }}
                      value={cfg.faixa_min ?? 0}
                      onChange={(e) => mudarFator(nome, "faixa_min", Number(e.target.value))}
                    />
                    <span>–</span>
                    <input
                      type="number"
                      aria-label="Renda máxima da faixa ótima"
                      style={{ width: 72, background: "var(--bg-2)", border: "1px solid var(--linha-forte)", borderRadius: 4, padding: "2px 6px" }}
                      value={cfg.faixa_max ?? 0}
                      onChange={(e) => mudarFator(nome, "faixa_max", Number(e.target.value))}
                    />
                  </span>
                </div>
              )}
            </div>
          ))}

          <div className="soma-pesos">
            Soma dos pesos: <b className="dados">{somaPesos}</b> — o modelo normaliza pela soma
            disponível, então a escala absoluta não importa, só a proporção entre fatores.
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            <button className="btn" onClick={onRestaurar}>
              Restaurar pesos do pipeline
            </button>
            <button
              className="btn btn-sutil"
              onClick={() => navigator.clipboard?.writeText(gerarYaml(pesos))}
              title="Copia o trecho de weights.yaml para colar no pipeline"
            >
              Copiar como weights.yaml
            </button>
          </div>
          <p style={{ color: "var(--txt-3)", fontSize: 11, marginBottom: 0 }}>
            O ajuste aqui é exploratório e vive só neste navegador. Para valer no pipeline (e no
            banco), cole o YAML em <code>pipeline/config/weights.yaml</code> e rode{" "}
            <code>mapa-optico score</code>.
          </p>
        </div>

        <div className="cartao">
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
            <h3 style={{ margin: 0 }}>Ranking: pesos novos × pesos do pipeline</h3>
            <span
              className={`pilula ${divergencia <= 0.5 ? "pilula-ok" : "pilula-alerta"}`}
              title="Diferença máxima entre o modelo do navegador e o do pipeline, com os pesos originais"
            >
              conferência: {divergencia <= 0.5 ? "confere" : `divergência de ${num(divergencia, 2)} pts`}
            </span>
            <label className="campo" style={{ marginLeft: "auto" }}>
              <span style={{ fontSize: 10, textTransform: "uppercase", color: "var(--txt-3)" }}>
                linhas
              </span>
              <select value={quantidade} onChange={(e) => setQuantidade(Number(e.target.value))}>
                {[10, 20, 50, 100].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div style={{ overflow: "auto", maxHeight: "62vh" }}>
            <table className="comparacao dados">
              <thead>
                <tr>
                  <th>#</th>
                  <th className="esq">Município</th>
                  <th>Score novo</th>
                  <th>Score atual</th>
                  <th>Δ score</th>
                  <th>Posição antes</th>
                  <th>Δ posição</th>
                </tr>
              </thead>
              <tbody>
                {rankingNovo.slice(0, quantidade).map((m) => {
                  const antes = posicaoBase.get(m.codigo_ibge);
                  const scoreAntes = scoreBase.get(m.codigo_ibge) ?? null;
                  const deltaPos = antes !== undefined ? antes - m.posicao : null;
                  const deltaScore =
                    scoreAntes !== null && m.score_total !== null ? m.score_total - scoreAntes : null;
                  const classe =
                    deltaPos === null || deltaPos === 0 ? "igual" : deltaPos > 0 ? "subiu" : "caiu";
                  return (
                    <tr key={m.codigo_ibge}>
                      <td>{m.posicao}</td>
                      <td className="esq" style={{ fontFamily: "var(--fonte-ui)" }}>
                        {m.nome}
                      </td>
                      <td>{num(m.score_total, 1)}</td>
                      <td style={{ color: "var(--txt-3)" }}>{num(scoreAntes, 1)}</td>
                      <td className={deltaScore === null ? "igual" : deltaScore >= 0 ? "subiu" : "caiu"}>
                        {deltaScore === null ? "—" : `${deltaScore >= 0 ? "+" : ""}${num(deltaScore, 1)}`}
                      </td>
                      <td style={{ color: "var(--txt-3)" }}>{antes ?? "—"}</td>
                      <td className={classe}>
                        {deltaPos === null ? "—" : deltaPos === 0 ? "=" : deltaPos > 0 ? `▲ ${deltaPos}` : `▼ ${-deltaPos}`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function gerarYaml(pesos: Pesos): string {
  const linhas: string[] = [`versao: "${pesos.versao}"`, "", "fatores:"];
  Object.entries(pesos.fatores).forEach(([nome, cfg]) => {
    linhas.push(`  ${nome}:`);
    Object.entries(cfg).forEach(([chave, valor]) => {
      linhas.push(`    ${chave}: ${typeof valor === "string" ? valor : valor}`);
    });
  });
  return linhas.join("\n");
}
