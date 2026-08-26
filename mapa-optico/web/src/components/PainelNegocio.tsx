/**
 * Parâmetros do negócio: mexer no ticket, no custo e nas taxas e ver o ranking
 * de faturamento se refazer na hora.
 *
 * Cada campo carrega a origem do número, porque a confiança neles é muito
 * diferente e isso muda como o usuário deve tratá-los:
 *
 *   informado    veio da operação. Só muda quando a operação mudar.
 *   estimado     constante clínica ou demográfica, com base defensável.
 *   calibrável   chute inicial. Move o TAMANHO da projeção, não a ORDEM do
 *                ranking, porque incide igual em todos os municípios.
 *
 * Essa última distinção é a mais importante da tela: enquanto não houver evento
 * executado, os calibráveis são a maior fonte de erro absoluto — e mesmo assim
 * a comparação entre cidades continua de pé.
 */
import { useMemo, useState } from "react";
import type { Municipio, Negocio } from "../lib/types";
import { moeda, moedaCurta, num, pct } from "../lib/format";
import { conferirProjecaoComPipeline, margemPorPar, projetar } from "../lib/projecao";
import { ordenarPor, reposicionar } from "../lib/ordenacao";

type Origem = "informado" | "estimado" | "calibravel";

interface Campo {
  caminho: [keyof Negocio, string];
  rotulo: string;
  origem: Origem;
  ajuda: string;
  min: number;
  max: number;
  passo: number;
  formato?: "reais" | "pct" | "num";
}

const GRUPOS: { titulo: string; nota: string; campos: Campo[] }[] = [
  {
    titulo: "O que você vende",
    nota:
      "A faixa que você pratica. Referência: o ticket médio do setor óptico brasileiro fica perto " +
      "de R$ 250 por par — a sua faixa está bem acima, o que faz sentido para venda com a receita " +
      "na mão, mas é um número a vigiar.",
    campos: [
      {
        caminho: ["venda", "ticket_medio"],
        rotulo: "Ticket médio",
        origem: "informado",
        ajuda: "Meio da faixa que você pratica. Você citou de 400 a 1.200 o par completo.",
        min: 200,
        max: 2000,
        passo: 25,
        formato: "reais",
      },
      {
        caminho: ["venda", "ticket_min"],
        rotulo: "Piso da faixa",
        origem: "informado",
        ajuda: "O par mais barato que você vende. Segura o ticket nas cidades de renda baixa.",
        min: 100,
        max: 1500,
        passo: 25,
        formato: "reais",
      },
      {
        caminho: ["venda", "ticket_max"],
        rotulo: "Teto da faixa",
        origem: "informado",
        ajuda: "O par mais caro. Também é o teto teórico usado no cálculo do potencial %.",
        min: 300,
        max: 3000,
        passo: 50,
        formato: "reais",
      },
      {
        caminho: ["venda", "elasticidade_renda"],
        rotulo: "Sensibilidade à renda",
        origem: "calibravel",
        ajuda: "0 = mesmo ticket em toda cidade. 1 = ticket proporcional à renda local.",
        min: 0,
        max: 1,
        passo: 0.05,
        formato: "num",
      },
      {
        caminho: ["venda", "alcance_crediario"],
        rotulo: "Vendas no crediário",
        origem: "calibravel",
        ajuda:
          "Quanto do que você vende sai a prazo. É o que solta o ticket da renda local: " +
          "a decisão do cliente vira “cabe a parcela?” em vez de “tenho o valor hoje?”. " +
          "Em 0 o crediário não existe e a cidade pobre compra o par barato.",
        min: 0,
        max: 1,
        passo: 0.05,
        formato: "pct",
      },
    ],
  },
  {
    titulo: "O que você paga ao fornecedor",
    nota:
      "O custo NÃO é uma fração fixa do preço: par de R$ 400 custa 10% dele, par de R$ 1.200 custa " +
      "15%. O modelo interpola entre os dois pontos que você informou, então lente boa não fica " +
      "barata demais nem lente básica cara demais.",
    campos: [
      {
        caminho: ["venda", "custo_par.custo_baixo"],
        rotulo: "Custo do par mais barato",
        origem: "informado",
        ajuda: "Quanto custa o par no piso da faixa. Você citou R$ 40 no par de R$ 400.",
        min: 10,
        max: 400,
        passo: 5,
        formato: "reais",
      },
      {
        caminho: ["venda", "custo_par.custo_alto"],
        rotulo: "Custo do par mais caro",
        origem: "informado",
        ajuda: "Quanto custa o par no teto da faixa. Você citou R$ 180 no par de R$ 1.200.",
        min: 20,
        max: 800,
        passo: 10,
        formato: "reais",
      },
      {
        caminho: ["venda", "custo_par.custo_maximo"],
        rotulo: "Teto absoluto do custo",
        origem: "informado",
        ajuda: "Trava: nenhum par completo custa mais que isso, aconteça o que acontecer.",
        min: 50,
        max: 1000,
        passo: 10,
        formato: "reais",
      },
    ],
  },
  {
    titulo: "Como o evento roda",
    nota: "Define o teto físico: nenhuma cidade rende além do que o médico consegue atender.",
    campos: [
      {
        caminho: ["evento", "dias"],
        rotulo: "Dias de evento",
        origem: "informado",
        ajuda: "Quantos dias o médico fica na cidade.",
        min: 1,
        max: 10,
        passo: 1,
        formato: "num",
      },
      {
        caminho: ["evento", "consultas_por_dia"],
        rotulo: "Consultas por dia, por médico",
        origem: "estimado",
        ajuda: "Teto físico de refrações que um oftalmologista faz num dia.",
        min: 15,
        max: 80,
        passo: 5,
        formato: "num",
      },
      {
        caminho: ["evento", "medicos"],
        rotulo: "Médicos no evento",
        origem: "informado",
        ajuda:
          "Dois médicos atendem o dobro no mesmo evento — e é o único custo que dobra junto. " +
          "Sala e mídia são as mesmas para um ou para três. Onde a agenda aparece com asterisco, " +
          "é aqui que se ganha.",
        min: 1,
        max: 4,
        passo: 1,
        formato: "num",
      },
      {
        caminho: ["evento", "custo_medico_dia"],
        rotulo: "Cachê do médico / dia",
        origem: "calibravel",
        ajuda: "Quanto custa o dia do oftalmologista.",
        min: 0,
        max: 5000,
        passo: 100,
        formato: "reais",
      },
      {
        caminho: ["evento", "custo_estrutura_dia"],
        rotulo: "Estrutura e equipe / dia",
        origem: "calibravel",
        ajuda: "Espaço, montagem, equipe local.",
        min: 0,
        max: 3000,
        passo: 100,
        formato: "reais",
      },
      {
        caminho: ["evento", "investimento_midia"],
        rotulo: "Mídia por cidade",
        origem: "informado",
        ajuda: "Verba de divulgação. Puxa o alcance para cima.",
        min: 0,
        max: 15000,
        passo: 250,
        formato: "reais",
      },
    ],
  },
  {
    titulo: "Quantos aparecem",
    nota: "Aqui moram os maiores chutes. Corrigem-se sozinhos depois do primeiro evento registrado.",
    campos: [
      {
        caminho: ["captacao", "alcance_por_mil_reais"],
        rotulo: "Alcance por R$ 1.000",
        origem: "calibravel",
        ajuda: "Fração do público que fica sabendo a cada mil reais investidos.",
        min: 0,
        max: 0.4,
        passo: 0.01,
        formato: "pct",
      },
      {
        caminho: ["captacao", "taxa_agendamento"],
        rotulo: "Agendam",
        origem: "calibravel",
        ajuda: "De quem ficou sabendo E precisa de receita.",
        min: 0,
        max: 0.6,
        passo: 0.01,
        formato: "pct",
      },
      {
        caminho: ["captacao", "taxa_comparecimento"],
        rotulo: "Comparecem",
        origem: "calibravel",
        ajuda: "No-show é alto em consulta barata. Confirmação por telefone muda esse número.",
        min: 0.2,
        max: 1,
        passo: 0.02,
        formato: "pct",
      },
    ],
  },
  {
    titulo: "Quantos compram com você",
    nota: "É aqui que as óticas concorrentes, as notas e as avaliações entram na conta.",
    campos: [
      {
        caminho: ["conversao", "base"],
        rotulo: "Conversão sem concorrência",
        origem: "calibravel",
        ajuda: "Quanto compraria com você numa cidade sem nenhuma ótica.",
        min: 0.05,
        max: 0.9,
        passo: 0.01,
        formato: "pct",
      },
      {
        caminho: ["conversao", "peso_saturacao"],
        rotulo: "Efeito da quantidade de óticas",
        origem: "calibravel",
        ajuda: "Quanto a saturação do mercado derruba a conversão.",
        min: 0,
        max: 0.8,
        passo: 0.05,
        formato: "pct",
      },
      {
        caminho: ["conversao", "peso_reputacao"],
        rotulo: "Efeito da nota das óticas",
        origem: "calibravel",
        ajuda: "Concorrente bem avaliado segura o cliente; nota baixa é oportunidade.",
        min: 0,
        max: 0.8,
        passo: 0.05,
        formato: "pct",
      },
      {
        caminho: ["conversao", "peso_presenca"],
        rotulo: "Efeito do volume de avaliações",
        origem: "calibravel",
        ajuda: "Muitas avaliações indicam mercado ótico ativo de verdade.",
        min: 0,
        max: 0.8,
        passo: 0.05,
        formato: "pct",
      },
    ],
  },
  {
    titulo: "Quanta gente precisa",
    nota: "Constantes clínicas e demográficas. Mexer aqui só com motivo.",
    campos: [
      {
        caminho: ["demanda", "prevalencia_40mais"],
        rotulo: "Precisa de correção (40+)",
        origem: "estimado",
        ajuda: "Presbiopia é quase universal depois dos 45.",
        min: 0.3,
        max: 1,
        passo: 0.05,
        formato: "pct",
      },
      {
        caminho: ["demanda", "renovacao_anual"],
        rotulo: "Renova receita por ano",
        origem: "estimado",
        ajuda: "0,22 equivale a trocar de óculos a cada ~4,5 anos.",
        min: 0.05,
        max: 0.6,
        passo: 0.01,
        formato: "pct",
      },
      {
        caminho: ["demanda", "backlog_anos"],
        rotulo: "Anos de fila acumulada",
        origem: "calibravel",
        ajuda: "Um primeiro evento pega quem está há anos sem consultar, não só o ano corrente.",
        min: 0.5,
        max: 8,
        passo: 0.5,
        formato: "num",
      },
      {
        caminho: ["demanda", "atrito_saturacao_km"],
        rotulo: "Distância que impede viajar",
        origem: "estimado",
        ajuda: "A partir daqui, praticamente ninguém vai ao polo por rotina.",
        min: 20,
        max: 400,
        passo: 10,
        formato: "num",
      },
    ],
  },
];

const COR_ORIGEM: Record<Origem, string> = {
  informado: "pilula-ok",
  estimado: "pilula",
  calibravel: "pilula-atencao",
};

const LEGENDA_ORIGEM: Record<Origem, string> = {
  informado: "veio da sua operação",
  estimado: "constante com base defensável",
  calibravel: "chute inicial — move o tamanho, não a ordem",
};

interface Props {
  negocioBase: Negocio;
  negocio: Negocio;
  municipios: Municipio[];
  onMudar: (n: Negocio) => void;
  onRestaurar: () => void;
}

/** A chave aceita um nível de aninhamento ("custo_par.custo_baixo"). */
function lerValor(n: Negocio, [grupo, chave]: [keyof Negocio, string]): number {
  const bloco = (n[grupo] ?? {}) as Record<string, unknown>;
  const [primeira, segunda] = chave.split(".");
  if (segunda === undefined) return (bloco[primeira] as number) ?? 0;
  const interno = (bloco[primeira] ?? {}) as Record<string, number>;
  return interno[segunda] ?? 0;
}

function comValor(n: Negocio, [grupo, chave]: [keyof Negocio, string], valor: number): Negocio {
  const bloco = (n[grupo] ?? {}) as Record<string, unknown>;
  const [primeira, segunda] = chave.split(".");
  if (segunda === undefined) return { ...n, [grupo]: { ...bloco, [primeira]: valor } };
  const interno = (bloco[primeira] ?? {}) as Record<string, number>;
  return { ...n, [grupo]: { ...bloco, [primeira]: { ...interno, [segunda]: valor } } };
}

function formatar(valor: number, formato: Campo["formato"]): string {
  if (formato === "reais") return moeda(valor);
  if (formato === "pct") return pct(valor);
  return num(valor, valor % 1 === 0 ? 0 : 2);
}

export default function PainelNegocio({
  negocioBase,
  negocio,
  municipios,
  onMudar,
  onRestaurar,
}: Props) {
  const [quantidade, setQuantidade] = useState(20);

  const divergencia = useMemo(
    () => conferirProjecaoComPipeline(municipios, negocioBase),
    [municipios, negocioBase],
  );

  const novo = useMemo(
    () => reposicionar(ordenarPor(projetar(municipios, negocio), "lucro_estimado")),
    [municipios, negocio],
  );
  const base = useMemo(
    () => reposicionar(ordenarPor(projetar(municipios, negocioBase), "lucro_estimado")),
    [municipios, negocioBase],
  );
  const posicaoBase = useMemo(() => new Map(base.map((m) => [m.codigo_ibge, m.posicao])), [base]);
  const lucroBase = useMemo(
    () => new Map(base.map((m) => [m.codigo_ibge, m.lucro_estimado])),
    [base],
  );

  const resumo = useMemo(() => {
    const viaveis = novo.filter((m) => (m.lucro_estimado ?? 0) > 0);
    const somaTop = novo.slice(0, 10).reduce((a, m) => a + (m.lucro_estimado ?? 0), 0);
    return { viaveis: viaveis.length, total: novo.length, somaTop };
  }, [novo]);

  const ticketMedio = negocio.venda?.ticket_medio ?? 0;
  const margem = margemPorPar(ticketMedio, negocio.venda ?? {});
  const margemPct = ticketMedio ? margem / ticketMedio : 0;
  const margemPiso = margemPorPar(negocio.venda?.ticket_min ?? 0, negocio.venda ?? {});
  const margemTeto = margemPorPar(negocio.venda?.ticket_max ?? 0, negocio.venda ?? {});

  return (
    <div className="tela-pesos">
      <div className="pesos-grade">
        <div className="cartao">
          <h3>Parâmetros do negócio</h3>
          <p style={{ color: "var(--txt-2)", fontSize: 12, marginTop: 0 }}>
            Mexa e o ranking de faturamento se refaz na hora. No ticket médio sobra{" "}
            <b className="dados">{moeda(margem)}</b> por par ({pct(margemPct)} do preço) — de{" "}
            <b className="dados">{moeda(margemPiso)}</b> no par mais barato a{" "}
            <b className="dados">{moeda(margemTeto)}</b> no mais caro.
          </p>

          {GRUPOS.map((g) => (
            <div key={g.titulo} className="grupo-negocio">
              <h4>{g.titulo}</h4>
              <p className="slider-ajuda" style={{ marginTop: 0, marginBottom: 10 }}>{g.nota}</p>
              {g.campos.map((c) => {
                const valor = lerValor(negocio, c.caminho);
                const id = `n-${c.caminho.join("-")}`;
                return (
                  <div key={id} className="slider-linha">
                    <div className="slider-linha-topo">
                      <label htmlFor={id}>
                        {c.rotulo}
                        <span
                          className={`pilula ${COR_ORIGEM[c.origem]} pilula-mini`}
                          title={LEGENDA_ORIGEM[c.origem]}
                        >
                          {c.origem}
                        </span>
                      </label>
                      <span className="num dados">{formatar(valor, c.formato)}</span>
                    </div>
                    <input
                      id={id}
                      type="range"
                      min={c.min}
                      max={c.max}
                      step={c.passo}
                      value={valor}
                      onChange={(e) => onMudar(comValor(negocio, c.caminho, Number(e.target.value)))}
                    />
                    <div className="slider-ajuda">{c.ajuda}</div>
                  </div>
                );
              })}
            </div>
          ))}

          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            <button className="btn" onClick={onRestaurar}>
              Restaurar parâmetros do pipeline
            </button>
            <button
              className="btn btn-sutil"
              onClick={() => navigator.clipboard?.writeText(gerarYaml(negocio))}
              title="Copia o trecho de negocio.yaml para colar no pipeline"
            >
              Copiar como negocio.yaml
            </button>
          </div>
          <p style={{ color: "var(--txt-3)", fontSize: 11, marginBottom: 0 }}>
            O ajuste aqui vive só neste navegador. Para valer no pipeline, cole em{" "}
            <code>pipeline/config/negocio.yaml</code> e rode <code>mapa-optico score</code>.
          </p>
        </div>

        <div className="cartao">
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
            <h3 style={{ margin: 0 }}>Lucro: parâmetros novos × pipeline</h3>
            <span
              className={`pilula ${divergencia <= 1 ? "pilula-ok" : "pilula-alerta"}`}
              title="Diferença máxima de faturamento entre o modelo do navegador e o do pipeline"
            >
              conferência: {divergencia <= 1 ? "confere" : `divergência de ${moeda(divergencia)}`}
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

          <div className="resumo-negocio">
            <div>
              <span className="rotulo-mini">municípios viáveis</span>
              <b className="dados">
                {resumo.viaveis}
                <small> / {resumo.total}</small>
              </b>
            </div>
            <div>
              <span className="rotulo-mini">lucro somado do top 10</span>
              <b className="dados">{moedaCurta(resumo.somaTop)}</b>
            </div>
          </div>

          <div style={{ overflow: "auto", maxHeight: "56vh" }}>
            <table className="comparacao dados">
              <thead>
                <tr>
                  <th>#</th>
                  <th className="esq">Município</th>
                  <th>Lucro novo</th>
                  <th>Lucro atual</th>
                  <th>Δ</th>
                  <th>Antes</th>
                  <th>Δ pos</th>
                </tr>
              </thead>
              <tbody>
                {novo.slice(0, quantidade).map((m) => {
                  const antes = posicaoBase.get(m.codigo_ibge);
                  const lucroAntes = lucroBase.get(m.codigo_ibge) ?? null;
                  const deltaPos = antes !== undefined ? antes - m.posicao : null;
                  const delta =
                    lucroAntes !== null && m.lucro_estimado !== null
                      ? m.lucro_estimado - lucroAntes
                      : null;
                  const classe =
                    deltaPos === null || deltaPos === 0 ? "igual" : deltaPos > 0 ? "subiu" : "caiu";
                  return (
                    <tr key={m.codigo_ibge}>
                      <td>{m.posicao}</td>
                      <td className="esq" style={{ fontFamily: "var(--fonte-ui)" }}>
                        {m.nome}
                      </td>
                      <td className={(m.lucro_estimado ?? 0) > 0 ? "bom" : "ruim"}>
                        {moedaCurta(m.lucro_estimado)}
                      </td>
                      <td style={{ color: "var(--txt-3)" }}>{moedaCurta(lucroAntes)}</td>
                      <td className={delta === null ? "igual" : delta >= 0 ? "subiu" : "caiu"}>
                        {delta === null ? "—" : `${delta >= 0 ? "+" : ""}${moedaCurta(delta)}`}
                      </td>
                      <td style={{ color: "var(--txt-3)" }}>{antes ?? "—"}</td>
                      <td className={classe}>
                        {deltaPos === null
                          ? "—"
                          : deltaPos === 0
                            ? "="
                            : deltaPos > 0
                              ? `▲ ${deltaPos}`
                              : `▼ ${-deltaPos}`}
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

function gerarYaml(n: Negocio): string {
  const linhas: string[] = [`versao: "${n.versao ?? "n1"}"`, ""];
  (["venda", "evento", "demanda", "captacao", "conversao"] as const).forEach((grupo) => {
    const bloco = n[grupo] as Record<string, unknown> | undefined;
    if (!bloco) return;
    linhas.push(`${grupo}:`);
    Object.entries(bloco).forEach(([chave, valor]) => linhas.push(`  ${chave}: ${valor}`));
    linhas.push("");
  });
  return linhas.join("\n");
}
