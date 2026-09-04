-- ============================================================================
--  S7 PONTO — histórico de pagamentos + totais da planilha (conferência)
-- ============================================================================

-- Bônus importados das planilhas
alter table s7ponto.bonus_entries drop constraint if exists bonus_entries_source_check;
alter table s7ponto.bonus_entries
  add constraint bonus_entries_source_check
  check (source in ('auto', 'manual', 'import'));

-- Pagamentos / recebimentos (o que já foi pago à pessoa)
create table if not exists s7ponto.payments (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references s7ponto.profiles (id) on delete cascade,
  paid_on     date not null,
  year_month  text not null check (year_month ~ '^\d{4}-\d{2}$'),
  amount      numeric(12,2) not null check (amount >= 0),
  title       text not null default 'Pagamento',
  note        text,
  source      text not null default 'manual'
              check (source in ('import', 'manual')),
  created_at  timestamptz not null default now()
);
comment on table s7ponto.payments is
  'Histórico do que já foi pago/recebido pela pessoa (com data).';

create index if not exists payments_por_pessoa_mes
  on s7ponto.payments (user_id, year_month);
create index if not exists payments_por_data
  on s7ponto.payments (paid_on desc);

-- Totais esperados da planilha (para bater com o app)
create table if not exists s7ponto.sheet_month_totals (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references s7ponto.profiles (id) on delete cascade,
  year_month      text not null check (year_month ~ '^\d{4}-\d{2}$'),
  expected_total  numeric(12,2) not null default 0,
  note            text,
  source          text not null default 'import',
  created_at      timestamptz not null default now(),
  unique (user_id, year_month)
);
comment on table s7ponto.sheet_month_totals is
  'Total do mês na planilha (trabalho + extras). Usado na conferência app × planilha.';

alter table s7ponto.payments           enable row level security;
alter table s7ponto.sheet_month_totals enable row level security;

drop policy if exists payments_leitura on s7ponto.payments;
create policy payments_leitura on s7ponto.payments for select to authenticated
  using (user_id = auth.uid() or s7ponto.is_admin());
drop policy if exists payments_escrita_admin on s7ponto.payments;
create policy payments_escrita_admin on s7ponto.payments for all to authenticated
  using (s7ponto.is_admin()) with check (s7ponto.is_admin());

drop policy if exists sheet_totals_leitura on s7ponto.sheet_month_totals;
create policy sheet_totals_leitura on s7ponto.sheet_month_totals for select to authenticated
  using (user_id = auth.uid() or s7ponto.is_admin());
drop policy if exists sheet_totals_escrita_admin on s7ponto.sheet_month_totals;
create policy sheet_totals_escrita_admin on s7ponto.sheet_month_totals for all to authenticated
  using (s7ponto.is_admin()) with check (s7ponto.is_admin());

grant all on all tables in schema s7ponto to anon, authenticated, service_role;
grant all on all sequences in schema s7ponto to anon, authenticated, service_role;
