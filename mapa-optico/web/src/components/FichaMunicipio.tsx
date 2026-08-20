/**
 * Ficha do município.
 *
 * O bloco mais importante é o breakdown do score: o usuário precisa entender —
 * e poder discordar — de por que a cidade pontuou o que pontuou. Score sem
 * componente é caixa preta, e caixa preta não sustenta decisão comercial.
 */
import { useEffect, useMemo, useState } from "react";
import type { Componente, Municipio, Otica } from "../lib/types";
import { km, moeda, num, VAZIO } from "../lib/format";
import { ROTULO_FATOR } from "../lib/score";
import { lerNotasLocais, salvarNota, temSupabase } from "../lib/data";
import { CORES } from "./MapaChoropleth";

const COR_FATOR: Record<string, string> = {
  distancia_polo: CORES[4],
  ausencia_oftalmo: CORES[3],
  populacao_40mais: CORES[2],
  concorrencia_oticas: CORES[1],
  renda: CORES[0],
};

const EXPLICACAO: Record<string, string> = {
  distancia_polo: "Quanto o morador precisa se deslocar para conseguir uma receita.",
  ausencia_oftalmo: "Oferta local, ponderada por carga horária (40h = 1 oftalmologista equivalente).",
  populacao_40mais: "Mercado endereçável real: presbiopia começa nessa faixa.",
  concorrencia_oticas: "Óticas já instaladas disputando o mesmo comprador.",
  renda: "Faixa ótima: abaixo cai o ticket, acima o cliente compra na cidade grande.",
};

interface Props {
  municipio: Municipio;
  oticas: Otica[];
  vizinhosProximos: { nome: string; km: number }[];
  onFechar: () => void;
}

export default function FichaMunicipio({ municipio: m, oticas, vizinhosProximos, onFechar }: Props) {
  const [nota, setNota] = useState("");
  const [fila, setFila] = useState<string>("");
  const [salvo, setSalvo] = useState(false);

  useEffect(() => {
    const existente = lerNotasLocais()[m.codigo_ibge];
    setNota(existente?.texto ?? "");
    setFila(existente?.fila_sus_dias != null ? String(existente.fila_sus_dias) : "");
    setSalvo(false);
  }, [m.codigo_ibge]);

  const fatores = useMemo(
    () =>
      (Object.entries(m.componentes ?? {}) as [string, Componente][])
        .filter(([chave]) => chave !== "_meta")
        .map(([chave, c]) => ({ chave, ...c }))
        .sort((a, b) => (b.contribuicao ?? 0) - (a.contribuicao ?? 0)),
    [m],
  );

  const ausentes = fatores.filter((f) => !f.disponivel);

  const gravar = async () => {
    await salvarNota({
      codigo_ibge: m.codigo_ibge,
      texto: nota,
      fila_sus_dias: fila === "" ? null : Number(fila),
      criado_em: new Date().toISOString(),
    });
    setSalvo(true);
  };

  return (
    <aside className="ficha" aria-label={`Ficha de ${m.nome}`}>
      <div className="ficha-topo">
        <div style={{ flex: 1 }}>
          <h2>{m.nome}</h2>
          <div className="sub dados">
            {m.uf} · {m.codigo_ibge} · #{m.posicao} no ranking
            {m.circuito !== null && m.circuito >= 0 ? ` · circuito ${m.circuito}` : ""}
          </div>
        </div>
        <button className="btn btn-sutil" onClick={onFechar} aria-label="Fechar ficha">
          ✕
        </button>
      </div>

      <div className="ficha-corpo">
        <section className="secao">
          <h3>Score {num(m.score_total, 1)} · confiança {num(m.confianca, 2)}</h3>
          <div className="trilho" style={{ height: 12 }}>
            {fatores
              .filter((f) => f.disponivel)
              .map((f) => (
                <i
                  key={f.chave}
                  style={{
                    width: `${f.contribuicao}%`,
                    background: COR_FATOR[f.chave] ?? CORES[2],
                  }}
                  title={`${ROTULO_FATOR[f.chave] ?? f.chave}: ${num(f.contribuicao, 1)} pontos`}
                />
              ))}
          </div>
          <div className="barra-legenda">
            A barra soma exatamente o score: cada faixa é a contribuição de um fator.
          </div>
        </section>

        <section className="secao">
          <h3>Como esse score se formou</h3>
          {fatores.map((f) => (
            <div key={f.chave} className={`barra-fator${f.disponivel ? "" : " fator-indisponivel"}`}>
              <div className="barra-fator-topo">
                <b>{ROTULO_FATOR[f.chave] ?? f.chave}</b>
                <span className="num dados">
                  {f.disponivel ? (
                    <>
                      {num(f.contribuicao, 1)} pts · peso {num(f.peso_efetivo ?? f.peso, 0)}%
                    </>
                  ) : (
                    <span className="selo-indisponivel">sem dado</span>
                  )}
                </span>
              </div>
              <div className="trilho">
                <i
                  style={{
                    width: `${f.normalizado ?? 0}%`,
                    background: f.disponivel ? (COR_FATOR[f.chave] ?? CORES[2]) : "var(--linha-forte)",
                  }}
                />
              </div>
              <div className="barra-legenda">
                {f.disponivel
                  ? `${EXPLICACAO[f.chave] ?? ""} Valor: ${num(f.valor_bruto, 1)} → nota ${num(f.normalizado, 0)}/100.`
                  : "Fonte indisponível para este município — o fator saiu da conta e a confiança caiu."}
              </div>
            </div>
          ))}
          {ausentes.length > 0 && (
            <div className="pilula pilula-alerta" style={{ marginTop: 6 }}>
              {ausentes.length} fator(es) sem dado — score calculado só com o que existe
            </div>
          )}
        </section>

        <section className="secao">
          <h3>Dados do município</h3>
          <dl className="grade-kv">
            <dt>População total</dt>
            <dd>{num(m.populacao_total)}</dd>
            <dt>População 40+</dt>
            <dd>{num(m.populacao_40mais)}</dd>
            <dt>Renda</dt>
            <dd>{moeda(m.renda_mediana)}</dd>
            <dt>Área</dt>
            <dd>{m.area_km2 === null ? VAZIO : `${num(m.area_km2)} km²`}</dd>
            <dt>Oftalmologistas (CNES)</dt>
            <dd>{m.qtd_oftalmologistas === null ? VAZIO : num(m.qtd_oftalmologistas)}</dd>
            <dt>Equivalente 40h</dt>
            <dd>{num(m.oftalmo_equivalente, 2)}</dd>
            <dt>Competência CNES</dt>
            <dd>{m.competencia_cnes ?? VAZIO}</dd>
            <dt>Microrregião</dt>
            <dd style={{ fontFamily: "var(--fonte-ui)" }}>{m.microrregiao ?? VAZIO}</dd>
          </dl>
        </section>

        <section className="secao">
          <h3>Acesso ao polo</h3>
          {m.distancia_km === null ? (
            <p style={{ margin: 0, color: "var(--txt-2)" }}>
              Sem cálculo de distância. Rode o pipeline com o OSRM disponível.
            </p>
          ) : (
            <dl className="grade-kv">
              <dt>Polo mais próximo</dt>
              <dd style={{ fontFamily: "var(--fonte-ui)" }}>{m.polo_nome ?? VAZIO}</dd>
              <dt>Distância rodoviária</dt>
              <dd>{km(m.distancia_km)}</dd>
              <dt>Tempo estimado</dt>
              <dd>{m.tempo_minutos === null ? VAZIO : `${num(m.tempo_minutos)} min`}</dd>
            </dl>
          )}
        </section>

        {vizinhosProximos.length > 0 && (
          <section className="secao">
            <h3>Canibalização</h3>
            <p style={{ margin: "0 0 6px", color: "var(--txt-2)" }}>
              Municípios do topo perto demais — provavelmente um circuito único, não dois eventos:
            </p>
            <ul className="lista-oticas">
              {vizinhosProximos.map((v) => (
                <li key={v.nome}>
                  <span>{v.nome}</span>
                  <span className="dados">{km(v.km)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="secao">
          <h3>Óticas encontradas ({m.qtd_oticas === null ? VAZIO : num(m.qtd_oticas)})</h3>
          {m.qtd_oticas === null ? (
            <p style={{ margin: 0, color: "var(--txt-2)" }}>
              Google Places não foi consultado para este município. Ausência de consulta não é
              ausência de ótica.
            </p>
          ) : oticas.length === 0 ? (
            <p style={{ margin: 0, color: "var(--txt-2)" }}>
              Nenhuma ótica retornada na busca — vale confirmar em campo antes de tratar como zero.
            </p>
          ) : (
            <ul className="lista-oticas">
              {oticas.map((o) => (
                <li key={o.place_id}>
                  <span>{o.nome}</span>
                  <span className="dados">
                    {o.rating === null ? VAZIO : `★ ${num(o.rating, 1)}`}
                    {o.total_ratings ? ` (${num(o.total_ratings)})` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="secao">
          <h3>Validação de campo</h3>
          <label className="campo" style={{ marginBottom: 8 }}>
            <span style={{ fontSize: 10, textTransform: "uppercase", color: "var(--txt-3)" }}>
              Fila do SUS (dias) — preenchimento manual
            </span>
            <input
              type="number"
              className="dados"
              value={fila}
              placeholder="ex.: 240"
              onChange={(e) => {
                setFila(e.target.value);
                setSalvo(false);
              }}
            />
          </label>
          <textarea
            className="nota"
            value={nota}
            placeholder="Telefonema para a secretaria de saúde, conversa com ótica local, o que for apurado…"
            onChange={(e) => {
              setNota(e.target.value);
              setSalvo(false);
            }}
          />
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
            <button className="btn" onClick={gravar}>
              Salvar nota
            </button>
            {salvo && (
              <span className="pilula pilula-ok">
                salvo {temSupabase ? "no Supabase" : "neste navegador"}
              </span>
            )}
            <button className="btn btn-sutil" disabled title="Fase 2 do plano de execução">
              Registrar evento
            </button>
          </div>
        </section>
      </div>
    </aside>
  );
}
