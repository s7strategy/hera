/**
 * Mapa coroplético dos municípios.
 *
 * Sem tiles por padrão — e isso é decisão, não limitação. A malha municipal já
 * é o mapa; um basemap raster cobraria por uso (Mapbox/Google estão fora por
 * custo, conforme o briefing), pesaria no carregamento e competiria com o dado.
 * Quem quiser contexto define VITE_BASEMAP_STYLE com um style MapLibre próprio.
 *
 * O elemento de assinatura do produto mora aqui: mapa e tabela ligados nos dois
 * sentidos — hover na linha acende o município, clique no mapa seleciona, e
 * shift+arrastar filtra o conjunto pela área.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type MapGeoJSONFeature } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Municipio } from "../lib/types";
import { num } from "../lib/format";

const ESTILO_BASE = import.meta.env.VITE_BASEMAP_STYLE as string | undefined;

export const CORES = ["#33253f", "#5c2a5e", "#93334f", "#cc5a2b", "#f2a03c"];
const COR_SEM_DADO = "#1b2228";

interface Props {
  malha: GeoJSON.FeatureCollection | null;
  municipios: Municipio[];
  visiveis: Municipio[];
  selecionado: string | null;
  destacado: string | null;
  onSelecionar: (codigo: string | null) => void;
  onDestacar: (codigo: string | null) => void;
  onSelecionarArea: (codigos: string[]) => void;
}

/** Quebras por quintil do conjunto visível: a escala acompanha o que está na tela. */
export function calcularQuebras(valores: number[]): number[] {
  if (valores.length === 0) return [20, 40, 60, 80];
  const ordenados = [...valores].sort((a, b) => a - b);
  const q = (p: number) => ordenados[Math.min(ordenados.length - 1, Math.floor(p * ordenados.length))];
  const quebras = [q(0.2), q(0.4), q(0.6), q(0.8)];
  // garante monotonicidade estrita (o MapLibre exige degraus crescentes)
  for (let i = 1; i < quebras.length; i += 1) {
    if (quebras[i] <= quebras[i - 1]) quebras[i] = quebras[i - 1] + 0.01;
  }
  return quebras.map((v) => Math.round(v * 10) / 10);
}

export default function MapaChoropleth({
  malha,
  municipios,
  visiveis,
  selecionado,
  destacado,
  onSelecionar,
  onDestacar,
  onSelecionarArea,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapa = useRef<maplibregl.Map | null>(null);
  const [pronto, setPronto] = useState(false);
  const [caixa, setCaixa] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const [dica, setDica] = useState<{ x: number; y: number; m: Municipio } | null>(null);

  const porCodigo = useMemo(
    () => new Map(municipios.map((m) => [m.codigo_ibge, m])),
    [municipios],
  );
  const codigosVisiveis = useMemo(
    () => new Set(visiveis.map((m) => m.codigo_ibge)),
    [visiveis],
  );
  const quebras = useMemo(
    () => calcularQuebras(visiveis.map((m) => m.score_total).filter((v): v is number => v !== null)),
    [visiveis],
  );

  /* ------------------------------------------------------------- mapa base */
  useEffect(() => {
    if (!container.current || mapa.current) return;
    const estilo: maplibregl.StyleSpecification | string = ESTILO_BASE
      ? ESTILO_BASE
      : {
          version: 8,
          sources: {},
          layers: [{ id: "fundo", type: "background", paint: { "background-color": "#0d1114" } }],
        };
    const m = new maplibregl.Map({
      container: container.current,
      style: estilo,
      center: [-50.5, -27.3],
      zoom: 6,
      attributionControl: false,
      dragRotate: false,
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    m.addControl(
      new maplibregl.AttributionControl({
        compact: true,
        customAttribution: "Malha municipal: IBGE",
      }),
      "bottom-right",
    );
    m.on("load", () => setPronto(true));
    mapa.current = m;
    return () => {
      m.remove();
      mapa.current = null;
    };
  }, []);

  /* -------------------------------------------------- fonte + camadas ------ */
  useEffect(() => {
    const m = mapa.current;
    if (!m || !pronto || !malha) return;

    const dados: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: malha.features.map((f) => {
        const codigo = String((f.properties as Record<string, unknown>)?.codigo_ibge ?? f.id ?? "");
        const mun = porCodigo.get(codigo);
        return {
          ...f,
          id: codigo,
          properties: {
            codigo_ibge: codigo,
            nome: mun?.nome ?? "",
            score: mun?.score_total ?? null,
            visivel: codigosVisiveis.has(codigo) ? 1 : 0,
            confianca: mun?.confianca ?? 0,
          },
        };
      }),
    };

    const fonte = m.getSource("municipios") as maplibregl.GeoJSONSource | undefined;
    if (fonte) {
      fonte.setData(dados);
    } else {
      m.addSource("municipios", { type: "geojson", data: dados, promoteId: "codigo_ibge" });
      m.addLayer({
        id: "municipios-preenchimento",
        type: "fill",
        source: "municipios",
        paint: {
          "fill-color": COR_SEM_DADO,
          // Município fora do filtro não some: fica em cinza de contexto, para a
          // silhueta do estado continuar inteira e o recorte ficar legível.
          "fill-opacity": ["case", ["==", ["get", "visivel"], 1], 0.88, 0.5],
        },
      });
      m.addLayer({
        id: "municipios-contorno",
        type: "line",
        source: "municipios",
        paint: { "line-color": "#0d1114", "line-width": 0.5 },
      });
      m.addLayer({
        id: "municipios-selecionado",
        type: "line",
        source: "municipios",
        filter: ["==", ["get", "codigo_ibge"], ""],
        paint: { "line-color": "#ff9d3d", "line-width": 2.2 },
      });
      m.addLayer({
        id: "municipios-destacado",
        type: "line",
        source: "municipios",
        filter: ["==", ["get", "codigo_ibge"], ""],
        paint: { "line-color": "#ffffff", "line-width": 1.4 },
      });

      const bounds = new maplibregl.LngLatBounds();
      dados.features.forEach((f) => {
        const g = f.geometry;
        const coords: number[][] =
          g.type === "Polygon"
            ? (g.coordinates as number[][][]).flat()
            : g.type === "MultiPolygon"
              ? (g.coordinates as number[][][][]).flat(2)
              : [];
        coords.forEach((c) => bounds.extend([c[0], c[1]] as [number, number]));
      });
      if (!bounds.isEmpty()) m.fitBounds(bounds, { padding: 28, duration: 0 });
    }

    m.setPaintProperty("municipios-preenchimento", "fill-color", [
      "case",
      ["!=", ["get", "visivel"], 1],
      COR_SEM_DADO,
      ["==", ["typeof", ["get", "score"]], "number"],
      [
        "step",
        ["get", "score"],
        CORES[0],
        quebras[0],
        CORES[1],
        quebras[1],
        CORES[2],
        quebras[2],
        CORES[3],
        quebras[3],
        CORES[4],
      ],
      COR_SEM_DADO,
    ]);
  }, [pronto, malha, porCodigo, codigosVisiveis, quebras]);

  /* --------------------------------------------------------- interações --- */
  useEffect(() => {
    const m = mapa.current;
    if (!m || !pronto) return;

    const aoMover = (e: maplibregl.MapMouseEvent) => {
      const f = m.queryRenderedFeatures(e.point, { layers: ["municipios-preenchimento"] })[0] as
        | MapGeoJSONFeature
        | undefined;
      const codigo = f ? String(f.properties?.codigo_ibge) : null;
      m.getCanvas().style.cursor = codigo ? "pointer" : "";
      onDestacar(codigo);
      const mun = codigo ? porCodigo.get(codigo) : undefined;
      setDica(mun ? { x: e.point.x, y: e.point.y, m: mun } : null);
    };
    const aoSair = () => {
      onDestacar(null);
      setDica(null);
    };
    const aoClicar = (e: maplibregl.MapMouseEvent) => {
      const f = m.queryRenderedFeatures(e.point, { layers: ["municipios-preenchimento"] })[0];
      onSelecionar(f ? String(f.properties?.codigo_ibge) : null);
    };

    m.on("mousemove", aoMover);
    m.on("mouseout", aoSair);
    m.on("click", aoClicar);
    return () => {
      m.off("mousemove", aoMover);
      m.off("mouseout", aoSair);
      m.off("click", aoClicar);
    };
  }, [pronto, porCodigo, onDestacar, onSelecionar]);

  /* --------------------------------- seleção por área (shift + arrastar) --- */
  useEffect(() => {
    const m = mapa.current;
    const el = container.current;
    if (!m || !pronto || !el) return;
    let inicio: { x: number; y: number } | null = null;

    const aoPressionar = (ev: MouseEvent) => {
      if (!ev.shiftKey) return;
      ev.preventDefault();
      const r = el.getBoundingClientRect();
      inicio = { x: ev.clientX - r.left, y: ev.clientY - r.top };
      m.dragPan.disable();
    };
    const aoArrastar = (ev: MouseEvent) => {
      if (!inicio) return;
      const r = el.getBoundingClientRect();
      const x = ev.clientX - r.left;
      const y = ev.clientY - r.top;
      setCaixa({
        x: Math.min(inicio.x, x),
        y: Math.min(inicio.y, y),
        w: Math.abs(x - inicio.x),
        h: Math.abs(y - inicio.y),
      });
    };
    const aoSoltar = (ev: MouseEvent) => {
      if (!inicio) return;
      const r = el.getBoundingClientRect();
      const fim = { x: ev.clientX - r.left, y: ev.clientY - r.top };
      const p1 = new maplibregl.Point(inicio.x, inicio.y);
      const p2 = new maplibregl.Point(fim.x, fim.y);
      inicio = null;
      setCaixa(null);
      m.dragPan.enable();
      if (Math.abs(p1.x - p2.x) < 4 && Math.abs(p1.y - p2.y) < 4) return;
      const feicoes = m.queryRenderedFeatures([p1, p2], { layers: ["municipios-preenchimento"] });
      const codigos = Array.from(new Set(feicoes.map((f) => String(f.properties?.codigo_ibge))));
      onSelecionarArea(codigos);
    };

    el.addEventListener("mousedown", aoPressionar);
    window.addEventListener("mousemove", aoArrastar);
    window.addEventListener("mouseup", aoSoltar);
    return () => {
      el.removeEventListener("mousedown", aoPressionar);
      window.removeEventListener("mousemove", aoArrastar);
      window.removeEventListener("mouseup", aoSoltar);
    };
  }, [pronto, onSelecionarArea]);

  /* --------------------------------------------- destaque vindo da tabela -- */
  useEffect(() => {
    const m = mapa.current;
    if (!m || !pronto || !m.getLayer("municipios-destacado")) return;
    m.setFilter("municipios-destacado", ["==", ["get", "codigo_ibge"], destacado ?? ""]);
  }, [destacado, pronto]);

  useEffect(() => {
    const m = mapa.current;
    if (!m || !pronto || !m.getLayer("municipios-selecionado")) return;
    m.setFilter("municipios-selecionado", ["==", ["get", "codigo_ibge"], selecionado ?? ""]);
  }, [selecionado, pronto]);

  return (
    <div className="mapa" ref={container} role="application" aria-label="Mapa de municípios por score">
      {caixa && (
        <div
          className="caixa-selecao"
          style={{ left: caixa.x, top: caixa.y, width: caixa.w, height: caixa.h }}
        />
      )}
      {dica && (
        <div
          className="tooltip-mapa dados"
          style={{
            left: Math.min(dica.x + 12, (container.current?.clientWidth ?? 400) - 190),
            top: dica.y + 12,
          }}
        >
          <b>{dica.m.nome}</b> · score {num(dica.m.score_total, 1)}
        </div>
      )}
      <div className="dica-mapa">clique seleciona · shift + arrastar filtra a área</div>
      <div className="legenda">
        <h4>Score do modelo</h4>
        <div className="legenda-escala">
          {CORES.map((c) => (
            <div key={c} className="legenda-passo" style={{ background: c }} />
          ))}
        </div>
        <div className="legenda-rotulos">
          <span>menor</span>
          <span>{quebras.map((q) => num(q, 0)).join(" · ")}</span>
          <span>maior</span>
        </div>
        <div className="legenda-nota">
          Quintis do conjunto filtrado. Cinza = fora do filtro ou sem score.
        </div>
      </div>
    </div>
  );
}
