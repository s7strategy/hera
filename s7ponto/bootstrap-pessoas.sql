-- ============================================================================
--  S7 PONTO — bootstrap de pessoas + empresas + pagamento
--  Idempotente: se o usuário já existe, só atualiza vínculos/modo.
--  Senha inicial de todos: teste1234
-- ============================================================================

-- Garante empresas
insert into s7ponto.companies (name, color, sort_order, active)
select * from (values
  ('Pessoal',  '#d95926', 1, true),
  ('Cineplay', '#3987e5', 2, true),
  ('S7',       '#199e70', 3, true)
) as c(name, color, sort_order, active)
where not exists (select 1 from s7ponto.companies x where lower(x.name) = lower(c.name));

-- Garante tarefas principais
insert into s7ponto.tasks (name, color, hourly_rate, sort_order, active)
select * from (values
  ('Atendimento', '#199e70', 12.00, 10, true),
  ('Tarefas',      '#3987e5', 15.00, 11, true),
  ('Treinamento',  '#9085e9', 20.00, 12, true)
) as t(name, color, hourly_rate, sort_order, active)
where not exists (select 1 from s7ponto.tasks x where lower(x.name) = lower(t.name));

update s7ponto.tasks set hourly_rate = 12, active = true where lower(name) = 'atendimento';
update s7ponto.tasks set hourly_rate = 15, active = true where lower(name) = 'tarefas';
update s7ponto.tasks set hourly_rate = 20, active = true where lower(name) = 'treinamento';

-- Cria usuários (pula se já existir)
do $$
declare
  r record;
  uid uuid;
begin
  for r in
    select * from (values
      ('denison', 'Denison',  'hourly'),
      ('milena',  'Milena',   'hourly'),
      ('david',   'David',    'hourly'),
      ('adriano', 'Adriano',  'hourly'),
      ('fran',    'Fran',     'shift')
    ) as p(username, full_name, pay_mode)
  loop
    select id into uid from s7ponto.profiles where username = r.username;
    if uid is null then
      uid := s7ponto._cria_usuario(r.username, r.full_name, 'teste1234', 'employee');
    end if;
    update s7ponto.profiles set pay_mode = r.pay_mode, active = true, full_name = r.full_name
     where id = uid;
  end loop;
end $$;

-- Empresas por pessoa
do $$
declare
  cid_pessoal  uuid := (select id from s7ponto.companies where lower(name)='pessoal'  limit 1);
  cid_cineplay uuid := (select id from s7ponto.companies where lower(name)='cineplay' limit 1);
  cid_s7       uuid := (select id from s7ponto.companies where lower(name)='s7'       limit 1);
  uid uuid;
begin
  -- DENISON → Cineplay
  uid := (select id from s7ponto.profiles where username='denison');
  delete from s7ponto.company_assignments where user_id = uid;
  insert into s7ponto.company_assignments(user_id, company_id) values (uid, cid_cineplay);

  -- MILENA → Cineplay
  uid := (select id from s7ponto.profiles where username='milena');
  delete from s7ponto.company_assignments where user_id = uid;
  insert into s7ponto.company_assignments(user_id, company_id) values (uid, cid_cineplay);

  -- DAVID → Cineplay + S7
  uid := (select id from s7ponto.profiles where username='david');
  delete from s7ponto.company_assignments where user_id = uid;
  insert into s7ponto.company_assignments(user_id, company_id) values
    (uid, cid_cineplay), (uid, cid_s7);

  -- ADRIANO → S7
  uid := (select id from s7ponto.profiles where username='adriano');
  delete from s7ponto.company_assignments where user_id = uid;
  insert into s7ponto.company_assignments(user_id, company_id) values (uid, cid_s7);

  -- FRAN → Pessoal
  uid := (select id from s7ponto.profiles where username='fran');
  delete from s7ponto.company_assignments where user_id = uid;
  insert into s7ponto.company_assignments(user_id, company_id) values (uid, cid_pessoal);
end $$;

-- Tarefas liberadas (todos hourly: Atendimento; David também Tarefas/Treinamento)
do $$
declare
  tid_at uuid := (select id from s7ponto.tasks where lower(name)='atendimento' limit 1);
  tid_ta uuid := (select id from s7ponto.tasks where lower(name)='tarefas'      limit 1);
  tid_tr uuid := (select id from s7ponto.tasks where lower(name)='treinamento'  limit 1);
  uid uuid;
begin
  foreach uid in array array[
    (select id from s7ponto.profiles where username='denison'),
    (select id from s7ponto.profiles where username='milena'),
    (select id from s7ponto.profiles where username='adriano')
  ]
  loop
    delete from s7ponto.task_assignments where user_id = uid;
    insert into s7ponto.task_assignments(user_id, task_id) values (uid, tid_at);
  end loop;

  uid := (select id from s7ponto.profiles where username='david');
  delete from s7ponto.task_assignments where user_id = uid;
  insert into s7ponto.task_assignments(user_id, task_id) values
    (uid, tid_at), (uid, tid_ta), (uid, tid_tr);

  -- Fran: modo shift — sem tarefas
  uid := (select id from s7ponto.profiles where username='fran');
  delete from s7ponto.task_assignments where user_id = uid;
end $$;

-- Taxas de tarefa (overrides = padrão das tasks; David com os 3)
do $$
declare
  tid_at uuid := (select id from s7ponto.tasks where lower(name)='atendimento' limit 1);
  tid_ta uuid := (select id from s7ponto.tasks where lower(name)='tarefas'      limit 1);
  tid_tr uuid := (select id from s7ponto.tasks where lower(name)='treinamento'  limit 1);
  uid uuid;
begin
  foreach uid in array array[
    (select id from s7ponto.profiles where username='denison'),
    (select id from s7ponto.profiles where username='milena'),
    (select id from s7ponto.profiles where username='adriano'),
    (select id from s7ponto.profiles where username='david')
  ]
  loop
    delete from s7ponto.task_rates where user_id = uid;
    insert into s7ponto.task_rates(user_id, task_id, hourly_rate) values (uid, tid_at, 12);
  end loop;

  uid := (select id from s7ponto.profiles where username='david');
  insert into s7ponto.task_rates(user_id, task_id, hourly_rate) values
    (uid, tid_ta, 15), (uid, tid_tr, 20)
  on conflict (user_id, task_id) do update set hourly_rate = excluded.hourly_rate;
end $$;

-- Fran: valores fixos por turno (AJUSTAR no painel se precisar)
-- Placeholder R$100 manhã/tarde/noite até confirmar valores reais.
do $$
declare
  uid uuid := (select id from s7ponto.profiles where username='fran');
begin
  delete from s7ponto.shift_rates where user_id = uid;
  insert into s7ponto.shift_rates(user_id, period, amount) values
    (uid, 'manha', 100), (uid, 'tarde', 100), (uid, 'noite', 100);
end $$;

select username, full_name, pay_mode, active
  from s7ponto.profiles
 where username in ('denison','milena','david','adriano','fran')
 order by username;
