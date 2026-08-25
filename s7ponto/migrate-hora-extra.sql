-- S7 PONTO — avisos de hora extra (funcionário → gestor).
-- Aplicar no container s7hub-supabase-db, schema s7ponto. Depois: NOTIFY pgrst.

create table if not exists s7ponto.overtime_notices (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references s7ponto.profiles (id) on delete cascade,
  shift_id        uuid not null references s7ponto.shifts (id) on delete cascade,
  year_month      text not null check (year_month ~ '^\d{4}-\d{2}$'),
  hours_extra     numeric(8,4) not null default 0,
  hours_worked    numeric(8,4) not null default 0,
  hours_expected  numeric(8,4) not null default 0,
  authorized      boolean not null default false,
  notified_at     timestamptz not null default now(),
  created_at      timestamptz not null default now(),
  unique (shift_id)
);
comment on table s7ponto.overtime_notices is
  'Aviso de hora extra enviado do ponto ao gestor. Um por turno. authorized = a pessoa confirmou no fechamento.';

create index if not exists overtime_notices_por_pessoa_mes
  on s7ponto.overtime_notices (user_id, year_month);
create index if not exists overtime_notices_por_mes
  on s7ponto.overtime_notices (year_month, notified_at desc);

alter table s7ponto.overtime_notices enable row level security;

drop policy if exists overtime_leitura on s7ponto.overtime_notices;
create policy overtime_leitura on s7ponto.overtime_notices for select to authenticated
  using (user_id = auth.uid() or s7ponto.is_admin());

drop policy if exists overtime_insercao on s7ponto.overtime_notices;
create policy overtime_insercao on s7ponto.overtime_notices for insert to authenticated
  with check (
    (user_id = auth.uid() and s7ponto.owns_shift(shift_id))
    or s7ponto.is_admin()
  );

drop policy if exists overtime_atualizacao on s7ponto.overtime_notices;
create policy overtime_atualizacao on s7ponto.overtime_notices for update to authenticated
  using (user_id = auth.uid() or s7ponto.is_admin())
  with check (user_id = auth.uid() or s7ponto.is_admin());

drop policy if exists overtime_exclusao_admin on s7ponto.overtime_notices;
create policy overtime_exclusao_admin on s7ponto.overtime_notices for delete to authenticated
  using (s7ponto.is_admin());

grant all on table s7ponto.overtime_notices to anon, authenticated, service_role;
