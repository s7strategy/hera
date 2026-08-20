-- ============================================================================
-- Projecao financeira por municipio.
--
-- Tabela separada de `scores` de proposito. Sao duas perguntas diferentes com
-- ciclos de vida diferentes:
--
--   scores      "onde ha demanda reprimida" — muda quando os PESOS mudam
--   projecoes   "quanto isso vira dinheiro" — muda quando o NEGOCIO muda
--                (ticket do fornecedor, cache do medico, verba de midia)
--
-- Guardar junto obrigaria a recalcular o score inteiro so porque o fornecedor
-- reajustou a armacao. Separado, cada versao evolui no seu ritmo e as duas
-- coexistem no banco para comparacao.
-- ============================================================================

create table if not exists projecoes (
  codigo_ibge      char(7) not null references municipios (codigo_ibge) on delete cascade,
  versao_negocio   text    not null,

  -- % de possibilidade: faturamento contra o teto teorico (agenda cheia x
  -- conversao maxima x ticket maximo). Por construcao decompoe em exatamente
  -- tres fatores, guardados em `componentes`.
  potencial_pct    numeric,

  -- funil de demanda
  demanda_anual         numeric,
  capacidade_local_ano  numeric,
  demanda_represada     numeric,
  consultas_esperadas   numeric,
  capacidade_evento     numeric,
  ocupacao_agenda       numeric,
  demanda_nao_capturada numeric,
  dias_sugeridos        integer,

  -- conversao e dinheiro
  conversao               numeric,
  vendas_esperadas        numeric,
  ticket_estimado         numeric,
  faturamento_estimado    numeric,
  margem_bruta            numeric,
  custo_evento            numeric,
  lucro_estimado          numeric,
  retorno_sobre_custo     numeric,
  ponto_equilibrio_vendas numeric,

  -- Confianca cai a cada entrada imputada pela mediana do universo. NUNCA
  -- escondemos imputacao atras de um numero limpo.
  projecao_confianca numeric not null default 1,

  -- Rastro completo: funil etapa a etapa, fatores da concorrencia, custos
  -- abertos e a lista do que foi imputado. E o que a ficha do municipio abre.
  componentes jsonb not null,

  calculado_em timestamptz not null default now(),
  primary key (codigo_ibge, versao_negocio)
);

create index if not exists projecoes_versao_lucro_idx
  on projecoes (versao_negocio, lucro_estimado desc);
create index if not exists projecoes_versao_potencial_idx
  on projecoes (versao_negocio, potencial_pct desc);

-- ------------------------------------------------- oticas: nota e avaliacoes
-- A view antiga so contava oticas. Contagem sozinha nao distingue tres oticas
-- com 400 avaliacoes cada de trinta oticas que ninguem nunca avaliou — e essa
-- diferenca e justamente o que move a conversao.
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
  o.horas_semanais_total,
  o.competencia_cnes,
  d.polo_codigo_ibge,
  d.polo_nome,
  d.distancia_km,
  d.tempo_minutos,
  t.qtd_oticas,
  t.oticas_nota_media,
  t.oticas_avaliacoes,
  s.versao_modelo,
  s.score_total,
  s.confianca,
  s.ranqueavel,
  s.posicao,
  s.circuito,
  s.componentes,
  p.versao_negocio,
  p.potencial_pct,
  p.consultas_esperadas,
  p.ocupacao_agenda,
  p.conversao,
  p.vendas_esperadas,
  p.ticket_estimado,
  p.faturamento_estimado,
  p.margem_bruta,
  p.custo_evento,
  p.lucro_estimado,
  p.retorno_sobre_custo,
  p.ponto_equilibrio_vendas,
  p.dias_sugeridos,
  p.demanda_nao_capturada,
  p.projecao_confianca,
  p.componentes as projecao
from municipios m
left join lateral (
  select * from oferta_oftalmo x
  where x.codigo_ibge = m.codigo_ibge
  order by x.competencia_cnes desc limit 1
) o on true
left join distancia_polo d on d.codigo_ibge = m.codigo_ibge
left join lateral (
  -- Nota media ponderada pelo numero de avaliacoes: uma otica nota 5 com uma
  -- unica avaliacao nao pode pesar o mesmo que uma nota 4,3 com trezentas.
  select
    count(*)                                as qtd_oticas,
    sum(coalesce(x.total_ratings, 0))       as oticas_avaliacoes,
    case
      when sum(case when x.rating is not null then coalesce(x.total_ratings, 0) else 0 end) > 0
      then round(
        sum(x.rating * coalesce(x.total_ratings, 0)) filter (where x.rating is not null)
        / nullif(sum(coalesce(x.total_ratings, 0)) filter (where x.rating is not null), 0),
        2
      )
      -- Sem contagem de avaliacoes, media simples e o melhor disponivel.
      -- Sem nota nenhuma, fica NULL: cidade sem otica nao tem nota, e nota 0
      -- seria mentira.
      else round(avg(x.rating), 2)
    end                                     as oticas_nota_media
  from oticas x
  where x.codigo_ibge = m.codigo_ibge
) t on true
left join scores s on s.codigo_ibge = m.codigo_ibge
left join projecoes p on p.codigo_ibge = m.codigo_ibge;

-- ---------------------------------------------------------------------- RLS
alter table projecoes enable row level security;

drop policy if exists projecoes_leitura on projecoes;
create policy projecoes_leitura on projecoes
  for select to authenticated using (true);
