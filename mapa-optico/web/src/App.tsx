import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import LimiteDeErro from "./components/LimiteDeErro";
import MapaChoropleth, { MapaIndisponivel } from "./components/MapaChoropleth";
import TabelaRanking from "./components/TabelaRanking";
import FiltrosBar from "./components/FiltrosBar";
import FichaMunicipio from "./components/FichaMunicipio";
import PainelPesos from "./components/PainelPesos";
import PainelNegocio from "./components/PainelNegocio";
import PainelSincronizacao from "./components/PainelSincronizacao";
import { carregarDados, type DadosCarregados } from "./lib/data";
import { FILTROS_INICIAIS, aplicar, type Filtros } from "./lib/filtros";
import { calcularScore, haversineKm } from "./lib/score";
import { projetar } from "./lib/projecao";
import { MODO_PADRAO, type ModoOrdenacao, ordenarPor, reposicionar } from "./lib/ordenacao";
import { baixarCSV } from "./lib/exportar";
import { dataHora } from "./lib/format";
import type { Municipio, Negocio, Pesos } from "./lib/types";

type Aba = "mapa" | "negocio" | "pesos" | "sincronizar";

export default function App() {
  const [dados, setDados] = useState<DadosCarregados | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aba, setAba] = useState<Aba>("mapa");
  const [filtros, setFiltros] = useState<Filtros>(FILTROS_INICIAIS);
  const [selecionado, setSelecionado] = useState<string | null>(null);
  const [destacado, setDestacado] = useState<string | null>(null);
  const [pesosAjustados, setPesosAjustados] = useState<Pesos | null>(null);
  const [negocioAjustado, setNegocioAjustado] = useState<Negocio | null>(null);
  const [modo, setModo] = useState<ModoOrdenacao>(MODO_PADRAO);
  const [larguraMapa, setLarguraMapa] = useState(50);
  const splitRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    carregarDados()
      .then(setDados)
      .catch((e: Error) => setErro(e.message));
  }, []);

  const pesosBase = dados?.snapshot.pesos ?? null;
  const pesos = pesosAjustados ?? pesosBase;
  const negocioBase = dados?.snapshot.negocio ?? null;
  const negocio = negocioAjustado ?? negocioBase;

  /**
   * Ranking exibido: o do pipeline, ou recalculado quando o usuário mexeu nos
   * pesos ou nos parâmetros do negócio. A ordem final vem do modo escolhido na
   * barra — e a coluna "#" é reatribuída para acompanhar.
   */
  const ranking: Municipio[] = useMemo(() => {
    if (!dados) return [];
    let base = dados.snapshot.municipios;
    if (pesosAjustados && pesos) base = calcularScore(base, pesos).municipios;
    if (negocioAjustado && negocio) base = projetar(base, negocio);
    return reposicionar(ordenarPor(base, modo));
  }, [dados, pesosAjustados, pesos, negocioAjustado, negocio, modo]);

  const visiveis = useMemo(() => aplicar(ranking, filtros), [ranking, filtros]);
  const ufs = useMemo(
    () => Array.from(new Set(ranking.map((m) => m.uf).filter(Boolean))).sort(),
    [ranking],
  );

  const municipioSelecionado = useMemo(
    () => ranking.find((m) => m.codigo_ibge === selecionado) ?? null,
    [ranking, selecionado],
  );

  const oticasDoSelecionado = useMemo(
    () => (dados?.snapshot.oticas ?? []).filter((o) => o.codigo_ibge === selecionado),
    [dados, selecionado],
  );

  const vizinhosProximos = useMemo(() => {
    if (!municipioSelecionado || !pesos) return [];
    const raio = pesos.canibalizacao?.raio_km ?? 30;
    const { lat, lon } = municipioSelecionado;
    if (lat === null || lon === null) return [];
    return ranking
      .filter(
        (m) =>
          m.codigo_ibge !== municipioSelecionado.codigo_ibge &&
          m.ranqueavel &&
          m.lat !== null &&
          m.lon !== null &&
          haversineKm(lat, lon, m.lat, m.lon) <= raio,
      )
      .map((m) => ({ nome: m.nome, km: Math.round(haversineKm(lat, lon, m.lat!, m.lon!) * 10) / 10 }))
      .sort((a, b) => a.km - b.km)
      .slice(0, 6);
  }, [municipioSelecionado, ranking, pesos]);

  /* --------------------------------------------------- divisor arrastável */
  const iniciarArraste = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const mover = (ev: MouseEvent) => {
      const caixa = splitRef.current?.getBoundingClientRect();
      if (!caixa) return;
      const pct = ((ev.clientX - caixa.left) / caixa.width) * 100;
      setLarguraMapa(Math.min(80, Math.max(25, pct)));
    };
    const soltar = () => {
      window.removeEventListener("mousemove", mover);
      window.removeEventListener("mouseup", soltar);
    };
    window.addEventListener("mousemove", mover);
    window.addEventListener("mouseup", soltar);
  }, []);

  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelecionado(null);
    };
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, []);

  if (erro) {
    return (
      <div className="vazio">
        <h3>Não consegui carregar os dados</h3>
        <p>{erro}</p>
        <p>
          Gere um snapshot com <code>mapa-optico ingest --uf SC</code> — ou, só para ver a interface
          funcionando, <code>mapa-optico demo --uf SC</code>.
        </p>
      </div>
    );
  }

  if (!dados || !pesos || !pesosBase || !negocio || !negocioBase) {
    return <div className="carregando">carregando dados…</div>;
  }

  const demo = Boolean(dados.snapshot.proveniencia?.demo);
  const avisos = dados.snapshot.avisos ?? [];

  return (
    <div className="app">
      {demo && (
        <div className="tarja tarja-demo">
          <b>MODO DEMO — DADOS SINTÉTICOS</b>
          <span>
            Nenhum número desta tela veio do CNES, do IBGE ou do Google Places. Serve para avaliar a
            interface, não para decidir cidade.
          </span>
        </div>
      )}
      {!demo && avisos.length > 0 && (
        <div className="tarja tarja-aviso">
          <b>⚠</b>
          <span>{avisos.join(" · ")}</span>
        </div>
      )}

      <header className="topo">
        <div className="marca">
          Mapa <span>Óptico</span>
          <small>
            modelo {dados.snapshot.versao_modelo} · {dados.origem} · {dataHora(dados.snapshot.gerado_em)}
          </small>
        </div>
        <div className="abas" role="tablist">
          <button
            className="aba"
            role="tab"
            aria-selected={aba === "mapa"}
            onClick={() => setAba("mapa")}
          >
            Mapa + tabela
          </button>
          <button
            className="aba"
            role="tab"
            aria-selected={aba === "negocio"}
            onClick={() => setAba("negocio")}
          >
            Faturamento
          </button>
          <button
            className="aba"
            role="tab"
            aria-selected={aba === "pesos"}
            onClick={() => setAba("pesos")}
          >
            Ajuste de pesos
          </button>
          <button
            className="aba"
            role="tab"
            aria-selected={aba === "sincronizar"}
            onClick={() => setAba("sincronizar")}
          >
            Sincronizar
          </button>
        </div>
      </header>

      {aba === "mapa" ? (
        <>
          <FiltrosBar
            filtros={filtros}
            ufsDisponiveis={ufs}
            modo={modo}
            onMudarModo={setModo}
            onMudar={setFiltros}
            total={ranking.length}
            visiveis={visiveis.length}
            areaAtiva={filtros.area !== null}
            onLimparArea={() => setFiltros({ ...filtros, area: null })}
            onExportar={() => baixarCSV(visiveis)}
          />
          <div className="corpo">
            <div className="split" ref={splitRef}>
              <div className="painel-mapa" style={{ flex: `0 0 ${larguraMapa}%` }}>
                <LimiteDeErro aoFalhar={(erro) => <MapaIndisponivel motivo={erro} />}>
                  <MapaChoropleth
                    malha={dados.malha}
                    municipios={ranking}
                    visiveis={visiveis}
                    metrica={modo}
                    selecionado={selecionado}
                    destacado={destacado}
                    onSelecionar={setSelecionado}
                    onDestacar={setDestacado}
                    onSelecionarArea={(codigos) =>
                      setFiltros((f) => ({ ...f, area: codigos.length ? codigos : null }))
                    }
                  />
                </LimiteDeErro>
              </div>
              <div
                className="divisor"
                onMouseDown={iniciarArraste}
                role="separator"
                aria-orientation="vertical"
                aria-label="Redimensionar mapa e tabela"
              />
              <div className="painel-tabela">
                <TabelaRanking
                  municipios={visiveis}
                  modo={modo}
                  selecionado={selecionado}
                  destacado={destacado}
                  onSelecionar={setSelecionado}
                  onDestacar={setDestacado}
                />
                <div className="rodape-tabela">
                  <span>
                    {visiveis.length} de {ranking.length} municípios
                  </span>
                  <span>·</span>
                  <span>
                    {visiveis.filter((m) => !m.ranqueavel).length} com confiança abaixo do mínimo
                  </span>
                  {dados.snapshot.canibalizacao?.length > 0 && (
                    <>
                      <span>·</span>
                      <span style={{ color: "var(--alerta)" }}>
                        {dados.snapshot.canibalizacao.length} par(es) de canibalização no topo
                      </span>
                    </>
                  )}
                </div>
              </div>
            </div>
            {municipioSelecionado && (
              <FichaMunicipio
                municipio={municipioSelecionado}
                negocio={negocio}
                oticas={oticasDoSelecionado}
                vizinhosProximos={vizinhosProximos}
                onFechar={() => setSelecionado(null)}
              />
            )}
          </div>
        </>
      ) : aba === "sincronizar" ? (
        <PainelSincronizacao snapshot={dados.snapshot} />
      ) : aba === "negocio" ? (
        <PainelNegocio
          negocioBase={negocioBase}
          negocio={negocio}
          municipios={dados.snapshot.municipios}
          onMudar={setNegocioAjustado}
          onRestaurar={() => setNegocioAjustado(null)}
        />
      ) : (
        <PainelPesos
          pesosBase={pesosBase}
          pesos={pesos}
          municipios={dados.snapshot.municipios}
          rankingBase={dados.snapshot.municipios}
          onMudar={setPesosAjustados}
          onRestaurar={() => setPesosAjustados(null)}
        />
      )}
    </div>
  );
}
