-- ============================================================================
--  S7 PONTO — 3 modos de pagamento
--
--  hourly = por HORA:  horas × R$/h da tarefa
--  task   = por TAREFA: valor FIXO da tarefa (não multiplica pelas horas)
--  shift  = por TURNO:  valor FIXO do período manhã / tarde / noite
-- ============================================================================

alter table s7ponto.profiles
  add column if not exists pay_mode text not null default 'hourly';

-- Garante o check certo (idempotente)
alter table s7ponto.profiles drop constraint if exists profiles_pay_mode_check;
alter table s7ponto.profiles
  add constraint profiles_pay_mode_check
  check (pay_mode in ('hourly', 'task', 'shift'));

comment on column s7ponto.profiles.pay_mode is
  'hourly=hora×tarefa; task=valor fixo da tarefa; shift=valor fixo manhã/tarde/noite.';

alter table s7ponto.shifts
  add column if not exists period text;
alter table s7ponto.shifts drop constraint if exists shifts_period_check;
alter table s7ponto.shifts
  add constraint shifts_period_check
  check (period is null or period in ('manha', 'tarde', 'noite'));

alter table s7ponto.shifts
  add column if not exists pay_mode text;
alter table s7ponto.shifts drop constraint if exists shifts_pay_mode_check;
alter table s7ponto.shifts
  add constraint shifts_pay_mode_check
  check (pay_mode is null or pay_mode in ('hourly', 'task', 'shift'));

alter table s7ponto.shifts
  add column if not exists flat_amount numeric(10,2);
alter table s7ponto.shifts drop constraint if exists shifts_flat_amount_check;
alter table s7ponto.shifts
  add constraint shifts_flat_amount_check
  check (flat_amount is null or flat_amount >= 0);

comment on column s7ponto.shifts.flat_amount is
  'Valor fixo do turno (pay_mode=shift). Independente das horas.';

alter table s7ponto.segments
  add column if not exists period text;
alter table s7ponto.segments drop constraint if exists segments_period_check;
alter table s7ponto.segments
  add constraint segments_period_check
  check (period is null or period in ('manha', 'tarde', 'noite'));

-- Valor fixo do trecho (pay_mode=task). Em hourly, fica null e usa hourly_rate×horas.
alter table s7ponto.segments
  add column if not exists flat_amount numeric(10,2);
alter table s7ponto.segments drop constraint if exists segments_flat_amount_check;
alter table s7ponto.segments
  add constraint segments_flat_amount_check
  check (flat_amount is null or flat_amount >= 0);

comment on column s7ponto.segments.flat_amount is
  'Valor FIXO do trecho quando a pessoa é paga por tarefa. Null = paga por hora.';

-- Limpa o modelo errado (tarefa×período)
drop function if exists s7ponto.taxa_da_pessoa(uuid, uuid, text);
drop table if exists s7ponto.pay_rates cascade;

-- Overrides / valores por pessoa+tarefa
-- hourly → hourly_rate (R$/h); task → flat_amount (R$ fixo)
create table if not exists s7ponto.task_rates (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references s7ponto.profiles (id) on delete cascade,
  task_id      uuid not null references s7ponto.tasks (id) on delete cascade,
  hourly_rate  numeric(10,2),
  flat_amount  numeric(10,2),
  created_at   timestamptz not null default now(),
  unique (user_id, task_id),
  check (hourly_rate is null or hourly_rate >= 0),
  check (flat_amount is null or flat_amount >= 0)
);
comment on table s7ponto.task_rates is
  'Por pessoa+tarefa: hourly_rate (modo hourly) ou flat_amount (modo task).';

-- Valores fixos por período (modo shift)
create table if not exists s7ponto.shift_rates (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references s7ponto.profiles (id) on delete cascade,
  period     text not null check (period in ('manha', 'tarde', 'noite')),
  amount     numeric(10,2) not null default 0 check (amount >= 0),
  created_at timestamptz not null default now(),
  unique (user_id, period)
);
comment on table s7ponto.shift_rates is
  'Valor FIXO manhã/tarde/noite quando pay_mode=shift (ex.: Fran).';

create index if not exists task_rates_por_pessoa on s7ponto.task_rates (user_id);
create index if not exists shift_rates_por_pessoa on s7ponto.shift_rates (user_id);

alter table s7ponto.task_rates  enable row level security;
alter table s7ponto.shift_rates enable row level security;

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

grant all on all tables in schema s7ponto to anon, authenticated, service_role;
grant all on all sequences in schema s7ponto to anon, authenticated, service_role;

insert into s7ponto.tasks (name, color, hourly_rate, sort_order, active)
select * from (values
  ('Atendimento', '#199e70', 12.00, 10, true),
  ('Tarefas',      '#3987e5', 15.00, 11, true),
  ('Treinamento',  '#9085e9', 20.00, 12, true)
) as t(name, color, hourly_rate, sort_order, active)
where not exists (select 1 from s7ponto.tasks x where lower(x.name) = lower(t.name));

update s7ponto.tasks set hourly_rate = 12 where lower(name) = 'atendimento';
update s7ponto.tasks set active = false
 where lower(name) in ('cozinha', 'produção', 'producao', 'limpeza') and active;

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
