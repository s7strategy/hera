-- ============================================================================
--  S7 PONTO — schema completo (Supabase self-hosted)
--  Rode este arquivo inteiro UMA VEZ no SQL Editor do Supabase Studio,
--  logado como postgres.
--
--  Tudo vive dentro do schema "s7ponto" — é o workspace separado do projeto.
--  Nada é criado em "public", nada se mistura com o que já existe no banco.
--
--  DEPOIS de rodar: exponha o schema no PostgREST (ver README.md, passo 3).
-- ============================================================================

create extension if not exists pgcrypto with schema extensions;

create schema if not exists s7ponto;

grant usage on schema s7ponto to anon, authenticated, service_role;
alter default privileges in schema s7ponto
  grant all on tables to anon, authenticated, service_role;
alter default privileges in schema s7ponto
  grant all on functions to anon, authenticated, service_role;
alter default privileges in schema s7ponto
  grant all on sequences to anon, authenticated, service_role;


-- ----------------------------------------------------------------------------
-- 1. TABELAS
-- ----------------------------------------------------------------------------

-- Pessoas. O id é o mesmo do auth.users do Supabase.
create table if not exists s7ponto.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  username    text        not null unique,
  full_name   text        not null,
  role        text        not null default 'employee'
                          check (role in ('admin', 'employee')),
  pay_mode    text        not null default 'hourly'
                          check (pay_mode in ('hourly', 'task', 'shift')),
  active      boolean     not null default true,
  created_at  timestamptz not null default now()
);
comment on table s7ponto.profiles is 'Equipe do S7 PONTO. role=admin enxerga e edita tudo.';
comment on column s7ponto.profiles.pay_mode is
  'hourly=hora×tarefa; task=valor fixo da tarefa; shift=valor fixo manhã/tarde/noite.';

-- Tarefas e quanto vale a hora de cada uma.
create table if not exists s7ponto.tasks (
  id           uuid        primary key default gen_random_uuid(),
  name         text        not null,
  color        text        not null default '#d95926',
  hourly_rate  numeric(10,2) not null default 0 check (hourly_rate >= 0),
  active       boolean     not null default true,
  sort_order   integer     not null default 0,
  created_at   timestamptz not null default now()
);
comment on column s7ponto.tasks.hourly_rate is 'R$ por hora — definido no painel do admin.';

-- Quais tarefas cada pessoa pode escolher ao iniciar o turno.
create table if not exists s7ponto.task_assignments (
  user_id uuid not null references s7ponto.profiles (id) on delete cascade,
  task_id uuid not null references s7ponto.tasks (id)    on delete cascade,
  primary key (user_id, task_id)
);

-- Empresas / sedes (Pessoal, Cineplay, S7…). A pessoa pode ter uma ou várias.
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

-- Um turno = da batida de entrada até a de saída.
create table if not exists s7ponto.shifts (
  id           uuid        primary key default gen_random_uuid(),
  user_id      uuid        not null references s7ponto.profiles (id) on delete cascade,
  company_id   uuid        references s7ponto.companies (id) on delete set null,
  company_name text,
  period       text        check (period is null or period in ('manha', 'tarde', 'noite')),
  pay_mode     text        check (pay_mode is null or pay_mode in ('hourly', 'task', 'shift')),
  flat_amount  numeric(10,2) check (flat_amount is null or flat_amount >= 0),
  started_at   timestamptz not null,
  ended_at     timestamptz,
  source       text        not null default 'app'
                           check (source in ('app', 'import', 'manual')),
  note         text,
  created_at   timestamptz not null default now(),
  constraint shifts_ordem_valida check (ended_at is null or ended_at >= started_at)
);
comment on column s7ponto.shifts.company_name is
  'Foto do nome da empresa no momento do turno. Renomear depois não reescreve o passado.';
comment on column s7ponto.shifts.flat_amount is
  'Valor fixo do turno quando pay_mode=shift. Independente das horas.';

-- Um trecho do turno dedicado a uma tarefa. Trocar de tarefa fecha um
-- trecho e abre o próximo — por isso o valor da hora fica congelado aqui.
create table if not exists s7ponto.segments (
  id           uuid        primary key default gen_random_uuid(),
  shift_id     uuid        not null references s7ponto.shifts (id) on delete cascade,
  task_id      uuid        references s7ponto.tasks (id) on delete set null,
  task_name    text        not null,
  hourly_rate  numeric(10,2) not null default 0 check (hourly_rate >= 0),
  flat_amount  numeric(10,2) check (flat_amount is null or flat_amount >= 0),
  period       text        check (period is null or period in ('manha', 'tarde', 'noite')),
  started_at   timestamptz not null,
  ended_at     timestamptz,
  created_at   timestamptz not null default now(),
  constraint segments_ordem_valida check (ended_at is null or ended_at >= started_at)
);
comment on column s7ponto.segments.hourly_rate is
  'Foto do R$/h no momento em que o trecho começou. Mudar a tarefa depois não reescreve o passado.';
comment on column s7ponto.segments.flat_amount is
  'Valor FIXO do trecho quando pay_mode=task. Null = paga por hora.';
comment on column s7ponto.segments.period is
  'manha | tarde | noite — escolhido ao iniciar (modo shift) ou opcional.';

-- Overrides por pessoa+tarefa: hourly_rate (modo hourly) ou flat_amount (modo task)
create table if not exists s7ponto.task_rates (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references s7ponto.profiles (id) on delete cascade,
  task_id      uuid not null references s7ponto.tasks (id) on delete cascade,
  hourly_rate  numeric(10,2) check (hourly_rate is null or hourly_rate >= 0),
  flat_amount  numeric(10,2) check (flat_amount is null or flat_amount >= 0),
  created_at   timestamptz not null default now(),
  unique (user_id, task_id)
);
comment on table s7ponto.task_rates is
  'Por pessoa+tarefa: hourly_rate (modo hourly) ou flat_amount (modo task).';

-- Valores fixos por período (modo shift — ex.: Fran)
create table if not exists s7ponto.shift_rates (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references s7ponto.profiles (id) on delete cascade,
  period     text not null check (period in ('manha', 'tarde', 'noite')),
  amount     numeric(10,2) not null default 0 check (amount >= 0),
  created_at timestamptz not null default now(),
  unique (user_id, period)
);
comment on table s7ponto.shift_rates is
  'Valor FIXO do turno por manhã/tarde/noite quando pay_mode=shift.';

-- Bônus mensais: template automático + lançamento concreto do mês
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

create unique index if not exists bonus_entries_template_mes
  on s7ponto.bonus_entries (user_id, year_month, template_id)
  where template_id is not null;

create index if not exists task_rates_por_pessoa on s7ponto.task_rates (user_id);
create index if not exists shift_rates_por_pessoa on s7ponto.shift_rates (user_id);
create index if not exists bonus_templates_por_pessoa
  on s7ponto.bonus_templates (user_id, sort_order);
create index if not exists bonus_entries_por_pessoa_mes
  on s7ponto.bonus_entries (user_id, year_month);
create index if not exists bonus_entries_por_mes
  on s7ponto.bonus_entries (year_month);

-- Regra de ouro: no máximo UM turno aberto por pessoa,
-- e no máximo UM trecho aberto por turno. Garantido pelo banco.
create unique index if not exists shifts_um_aberto_por_pessoa
  on s7ponto.shifts (user_id) where ended_at is null;
create unique index if not exists segments_um_aberto_por_turno
  on s7ponto.segments (shift_id) where ended_at is null;

create index if not exists shifts_por_pessoa_e_data
  on s7ponto.shifts (user_id, started_at desc);
create index if not exists shifts_por_empresa
  on s7ponto.shifts (company_id, started_at desc);
create index if not exists segments_por_turno
  on s7ponto.segments (shift_id, started_at);


-- ----------------------------------------------------------------------------
-- 2. GATILHO DE CONSISTÊNCIA
--    Fechou o turno? Todo trecho ainda aberto fecha junto, no mesmo horário.
-- ----------------------------------------------------------------------------

create or replace function s7ponto.fecha_trechos_com_o_turno()
returns trigger language plpgsql security definer
set search_path = s7ponto, public as $$
begin
  if new.ended_at is not null and old.ended_at is null then
    update s7ponto.segments
       set ended_at = new.ended_at
     where shift_id = new.id and ended_at is null;
  end if;
  return new;
end $$;

drop trigger if exists trg_fecha_trechos on s7ponto.shifts;
create trigger trg_fecha_trechos
  after update of ended_at on s7ponto.shifts
  for each row execute function s7ponto.fecha_trechos_com_o_turno();


-- ----------------------------------------------------------------------------
-- 3. FUNÇÕES DE PERMISSÃO
--    security definer para não entrar em recursão com o próprio RLS.
-- ----------------------------------------------------------------------------

create or replace function s7ponto.is_admin()
returns boolean language sql stable security definer
set search_path = s7ponto, public as $$
  select exists (
    select 1 from s7ponto.profiles p
     where p.id = auth.uid() and p.role = 'admin' and p.active
  );
$$;

create or replace function s7ponto.owns_shift(p_shift uuid)
returns boolean language sql stable security definer
set search_path = s7ponto, public as $$
  select exists (
    select 1 from s7ponto.shifts s
     where s.id = p_shift and s.user_id = auth.uid()
  );
$$;


-- ----------------------------------------------------------------------------
-- 4. RLS — cada um vê o que é seu; admin vê tudo.
-- ----------------------------------------------------------------------------

alter table s7ponto.profiles             enable row level security;
alter table s7ponto.tasks                enable row level security;
alter table s7ponto.task_assignments     enable row level security;
alter table s7ponto.companies            enable row level security;
alter table s7ponto.company_assignments  enable row level security;
alter table s7ponto.task_rates           enable row level security;
alter table s7ponto.shift_rates          enable row level security;
alter table s7ponto.bonus_templates      enable row level security;
alter table s7ponto.bonus_entries        enable row level security;
alter table s7ponto.shifts               enable row level security;
alter table s7ponto.segments             enable row level security;

-- profiles
drop policy if exists profiles_leitura on s7ponto.profiles;
create policy profiles_leitura on s7ponto.profiles for select to authenticated
  using (id = auth.uid() or s7ponto.is_admin());

drop policy if exists profiles_escrita_admin on s7ponto.profiles;
create policy profiles_escrita_admin on s7ponto.profiles for all to authenticated
  using (s7ponto.is_admin()) with check (s7ponto.is_admin());

-- tasks: todo mundo autenticado lê (precisa ver o nome da tarefa);
-- só admin cria, edita e apaga.
drop policy if exists tasks_leitura on s7ponto.tasks;
create policy tasks_leitura on s7ponto.tasks for select to authenticated using (true);

drop policy if exists tasks_escrita_admin on s7ponto.tasks;
create policy tasks_escrita_admin on s7ponto.tasks for all to authenticated
  using (s7ponto.is_admin()) with check (s7ponto.is_admin());

-- task_assignments
drop policy if exists atrib_leitura on s7ponto.task_assignments;
create policy atrib_leitura on s7ponto.task_assignments for select to authenticated
  using (user_id = auth.uid() or s7ponto.is_admin());

drop policy if exists atrib_escrita_admin on s7ponto.task_assignments;
create policy atrib_escrita_admin on s7ponto.task_assignments for all to authenticated
  using (s7ponto.is_admin()) with check (s7ponto.is_admin());

-- companies: todo mundo autenticado lê; só admin escreve.
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

-- pay rates: a pessoa lê os próprios; só admin escreve
drop policy if exists task_rates_leitura on s7ponto.task_rates;
create policy task_rates_leitura on s7ponto.task_rates for select to authenticated
  using (user_id = auth.uid() or s7ponto.is_admin());
drop policy if exists task_rates_escrita_admin on s7ponto.task_rates;
create policy task_rates_escrita_admin on s7ponto.task_rates for all to authenticated
  using (s7ponto.is_admin()) with check (s7ponto.is_admin());

drop policy if exists shift_rates_leitura on s7ponto.shift_rates;
create policy shift_rates_leitura on s7ponto.shift_rates for select to authenticated
  using (user_id = auth.uid() or s7ponto.is_admin());
drop policy if exists shift_rates_escrita_admin on s7ponto.shift_rates;
create policy shift_rates_escrita_admin on s7ponto.shift_rates for all to authenticated
  using (s7ponto.is_admin()) with check (s7ponto.is_admin());

-- bônus: a pessoa lê os próprios; só admin escreve
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

-- shifts: a pessoa bate o próprio ponto; admin corrige o de qualquer um.
drop policy if exists shifts_leitura on s7ponto.shifts;
create policy shifts_leitura on s7ponto.shifts for select to authenticated
  using (user_id = auth.uid() or s7ponto.is_admin());

drop policy if exists shifts_insercao on s7ponto.shifts;
create policy shifts_insercao on s7ponto.shifts for insert to authenticated
  with check (user_id = auth.uid() or s7ponto.is_admin());

drop policy if exists shifts_atualizacao on s7ponto.shifts;
create policy shifts_atualizacao on s7ponto.shifts for update to authenticated
  using (user_id = auth.uid() or s7ponto.is_admin())
  with check (user_id = auth.uid() or s7ponto.is_admin());

drop policy if exists shifts_exclusao_admin on s7ponto.shifts;
create policy shifts_exclusao_admin on s7ponto.shifts for delete to authenticated
  using (s7ponto.is_admin());

-- segments: seguem o dono do turno.
drop policy if exists segs_leitura on s7ponto.segments;
create policy segs_leitura on s7ponto.segments for select to authenticated
  using (s7ponto.owns_shift(shift_id) or s7ponto.is_admin());

drop policy if exists segs_insercao on s7ponto.segments;
create policy segs_insercao on s7ponto.segments for insert to authenticated
  with check (s7ponto.owns_shift(shift_id) or s7ponto.is_admin());

drop policy if exists segs_atualizacao on s7ponto.segments;
create policy segs_atualizacao on s7ponto.segments for update to authenticated
  using (s7ponto.owns_shift(shift_id) or s7ponto.is_admin())
  with check (s7ponto.owns_shift(shift_id) or s7ponto.is_admin());

drop policy if exists segs_exclusao_admin on s7ponto.segments;
create policy segs_exclusao_admin on s7ponto.segments for delete to authenticated
  using (s7ponto.is_admin());


-- ----------------------------------------------------------------------------
-- 5. CRIAR / EDITAR PESSOAS
--    O admin cadastra a equipe pelo painel; estas funções fazem o serviço
--    sujo de mexer no auth.users do Supabase.
-- ----------------------------------------------------------------------------

-- Interna: sem checagem de permissão. Só o postgres pode chamar
-- (usada no bloco de bootstrap, no final do arquivo).
create or replace function s7ponto._cria_usuario(
  p_username  text,
  p_full_name text,
  p_password  text,
  p_role      text default 'employee'
) returns uuid
language plpgsql security definer
set search_path = s7ponto, auth, extensions, public as $$
declare
  v_id       uuid := gen_random_uuid();
  v_user     text := lower(trim(p_username));
  v_email    text;
  v_now      timestamptz := now();
  v_tem_pid  boolean;
begin
  if v_user !~ '^[a-z0-9._-]{2,40}$' then
    raise exception 'Usuário inválido: use de 2 a 40 letras minúsculas, números, ponto, hífen ou _ (recebido: %)', p_username;
  end if;
  if length(coalesce(p_password, '')) < 4 then
    raise exception 'A senha precisa ter pelo menos 4 caracteres.';
  end if;
  if p_role not in ('admin', 'employee') then
    raise exception 'Perfil inválido: %', p_role;
  end if;

  -- O domínio abaixo precisa bater com CONFIG.EMAIL_DOMAIN do js/config.js.
  v_email := v_user || '@s7ponto.local';

  if exists (select 1 from auth.users u where u.email = v_email) then
    raise exception 'Já existe alguém com o usuário "%".', v_user;
  end if;

  insert into auth.users (
    instance_id, id, aud, role, email, encrypted_password,
    email_confirmed_at, created_at, updated_at,
    raw_app_meta_data, raw_user_meta_data,
    confirmation_token, recovery_token, email_change_token_new, email_change
  ) values (
    '00000000-0000-0000-0000-000000000000', v_id, 'authenticated', 'authenticated',
    v_email, extensions.crypt(p_password, extensions.gen_salt('bf')),
    v_now, v_now, v_now,
    '{"provider":"email","providers":["email"]}'::jsonb,
    jsonb_build_object('username', v_user, 'full_name', p_full_name),
    '', '', '', ''
  );

  -- auth.identities mudou de colunas entre versões do GoTrue; monta conforme o banco.
  select exists (
    select 1 from information_schema.columns
     where table_schema = 'auth' and table_name = 'identities' and column_name = 'provider_id'
  ) into v_tem_pid;

  if v_tem_pid then
    execute
      'insert into auth.identities (id, user_id, identity_data, provider, provider_id,
                                    last_sign_in_at, created_at, updated_at)
       values (gen_random_uuid(), $1, $2, ''email'', $3, $4, $4, $4)'
      using v_id, jsonb_build_object('sub', v_id::text, 'email', v_email), v_email, v_now;
  else
    execute
      'insert into auth.identities (id, user_id, identity_data, provider,
                                    last_sign_in_at, created_at, updated_at)
       values (gen_random_uuid(), $1, $2, ''email'', $3, $3, $3)'
      using v_id, jsonb_build_object('sub', v_id::text, 'email', v_email), v_now;
  end if;

  insert into s7ponto.profiles (id, username, full_name, role, active)
  values (v_id, v_user, coalesce(nullif(trim(p_full_name), ''), v_user), p_role, true);

  return v_id;
end $$;

revoke all on function s7ponto._cria_usuario(text, text, text, text) from public, anon, authenticated;

-- Pública: é a que o painel do admin chama. Exige admin.
create or replace function s7ponto.admin_cria_usuario(
  p_username  text,
  p_full_name text,
  p_password  text,
  p_role      text default 'employee'
) returns uuid
language plpgsql security definer
set search_path = s7ponto, public as $$
begin
  if not s7ponto.is_admin() then
    raise exception 'Só um administrador pode cadastrar pessoas.';
  end if;
  return s7ponto._cria_usuario(p_username, p_full_name, p_password, p_role);
end $$;

revoke all on function s7ponto.admin_cria_usuario(text, text, text, text) from public, anon;
grant execute on function s7ponto.admin_cria_usuario(text, text, text, text) to authenticated;

-- Só a administração define senhas (funcionário não troca a própria).
create or replace function s7ponto.troca_senha(p_user_id uuid, p_senha text)
returns void
language plpgsql security definer
set search_path = s7ponto, auth, extensions, public as $$
begin
  if not s7ponto.is_admin() then
    raise exception 'Só a administração pode definir senhas.';
  end if;
  if length(coalesce(p_senha, '')) < 4 then
    raise exception 'A senha precisa ter pelo menos 4 caracteres.';
  end if;
  update auth.users
     set encrypted_password = extensions.crypt(p_senha, extensions.gen_salt('bf')),
         updated_at = now()
   where id = p_user_id;
end $$;

revoke all on function s7ponto.troca_senha(uuid, text) from public, anon;
grant execute on function s7ponto.troca_senha(uuid, text) to authenticated;

-- Apagar de vez (some do auth e, em cascata, o histórico).
create or replace function s7ponto.admin_apaga_usuario(p_user_id uuid)
returns void
language plpgsql security definer
set search_path = s7ponto, auth, public as $$
begin
  if not s7ponto.is_admin() then
    raise exception 'Só um administrador pode remover pessoas.';
  end if;
  if p_user_id = auth.uid() then
    raise exception 'Você não pode apagar a si mesmo.';
  end if;
  delete from auth.users where id = p_user_id;
end $$;

revoke all on function s7ponto.admin_apaga_usuario(uuid) from public, anon;
grant execute on function s7ponto.admin_apaga_usuario(uuid) to authenticated;


-- ----------------------------------------------------------------------------
-- 5b. PERMISSÕES (garantia extra — se o schema já existia antes, os
--     "default privileges" acima não alcançam as tabelas antigas)
-- ----------------------------------------------------------------------------

grant all on all tables    in schema s7ponto to anon, authenticated, service_role;
grant all on all sequences in schema s7ponto to anon, authenticated, service_role;


-- ----------------------------------------------------------------------------
-- 6. TAREFAS INICIAIS (só na primeira vez)
-- ----------------------------------------------------------------------------

insert into s7ponto.tasks (name, color, hourly_rate, sort_order)
select * from (values
  ('Atendimento',  '#199e70', 12.00, 1),
  ('Tarefas',       '#3987e5', 15.00, 2),
  ('Treinamento',   '#9085e9', 20.00, 3),
  ('Cozinha',       '#d95926', 20.00, 4),
  ('Produção',      '#c98500', 22.00, 5),
  ('Limpeza',       '#d55181', 16.00, 6)
) as t(name, color, hourly_rate, sort_order)
where not exists (select 1 from s7ponto.tasks);

-- Desliga exemplos que não usamos no dia a dia da S7
update s7ponto.tasks set active = false
 where lower(name) in ('cozinha', 'produção', 'producao', 'limpeza');

insert into s7ponto.companies (name, color, sort_order)
select * from (values
  ('Pessoal',  '#c98500', 1),
  ('Cineplay', '#3987e5', 2),
  ('S7',       '#d95926', 3)
) as t(name, color, sort_order)
where not exists (select 1 from s7ponto.companies);

create or replace function s7ponto.taxa_hora(p_user uuid, p_task uuid)
returns numeric language sql stable security definer
set search_path = s7ponto, public as $$
  select coalesce(
    (select tr.hourly_rate from s7ponto.task_rates tr
      where tr.user_id = p_user and tr.task_id = p_task and tr.hourly_rate is not null),
    (select t.hourly_rate from s7ponto.tasks t where t.id = p_task),
    0
  );
$$;

create or replace function s7ponto.taxa_tarefa(p_user uuid, p_task uuid)
returns numeric language sql stable security definer
set search_path = s7ponto, public as $$
  select coalesce(
    (select tr.flat_amount from s7ponto.task_rates tr
      where tr.user_id = p_user and tr.task_id = p_task and tr.flat_amount is not null),
    (select t.hourly_rate from s7ponto.tasks t where t.id = p_task),
    0
  );
$$;

create or replace function s7ponto.taxa_turno(p_user uuid, p_period text)
returns numeric language sql stable security definer
set search_path = s7ponto, public as $$
  select coalesce(
    (select sr.amount from s7ponto.shift_rates sr
      where sr.user_id = p_user and sr.period = p_period),
    0
  );
$$;

revoke all on function s7ponto.taxa_hora(uuid, uuid) from public, anon;
revoke all on function s7ponto.taxa_tarefa(uuid, uuid) from public, anon;
revoke all on function s7ponto.taxa_turno(uuid, text) from public, anon;
grant execute on function s7ponto.taxa_hora(uuid, uuid) to authenticated;
grant execute on function s7ponto.taxa_tarefa(uuid, uuid) to authenticated;
grant execute on function s7ponto.taxa_turno(uuid, text) to authenticated;

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


-- ============================================================================
--  7. BOOTSTRAP — CRIE SEU PRIMEIRO ADMIN
--
--  Descomente as duas linhas abaixo, troque usuário/nome/senha e rode.
--  Depois disso você já entra no app e cadastra o resto da equipe pelo painel.
-- ============================================================================

-- select s7ponto._cria_usuario('admin', 'Administração S7', 'trocar-esta-senha', 'admin');

-- Já tem o usuário e só quer promover a admin?
-- update s7ponto.profiles set role = 'admin' where username = 'admin';
