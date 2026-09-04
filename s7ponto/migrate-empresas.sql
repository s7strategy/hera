-- ============================================================================
--  S7 PONTO — migração: empresas / sedes
--  Rode UMA VEZ no SQL Editor (postgres) se o schema já existia.
-- ============================================================================

create table if not exists s7ponto.companies (
  id          uuid        primary key default gen_random_uuid(),
  name        text        not null,
  color       text        not null default '#3987e5',
  active      boolean     not null default true,
  sort_order  integer     not null default 0,
  created_at  timestamptz not null default now()
);
comment on table s7ponto.companies is
  'Empresas / sedes onde a equipe trabalha (Pessoal, Cineplay, S7…).';

create table if not exists s7ponto.company_assignments (
  user_id    uuid not null references s7ponto.profiles (id) on delete cascade,
  company_id uuid not null references s7ponto.companies (id) on delete cascade,
  primary key (user_id, company_id)
);
comment on table s7ponto.company_assignments is
  'Quais empresas cada pessoa pode escolher ao iniciar o turno.';

alter table s7ponto.shifts
  add column if not exists company_id   uuid references s7ponto.companies (id) on delete set null,
  add column if not exists company_name text;

comment on column s7ponto.shifts.company_name is
  'Foto do nome da empresa no momento do turno. Renomear depois não reescreve o passado.';

create index if not exists shifts_por_empresa
  on s7ponto.shifts (company_id, started_at desc);

alter table s7ponto.companies            enable row level security;
alter table s7ponto.company_assignments  enable row level security;

drop policy if exists companies_leitura on s7ponto.companies;
create policy companies_leitura on s7ponto.companies for select to authenticated using (true);

drop policy if exists companies_escrita_admin on s7ponto.companies;
create policy companies_escrita_admin on s7ponto.companies for all to authenticated
  using (s7ponto.is_admin()) with check (s7ponto.is_admin());

drop policy if exists company_atrib_leitura on s7ponto.company_assignments;
create policy company_atrib_leitura on s7ponto.company_assignments for select to authenticated
  using (user_id = auth.uid() or s7ponto.is_admin());

drop policy if exists company_atrib_escrita_admin on s7ponto.company_assignments;
create policy company_atrib_escrita_admin on s7ponto.company_assignments for all to authenticated
  using (s7ponto.is_admin()) with check (s7ponto.is_admin());

grant all on all tables    in schema s7ponto to anon, authenticated, service_role;
grant all on all sequences in schema s7ponto to anon, authenticated, service_role;

-- Empresas iniciais (só se a tabela estiver vazia)
insert into s7ponto.companies (name, color, sort_order)
select * from (values
  ('Pessoal',  '#c98500', 1),
  ('Cineplay', '#3987e5', 2),
  ('S7',       '#d95926', 3)
) as t(name, color, sort_order)
where not exists (select 1 from s7ponto.companies);

-- Quem já está na equipe e ainda não tem empresa: libera todas as ativas
insert into s7ponto.company_assignments (user_id, company_id)
select p.id, c.id
  from s7ponto.profiles p
  cross join s7ponto.companies c
 where p.active and c.active
   and not exists (
     select 1 from s7ponto.company_assignments ca where ca.user_id = p.id
   )
on conflict do nothing;
