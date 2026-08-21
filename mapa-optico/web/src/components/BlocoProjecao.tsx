/**
 * Projeção financeira na ficha do município.
 *
 * Regra que organiza o bloco inteiro: o usuário precisa poder RECONSTRUIR o
 * número de cima a partir do que está embaixo. O potencial é o produto de três
 * fatores, e os três aparecem; o faturamento é a última linha de um funil, e o
 * funil aparece inteiro, com o valor de cada etapa.
 *
 * Se ele discordar de uma etapa, ele sabe exatamente qual parâmetro mexer — e é
 * por isso que existe a aba de parâmetros do negócio.
 */
import type { Municipio, Negocio } from "../lib/types";
import { moeda, moedaCurta, num, pct, pontos, VAZIO } from "../lib/format";
import { ROTULO_IMPUTADO } from "../lib/projecao";

interface Props {
  municipio: Municipio;
  negocio: Negocio;
}

/** Uma etapa do funil: rótulo, valor e a taxa que produziu a queda. */
function Etapa({
  nome,
  valor,
  taxa,
  largura,
  destaque,
}: {
  nome: string;
  valor: string;
  taxa?: string;
  largura: number;
  destaque?: boolean;
}) {
  return (
    <div className={`funil-etapa${destaque ? " funil-destaque" : ""}`}>
      <div className="funil-rotulo">
        <b>{nome}</b>
        {taxa && <small>{taxa}</small>}
      </div>
      <div className="funil-trilho">
        <i style={{ width: `${Math.max(1.5, largura)}%` }} />
      </div>
      <span className="funil-valor dados">{valor}</span>
    </div>
  );
}

export default function BlocoProjecao({ municipio: m, negocio }: Props) {
  const p = m.projecao;
  const diasEvento = negocio.evento?.dias ?? 3;

  if (!p || !p.disponivel) {
    const faltando = (p?.faltando ?? []).map((f) =>
      f === "cnes" ? "contagem de oftalmologistas (CNES)" : "população 40+ (IBGE)",
    );
    return (
      <section className="secao">
        <h3>Projeção financeira</h3>
        <div className="pilula pilula-alerta">sem dado suficiente para projetar</div>
        <p className="barra-legenda" style={{ marginTop: 8 }}>
          Falta {faltando.join(" e ")}. O município continua no ranking de demanda reprimida, mas
          não recebe estimativa de faturamento — preferimos deixar vazio a inventar número.
        </p>
      </section>
    );
  }

  const f = p.fatores!;
  const funil = p.funil!;
  const conc = p.concorrencia!;
  const dinheiro = p.dinheiro!;
  const imputados = p.imputados ?? [];

  // As barras do funil usam escala de raiz quadrada: sem isso as últimas etapas
  // ficam invisíveis e o funil deixa de comunicar a queda.
  const topo = Math.max(funil.populacao_40mais, 1);
  const larg = (v: number) => Math.sqrt(Math.max(v, 0) / topo) * 100;

  return (
    <>
      <section className="secao">
        <div className="projecao-cabeca">
          <div>
            <div className="rotulo-mini">Potencial de faturamento</div>
            <div className="projecao-numero dados">{pontos(m.potencial_pct, 1)}</div>
          </div>
          <div className="projecao-lucro">
            <div className="rotulo-mini">Lucro estimado</div>
            <div
              className={`projecao-numero dados ${(m.lucro_estimado ?? 0) > 0 ? "bom" : "ruim"}`}
            >
              {moedaCurta(m.lucro_estimado)}
            </div>
          </div>
        </div>

        <div className="fatores-produto">
          {[
            {
              nome: "Ocupação da agenda",
              valor: f.ocupacao_agenda,
              vem: "médicos locais, distância ao polo e população",
            },
            {
              nome: "Força da conversão",
              valor: f.forca_conversao,
              vem: "óticas concorrentes, suas notas e avaliações",
            },
            { nome: "Nível do ticket", valor: f.nivel_ticket, vem: "renda da cidade" },
          ].map((x) => (
            <div key={x.nome} className="fator-mult" title={`Vem de: ${x.vem}`}>
              <div className="barra-fator-topo">
                <b>{x.nome}</b>
                <span className="num dados">{pct(x.valor)}</span>
              </div>
              <div className="trilho">
                <i style={{ width: `${(x.valor ?? 0) * 100}%` }} />
              </div>
              <div className="barra-legenda">vem de {x.vem}</div>
            </div>
          ))}
        </div>
        <div className="barra-legenda identidade dados">
          {pct(f.ocupacao_agenda)} × {pct(f.forca_conversao)} × {pct(f.nivel_ticket)} ={" "}
          {pontos(m.potencial_pct, 1)} do teto de {moedaCurta(p.teto_faturamento)}
        </div>

        {imputados.length > 0 && (
          <div className="pilula pilula-alerta" style={{ marginTop: 10 }}>
            projeção usa estimativa para: {imputados.map((i) => ROTULO_IMPUTADO[i] ?? i).join(", ")}
          </div>
        )}
      </section>

      <section className="secao">
        <h3>De habitante a consulta</h3>
        <div className="funil">
          <Etapa
            nome="População 40+"
            valor={num(funil.populacao_40mais)}
            taxa="mercado endereçável"
            largura={100}
          />
          <Etapa
            nome="Precisam de receita por ano"
            valor={num(funil.demanda_anual)}
            taxa="prevalência × renovação"
            largura={larg(funil.demanda_anual)}
          />
          <Etapa
            nome="Sobra sem atendimento local"
            valor={num(funil.demanda_nao_atendida)}
            taxa={`capacidade dos oftalmos locais: ${num(funil.capacidade_local_ano)}/ano`}
            largura={larg(funil.demanda_nao_atendida)}
          />
          <Etapa
            nome="Não resolvem viajando"
            valor={num(funil.demanda_represada)}
            taxa={`atrito de deslocamento ${pct(funil.atrito_deslocamento)}`}
            largura={larg(funil.demanda_represada)}
          />
          <Etapa
            nome="Fila acumulada alcançável"
            valor={num(funil.publico_evento)}
            taxa={`${num(funil.backlog_anos, 1)} anos de demanda represada`}
            largura={larg(funil.publico_evento)}
          />
          <Etapa
            nome="Ficam sabendo"
            valor={num(funil.alcancados)}
            taxa={`alcance da mídia ${pct(funil.alcance_midia)}`}
            largura={larg(funil.alcancados)}
          />
          <Etapa
            nome="Agendam"
            valor={num(funil.agendamentos)}
            largura={larg(funil.agendamentos)}
          />
          <Etapa
            nome="Comparecem"
            valor={num(funil.comparecimentos)}
            largura={larg(funil.comparecimentos)}
          />
          <Etapa
            nome="Consultas no evento"
            valor={num(funil.consultas)}
            taxa={`agenda de ${num(funil.capacidade_evento)} vagas`}
            largura={larg(funil.consultas)}
            destaque
          />
        </div>
        {funil.limitado_pela_agenda && (
          <div className="pilula pilula-atencao" style={{ marginTop: 8 }}>
            agenda cheia — sobram {num(funil.demanda_nao_capturada)} pessoas. A procura daria para{" "}
            {funil.dias_sugeridos} dias de evento, não {diasEvento}.
          </div>
        )}
        <p className="barra-legenda" style={{ marginTop: 8 }}>
          As barras usam escala comprimida para as últimas etapas continuarem visíveis. Os números à
          direita são exatos.
        </p>
      </section>

      <section className="secao">
        <h3>Quanto disso compra com a gente</h3>
        <div className="conversao-cabeca">
          <span className="rotulo-mini">conversão estimada</span>
          <span className="projecao-numero-menor dados">{pct(conc.conversao)}</span>
        </div>
        <dl className="grade-kv">
          <dt title="Óticas por 10 mil habitantes">Saturação</dt>
          <dd>
            {conc.saturacao.valor === null ? VAZIO : `${num(conc.saturacao.valor, 1)}/10 mil hab`}
            <small className="efeito">{conc.saturacao.fator > 0 ? ` −${pct(conc.saturacao.fator)} do peso` : " sem efeito"}</small>
          </dd>
          <dt title="Nota média ponderada pelas avaliações. Concorrente fraco não é ameaça.">
            Nota da concorrência
          </dt>
          <dd>
            {conc.reputacao.valor === null ? VAZIO : num(conc.reputacao.valor, 1)}
            <small className="efeito">
              {conc.reputacao.valor === null
                ? ""
                : conc.reputacao.fator < 0.35
                  ? " concorrente fraco — oportunidade"
                  : conc.reputacao.fator > 0.7
                    ? " concorrente forte"
                    : " concorrência mediana"}
            </small>
          </dd>
          <dt title="Total de avaliações por mil habitantes: proxy de quanto comércio ótico a cidade movimenta">
            Movimento do mercado
          </dt>
          <dd>
            {conc.presenca.valor === null ? VAZIO : `${num(conc.presenca.valor, 1)}/mil hab`}
            <small className="efeito">
              {m.oticas_avaliacoes === null ? "" : ` ${num(m.oticas_avaliacoes)} avaliações no total`}
            </small>
          </dd>
        </dl>
      </section>

      <section className="secao">
        <h3>A conta</h3>
        <div className="conta">
          <span>
            {num(dinheiro.vendas)} pares × {moeda(dinheiro.ticket)}
          </span>
          <span className="dados">{moeda(dinheiro.faturamento)}</span>

          <span className="negativo">
            − lentes e armações ({moeda(dinheiro.custo_por_par)} por par ={" "}
            {pct(dinheiro.cmv_fracao)} deste ticket)
          </span>
          <span className="dados negativo">− {moeda(dinheiro.faturamento - dinheiro.margem_bruta)}</span>

          <span className="negativo">− médico ({diasEvento} dias)</span>
          <span className="dados negativo">− {moeda(dinheiro.custos.medico)}</span>

          <span className="negativo">− estrutura e equipe</span>
          <span className="dados negativo">− {moeda(dinheiro.custos.estrutura)}</span>

          <span className="negativo">− deslocamento (rateado no circuito)</span>
          <span className="dados negativo">− {moeda(dinheiro.custos.deslocamento)}</span>

          <span className="negativo">− mídia local</span>
          <span className="dados negativo">− {moeda(dinheiro.custos.midia)}</span>

          <span className="total">Lucro estimado</span>
          <span className={`dados total ${dinheiro.lucro > 0 ? "bom" : "ruim"}`}>
            {moeda(dinheiro.lucro)}
          </span>
        </div>
        <dl className="grade-kv" style={{ marginTop: 10 }}>
          <dt>Retorno sobre o custo</dt>
          <dd>{m.retorno_sobre_custo === null ? VAZIO : pct(m.retorno_sobre_custo)}</dd>
          <dt title="O que sobra em cada par depois do fornecedor">Margem por par</dt>
          <dd>
            {moeda(dinheiro.margem_por_par)}
            <small className="efeito"> {pct(1 - dinheiro.cmv_fracao)} do ticket</small>
          </dd>
          <dt title="Quantos pares pagam o evento inteiro">Ponto de equilíbrio</dt>
          <dd>
            {dinheiro.ponto_equilibrio_vendas === null
              ? VAZIO
              : `${num(dinheiro.ponto_equilibrio_vendas)} pares`}
          </dd>
          <dt>Confiança da projeção</dt>
          <dd>{pct(m.projecao_confianca)}</dd>
        </dl>
      </section>
    </>
  );
}
