/**
 * Tela de sincronização.
 *
 * O que ela resolve: hoje atualizar os dados exige terminal, Python e um
 * comando. Aqui é uma tela que diz o que está velho e um botão que atualiza.
 *
 * Três regras que organizam o desenho:
 *
 * 1. NUNCA GASTAR SEM MOSTRAR A CONTA. O Google Places é a única fonte que
 *    cobra. A estimativa aparece antes, com o número de consultas, e o disparo
 *    exige uma confirmação separada.
 * 2. CADA FONTE ENVELHECE NO SEU RITMO. O CNES publica competência mensal; o
 *    Censo dura anos. Uma barra de "atualizado em" só para o conjunto esconderia
 *    exatamente a fonte que precisa de atenção.
 * 3. FALTA DE CONFIGURAÇÃO NÃO É ERRO. Sem o token do GitHub a tela explica o
 *    que falta e quem resolve, em vez de mostrar um botão que não funciona.
 */
import { useCallback, useEffect, useState } from "react";
import {
  dispararSincronizacao,
  estadoDasFontes,
  estimarCustoPlaces,
  lerEstado,
  ROTULO_SITUACAO,
  tempoRelativo,
  type EstadoFonte,
  type Execucao,
  type RespostaEstado,
  type Situacao,
} from "../lib/sincronizar";
import type { Snapshot } from "../lib/types";
import { dataHora, num } from "../lib/format";

const CLASSE_SITUACAO: Record<Situacao, string> = {
  atual: "pilula-ok",
  envelhecendo: "pilula-atencao",
  refazer: "pilula-alerta",
  indisponivel: "pilula-alerta",
  demo: "pilula-alerta",
};

interface Props {
  snapshot: Snapshot;
}

export default function PainelSincronizacao({ snapshot }: Props) {
  const [estado, setEstado] = useState<RespostaEstado | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [comPlaces, setComPlaces] = useState(false);
  const [comOsrm, setComOsrm] = useState(true);
  const [refresh, setRefresh] = useState(false);
  const [confirmandoCusto, setConfirmandoCusto] = useState(false);
  const [disparando, setDisparando] = useState(false);
  const [recado, setRecado] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);

  const fontes: EstadoFonte[] = estadoDasFontes(snapshot.proveniencia?.detalhes);
  const ufs = Array.from(new Set(snapshot.municipios.map((m) => m.uf).filter(Boolean)));
  const custo = estimarCustoPlaces(snapshot.municipios.length, snapshot.fontes_config?.places);
  const emAndamento = estado?.execucoes?.find(
    (e) => e.estado === "queued" || e.estado === "in_progress",
  );

  const atualizar = useCallback(async () => {
    setEstado(await lerEstado());
    setCarregando(false);
  }, []);

  useEffect(() => {
    void atualizar();
  }, [atualizar]);

  // Enquanto o robô roda, a tela acompanha sozinha. Parado, não fica batendo.
  useEffect(() => {
    if (!emAndamento) return;
    const id = setInterval(() => void atualizar(), 15_000);
    return () => clearInterval(id);
  }, [emAndamento, atualizar]);

  const disparar = async () => {
    setDisparando(true);
    setRecado(null);
    const r = await dispararSincronizacao({
      ufs: ufs.join(",") || "SC",
      com_places: comPlaces,
      com_osrm: comOsrm,
      refresh,
    });
    setDisparando(false);
    setConfirmandoCusto(false);
    if (r.ok) {
      setRecado({
        tipo: "ok",
        texto:
          "Sincronização iniciada. Leva alguns minutos; esta tela acompanha sozinha e os dados " +
          "novos aparecem no próximo carregamento.",
      });
      setTimeout(() => void atualizar(), 4000);
    } else {
      setRecado({ tipo: "erro", texto: r.erro ?? "não deu para disparar" });
    }
  };

  const pedirSincronizacao = () => {
    if (comPlaces && custo) setConfirmandoCusto(true);
    else void disparar();
  };

  return (
    <div className="tela-pesos">
      <div className="pesos-grade">
        <div className="cartao">
          <h3>Estado das fontes</h3>
          <p className="slider-ajuda" style={{ marginTop: 0 }}>
            Cada fonte envelhece no seu ritmo. O CNES publica uma competência por mês; o Censo dura
            anos. Snapshot atual gerado em {dataHora(snapshot.gerado_em)}.
          </p>

          <div className="lista-fontes">
            {fontes.map(({ fonte, situacao, atualizadoEm, motivo }) => (
              <div key={fonte.chave} className="linha-fonte">
                <div>
                  <b>{fonte.rotulo}</b>
                  <small className="dados"> · {fonte.origem}</small>
                  <div className="slider-ajuda">{fonte.explicacao}</div>
                  {motivo && <div className="slider-ajuda erro-fonte">{motivo}</div>}
                </div>
                <span className="dados quando-fonte">{tempoRelativo(atualizadoEm)}</span>
                <span className={`pilula ${CLASSE_SITUACAO[situacao]}`}>
                  {ROTULO_SITUACAO[situacao]}
                  {fonte.custa ? " · custa" : ""}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="cartao">
          <h3>Sincronizar tudo</h3>

          {carregando ? (
            <p className="slider-ajuda">verificando…</p>
          ) : !estado?.configurado ? (
            <div className="pilula pilula-alerta" style={{ display: "block", padding: "10px 12px" }}>
              <b>Botão ainda não configurado.</b>
              <div style={{ marginTop: 6, fontWeight: 400, lineHeight: 1.5 }}>
                {estado?.motivo ?? estado?.erro}
              </div>
            </div>
          ) : (
            <>
              <div className="opcoes-sync">
                <label>
                  <input
                    type="checkbox"
                    checked={comPlaces}
                    onChange={(e) => setComPlaces(e.target.checked)}
                  />
                  <span>
                    <b>Atualizar óticas concorrentes</b>
                    <small>
                      {custo
                        ? ` custa cerca de US$ ${custo.usd.toFixed(2)} (${num(custo.chamadas)} consultas)`
                        : " única fonte que cobra"}
                    </small>
                  </span>
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={comOsrm}
                    onChange={(e) => setComOsrm(e.target.checked)}
                  />
                  <span>
                    <b>Recalcular distância até o polo</b>
                    <small> gratuito, mas é a etapa mais demorada</small>
                  </span>
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={refresh}
                    onChange={(e) => setRefresh(e.target.checked)}
                  />
                  <span>
                    <b>Ignorar o que já está guardado</b>
                    <small> busca tudo de novo, mesmo o que não mudou</small>
                  </span>
                </label>
              </div>

              <p className="slider-ajuda">
                Vai sincronizar {ufs.join(", ") || "SC"} · {num(snapshot.municipios.length)}{" "}
                municípios.
              </p>

              {confirmandoCusto && custo ? (
                <div className="confirma-custo">
                  <b>Confirma o gasto?</b>
                  <p>
                    Vão ser {num(custo.chamadas)} consultas ao Google Places, a US${" "}
                    {custo.porChamada.toFixed(3)} cada — cerca de{" "}
                    <b className="dados">US$ {custo.usd.toFixed(2)}</b>. Cidades já consultadas antes
                    não entram de novo, então a conta real tende a ser menor.
                  </p>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="btn btn-acento" onClick={() => void disparar()} disabled={disparando}>
                      {disparando ? "disparando…" : "Confirmar e sincronizar"}
                    </button>
                    <button className="btn btn-sutil" onClick={() => setConfirmandoCusto(false)}>
                      Cancelar
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  className="btn btn-acento"
                  onClick={pedirSincronizacao}
                  disabled={disparando || Boolean(emAndamento)}
                >
                  {emAndamento ? "sincronização em andamento…" : disparando ? "disparando…" : "Sincronizar"}
                </button>
              )}

              {recado && (
                <div
                  className={`pilula ${recado.tipo === "ok" ? "pilula-ok" : "pilula-alerta"}`}
                  style={{ display: "block", marginTop: 10, padding: "8px 12px", fontWeight: 400 }}
                >
                  {recado.texto}
                </div>
              )}

              <h3 style={{ marginTop: 20 }}>Execuções recentes</h3>
              {estado.execucoes?.length ? (
                <div className="lista-fontes">
                  {estado.execucoes.map((e: Execucao) => (
                    <div key={e.id} className="linha-fonte">
                      <div>
                        <b>{dataHora(e.criado_em)}</b>
                        <div className="slider-ajuda">
                          <a href={e.url} target="_blank" rel="noreferrer">
                            ver o log completo no GitHub
                          </a>
                        </div>
                      </div>
                      <span />
                      <span
                        className={`pilula ${
                          e.resultado === "success"
                            ? "pilula-ok"
                            : e.resultado === null
                              ? "pilula-atencao"
                              : "pilula-alerta"
                        }`}
                      >
                        {e.resultado ?? e.estado}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="slider-ajuda">Nenhuma execução ainda.</p>
              )}
            </>
          )}

          <p className="slider-ajuda" style={{ marginTop: 16 }}>
            O botão aciona o robô do GitHub, que roda o pipeline e grava os dados. Você não precisa
            deixar nada ligado. Além disso ele roda sozinho todo dia 5, quando o CNES publica a
            competência nova.
          </p>
        </div>
      </div>
    </div>
  );
}
