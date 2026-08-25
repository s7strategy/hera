/**
 * Origem dos dados do dashboard.
 *
 * Com VITE_SUPABASE_URL/ANON_KEY configurados, le a view `v_ranking`.
 * Sem eles, cai para o snapshot estatico gerado pelo pipeline
 * (public/data/snapshot.json). O formato e o mesmo nos dois casos, entao a
 * interface nao sabe a diferenca — e a ferramenta funciona offline.
 */
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type { Municipio, Snapshot } from "./types";

/**
 * Build de arquivo unico (`npm run build:unico`) embute snapshot e malha aqui.
 * Nesse formato o app abre sem servidor e sem rede — util para levar num
 * notebook para a estrada, onde a conexao e o que for.
 */
interface DadosEmbutidos {
  snapshot: Snapshot;
  malhas: Record<string, GeoJSON.FeatureCollection>;
}
const EMBUTIDO = (globalThis as { __MAPA_OPTICO__?: DadosEmbutidos }).__MAPA_OPTICO__;

const URL_SUPABASE = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const CHAVE_SUPABASE = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const temSupabase = Boolean(URL_SUPABASE && CHAVE_SUPABASE);

let cliente: SupabaseClient | null = null;
export function supabase(): SupabaseClient | null {
  if (!temSupabase) return null;
  if (!cliente) cliente = createClient(URL_SUPABASE!, CHAVE_SUPABASE!);
  return cliente;
}

export interface DadosCarregados {
  snapshot: Snapshot;
  origem: "supabase" | "snapshot";
  malha: GeoJSON.FeatureCollection | null;
}

async function lerSnapshotEstatico(): Promise<Snapshot> {
  if (EMBUTIDO) return EMBUTIDO.snapshot;
  const resp = await fetch(`${import.meta.env.BASE_URL}data/snapshot.json`);
  if (!resp.ok) {
    throw new Error(
      `snapshot.json não encontrado (HTTP ${resp.status}). Rode o pipeline: ` +
        "`mapa-optico ingest --uf SC` (ou `mapa-optico demo --uf SC` para dados sintéticos).",
    );
  }
  return (await resp.json()) as Snapshot;
}

async function lerMalha(uf: string): Promise<GeoJSON.FeatureCollection | null> {
  if (EMBUTIDO) return EMBUTIDO.malhas[uf] ?? null;
  try {
    const resp = await fetch(`${import.meta.env.BASE_URL}data/malha-${uf}.geojson`);
    if (!resp.ok) return null;
    return (await resp.json()) as GeoJSON.FeatureCollection;
  } catch {
    return null;
  }
}

export async function carregarDados(): Promise<DadosCarregados> {
  const base = await lerSnapshotEstatico();
  let municipios = base.municipios;
  let origem: "supabase" | "snapshot" = "snapshot";

  const sb = supabase();
  if (sb) {
    const { data, error } = await sb.from("v_ranking").select("*");
    if (!error && data && data.length) {
      municipios = data as unknown as Municipio[];
      origem = "supabase";
    } else if (error) {
      console.warn("Supabase indisponível, usando snapshot:", error.message);
    }
  }

  const ufs = Array.from(new Set(municipios.map((m) => m.uf).filter(Boolean)));
  const malhas = await Promise.all(ufs.map((uf) => lerMalha(uf)));
  const features = malhas.flatMap((m) => m?.features ?? []);
  const malha: GeoJSON.FeatureCollection | null = features.length
    ? { type: "FeatureCollection", features }
    : null;

  return { snapshot: { ...base, municipios }, origem, malha };
}

/* ------------------------------------------------------------------ notas */
/** Notas de validação de campo. Vão para o Supabase quando há credencial;
 *  senão ficam no localStorage, para o uso de 2–3 pessoas do briefing. */
const CHAVE_LOCAL = "mapa-optico:notas";

export interface NotaLocal {
  codigo_ibge: string;
  texto: string;
  fila_sus_dias: number | null;
  criado_em: string;
}

export function lerNotasLocais(): Record<string, NotaLocal> {
  try {
    return JSON.parse(localStorage.getItem(CHAVE_LOCAL) ?? "{}");
  } catch {
    return {};
  }
}

export async function salvarNota(nota: NotaLocal): Promise<void> {
  const atuais = lerNotasLocais();
  atuais[nota.codigo_ibge] = nota;
  localStorage.setItem(CHAVE_LOCAL, JSON.stringify(atuais));
  const sb = supabase();
  if (sb) {
    const { error } = await sb.from("notas_municipio").insert({
      codigo_ibge: nota.codigo_ibge,
      texto: nota.texto,
      fila_sus_dias: nota.fila_sus_dias,
    });
    if (error) console.warn("nota salva só localmente:", error.message);
  }
}
