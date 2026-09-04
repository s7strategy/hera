-- ============================================================================
--  S7 PONTO — bônus mensais (título + valor)
--  Automático (template recorrente) ou manual (só naquele mês).
-- ============================================================================

create table if not exists s7ponto.bonus_templates (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references s7ponto.profiles (id) on delete cascade,
  title       text not null,
  amount      numeric(10,2) not null default 0 check (amount >= 0),
  active      boolean not null default true,
  sort_order  integer not null default 0,
  created_at  timestamptz not null default now()
);
comment on table s7ponto.bonus_templates is
  'Bônus automático: enquanto ativo, gera lançamento todo mês (título + valor).';

create table if not exists s7ponto.bonus_entries (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references s7ponto.profiles (id) on delete cascade,
  year_month   text not null check (year_month ~ '^\d{4}-\d{2}$'),
  title        text not null,
  amount       numeric(10,2) not null default 0 check (amount >= 0),
  source       text not null default 'manual'
               check (source in ('auto', 'manual')),
  template_id  uuid references s7ponto.bonus_templates (id) on delete set null,
  note         text,
  created_at   timestamptz not null default now()
);
comment on table s7ponto.bonus_entries is
  'Lançamento concreto de bônus no mês (YYYY-MM). source=auto veio de template.';

-- Um template não duplica no mesmo mês
create unique index if not exists bonus_entries_template_mes
  on s7ponto.bonus_entries (user_id, year_month, template_id)
  where template_id is not null;

create index if not exists bonus_templates_por_pessoa
  on s7ponto.bonus_templates (user_id, sort_order);
create index if not exists bonus_entries_por_pessoa_mes
  on s7ponto.bonus_entries (user_id, year_month);
create index if not exists bonus_entries_por_mes
  on s7ponto.bonus_entries (year_month);

alter table s7ponto.bonus_templates enable row level security;
alter table s7ponto.bonus_entries   enable row level security;

drop policy if exists bonus_templates_leitura on s7ponto.bonus_templates;
create policy bonus_templates_leitura on s7ponto.bonus_templates for select to authenticated
  using (user_id = auth.uid() or s7ponto.is_admin());
drop policy if exists bonus_templates_escrita_admin on s7ponto.bonus_templates;
create policy bonus_templates_escrita_admin on s7ponto.bonus_templates for all to authenticated
  using (s7ponto.is_admin()) with check (s7ponto.is_admin());

drop policy if exists bonus_entries_leitura on s7ponto.bonus_entries;
create policy bonus_entries_leitura on s7ponto.bonus_entries for select to authenticated
  using (user_id = auth.uid() or s7ponto.is_admin());
drop policy if exists bonus_entries_escrita_admin on s7ponto.bonus_entries;
create policy bonus_entries_escrita_admin on s7ponto.bonus_entries for all to authenticated
  using (s7ponto.is_admin()) with check (s7ponto.is_admin());

-- Garante lançamentos auto dos templates ativos para um mês (idempotente).
-- Admin: qualquer pessoa. Funcionário: só a própria.
create or replace function s7ponto.garante_bonus_mes(p_user uuid, p_year_month text)
returns void
language plpgsql security definer
set search_path = s7ponto, public as $$
begin
  if p_year_month is null or p_year_month !~ '^\d{4}-\d{2}$' then
    raise exception 'Mês inválido: use AAAA-MM.';
  end if;
  if not (s7ponto.is_admin() or p_user = auth.uid()) then
    raise exception 'Sem permissão para gerar bônus deste mês.';
  end if;

  insert into s7ponto.bonus_entries (user_id, year_month, title, amount, source, template_id)
  select t.user_id, p_year_month, t.title, t.amount, 'auto', t.id
    from s7ponto.bonus_templates t
   where t.user_id = p_user and t.active
     and not exists (
       select 1 from s7ponto.bonus_entries e
        where e.user_id = t.user_id
          and e.year_month = p_year_month
          and e.template_id = t.id
     );
end $$;

revoke all on function s7ponto.garante_bonus_mes(uuid, text) from public, anon;
grant execute on function s7ponto.garante_bonus_mes(uuid, text) to authenticated;

grant all on all tables in schema s7ponto to anon, authenticated, service_role;
grant all on all sequences in schema s7ponto to anon, authenticated, service_role;
