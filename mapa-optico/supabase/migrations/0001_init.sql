-- Mapa Optico — schema inicial
-- Roda no SQL Editor do Supabase ou via `supabase db push`.
-- Idempotente: pode rodar duas vezes sem quebrar.

create extension if not exists postgis;
create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------- municipios
create table if not exists municipios (
  codigo_ibge      char(7) primary key,
  nome             text not null,
  uf               char(2) not null,
  microrregiao     text,
  mesorregiao      text,
  populacao_total  integer,
  populacao_40mais integer,
  area_km2         numeric,
  renda_mediana    numeric,
  centroide        geography(point, 4326),
  geom             geography(multipolygon, 4326),
  -- de onde veio cada campo (oficial | espelho | manual) — a interface mostra isso
  fonte_por_campo  jsonb not null default '{}'::jsonb,
  atualizado_em    timestamptz not null default now()
);

create index if not exists municipios_uf_idx on municipios (uf);
create index if not exists municipios_centroide_idx on municipios using gist (centroide);
create index if not exists municipios_geom_idx on municipios using gist (geom);

-- ----------------------------------------------------------- oferta oftalmo
create table if not exists oferta_oftalmo (
  codigo_ibge          char(7) not null references municipios (codigo_ibge) on delete cascade,
  qtd_oftalmologistas  integer not null default 0,
  horas_semanais_total numeric,
  -- oftalmologista equivalente: horas/40. Um oftalmo de 4h/semana nao e um de 40h.
  oftalmo_equivalente  numeric,
  competencia_cnes     char(6) not null,
  origem               text,
  atualizado_em        timestamptz not null default now(),
  primary key (codigo_ibge, competencia_cnes)
);

-- ------------------------------------------------------------------- oticas
create table if not exists oticas (
  id             uuid primary key default gen_random_uuid(),
  codigo_ibge    char(7) references municipios (codigo_ibge) on delete cascade,
  place_id       text unique,
  nome           text,
  endereco       text,
  rating         numeric,
  total_ratings  integer,
  localizacao    geography(point, 4326),
  coletado_em    timestamptz not null default now()
);

create index if not exists oticas_municipio_idx on oticas (codigo_ibge);

-- ----------------------------------------------------------- distancia polo
create table if not exists distancia_polo (
  codigo_ibge      char(7) primary key references municipios (codigo_ibge) on delete cascade,
  polo_codigo_ibge char(7) references municipios (codigo_ibge),
  polo_nome        text,
  distancia_km     numeric,
  tempo_minutos    numeric,
  calculado_em     timestamptz not null default now()
);

-- ------------------------------------------------------------------- scores
create table if not exists scores (
  codigo_ibge   char(7) not null references municipios (codigo_ibge) on delete cascade,
  versao_modelo text not null,
  score_total   numeric,
  confianca     numeric not null default 0,
  ranqueavel    boolean not null default false,
  posicao       integer,
  circuito      integer,
  -- componentes: score de cada fator, para explicabilidade. Sem isso o score
  -- vira caixa preta e o usuario nao consegue discordar do modelo.
  componentes   jsonb not null,
  calculado_em  timestamptz not null default now(),
  primary key (codigo_ibge, versao_modelo)
);

create index if not exists scores_versao_idx on scores (versao_modelo, score_total desc);

-- ------------------------------------------------------------------ eventos
-- Fase 2: cada evento executado vira dado de treino do modelo.
create table if not exists eventos (
  id                  uuid primary key default gen_random_uuid(),
  codigo_ibge         char(7) references municipios (codigo_ibge),
  data_inicio         date,
  data_fim            date,
  investimento_midia  numeric,
  agendamentos        integer,
  compareceram        integer,
  receitas_prescritas integer,
  vendas              integer,
  faturamento_bruto   numeric,
  cmv                 numeric,
  custos_operacionais numeric,
  observacoes         text,
  criado_em           timestamptz not null default now()
);

-- Notas de validacao de campo (telefonema para a secretaria, fila do SUS etc.)
create table if not exists notas_municipio (
  id            uuid primary key default gen_random_uuid(),
  codigo_ibge   char(7) references municipios (codigo_ibge) on delete cascade,
  texto         text not null,
  fila_sus_dias integer,          -- Fase 2: campo opcional, preenchido a mao
  autor         text,
  criado_em     timestamptz not null default now()
);

create index if not exists notas_municipio_idx on notas_municipio (codigo_ibge, criado_em desc);

-- --------------------------------------------------------------------- view
-- Uma linha por municipio com tudo que o dashboard precisa.
create or replace view v_ranking as
select
  m.codigo_ibge,
  m.nome,
  m.uf,
  m.microrregiao,
  m.mesorregiao,
  m.populacao_total,
  m.populacao_40mais,
  m.renda_mediana,
  m.area_km2,
  st_y(m.centroide::geometry) as lat,
  st_x(m.centroide::geometry) as lon,
  o.qtd_oftalmologistas,
  o.oftalmo_equivalente,
  o.competencia_cnes,
  d.polo_codigo_ibge,
  d.polo_nome,
  d.distancia_km,
  d.tempo_minutos,
  (select count(*) from oticas t where t.codigo_ibge = m.codigo_ibge) as qtd_oticas,
  s.versao_modelo,
  s.score_total,
  s.confianca,
  s.ranqueavel,
  s.posicao,
  s.circuito,
  s.componentes
from municipios m
left join lateral (
  select * from oferta_oftalmo x
  where x.codigo_ibge = m.codigo_ibge
  order by x.competencia_cnes desc limit 1
) o on true
left join distancia_polo d on d.codigo_ibge = m.codigo_ibge
left join scores s on s.codigo_ibge = m.codigo_ibge;

-- ---------------------------------------------------------------------- RLS
-- Sao 2-3 usuarios: auth simples do Supabase, sem multi-tenant.
-- Leitura para qualquer usuario autenticado; escrita so pela service key do pipeline.
alter table municipios      enable row level security;
alter table oferta_oftalmo  enable row level security;
alter table oticas          enable row level security;
alter table distancia_polo  enable row level security;
alter table scores          enable row level security;
alter table eventos         enable row level security;
alter table notas_municipio enable row level security;

do $$
declare t text;
begin
  foreach t in array array['municipios','oferta_oftalmo','oticas','distancia_polo','scores']
  loop
    execute format(
      'drop policy if exists leitura_autenticada on %I; '
      'create policy leitura_autenticada on %I for select to authenticated using (true);', t, t);
  end loop;

  -- eventos e notas: os usuarios escrevem pela interface
  foreach t in array array['eventos','notas_municipio']
  loop
    execute format(
      'drop policy if exists escrita_autenticada on %I; '
      'create policy escrita_autenticada on %I for all to authenticated using (true) with check (true);', t, t);
  end loop;
end $$;
