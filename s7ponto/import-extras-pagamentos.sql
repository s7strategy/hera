-- Auto: extras + pagamentos + totais planilha
begin;

-- limpa imports anteriores destes 3
delete from s7ponto.bonus_entries
 where source = 'import'
   and user_id in (select id from s7ponto.profiles where username in ('david','denison','milena'));
delete from s7ponto.payments
 where source = 'import'
   and user_id in (select id from s7ponto.profiles where username in ('david','denison','milena'));
delete from s7ponto.sheet_month_totals
 where user_id in (select id from s7ponto.profiles where username in ('david','denison','milena'));

do $$
declare uid uuid;
begin

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-08', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0 bonus atendimento 100');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-06', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0 referente');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-06', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-06', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-05', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0 a pagar 0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-05', 'Tarefas (fixo)', 120.0, 'import', '2026-05-12 00:00:00 tarefas 00:00:00 0 120.0 120.0 multas');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-05', 'Bônus atendimento', 100.0, 'import', '2026-05-20 00:00:00 bônus atendimento 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-05', 'Bônus atendimento', 100.0, 'import', '2026-05-24 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-02', 'Bônus atendimento', 100.0, 'import', '2026-02-14 00:00:00 bônus atendimento 00:00:00 0 100.0 multas');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-02', 'Bônus atendimento', 100.0, 'import', '2026-02-22 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-03', 'Bônus atendimento', 100.0, 'import', '2026-03-21 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-04', 'Bônus atendimento', 100.0, 'import', '2026-04-18 00:00:00 bônus atendimento 00:00:00 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-02', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-01', 'Tarefas (fixo)', 80.0, 'import', '2026-01-01 00:00:00 tarefas 00:00:00 0 80.0 pago 1426');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-01', 'Bônus atendimento', 100.0, 'import', '2026-01-16 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-01', 'Bônus atendimento', 100.0, 'import', '2026-01-23 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-01', 'Bônus atendimento', 30.0, 'import', '30.0 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-12', 'Bônus atendimento', 100.0, 'import', '2025-12-09 00:00:00 bônus atendimento 00:00:00 0 100.0 nota mes:');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-12', 'Bônus atendimento', 100.0, 'import', '2025-12-26 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-11', 'Tarefas (fixo)', 70.0, 'import', '2025-11-04 00:00:00 video1 tarefas 70.0 referente');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-11', 'Bônus atendimento', 100.0, 'import', '2025-11-04 00:00:00 bônus atendimento 00:00:00 0 100.0 atendimento 1326');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-11', 'Tarefas (fixo)', 90.0, 'import', '2025-11-19 00:00:00 tarefas 00:00:00 0 90.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-11', 'Bônus atendimento', 100.0, 'import', '2025-11-27 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-10', 'Bônus atendimento', 100.0, 'import', '2025-10-10 00:00:00 bônus atendimento 00:00:00 0 100.0 atendimento 1128');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-09', 'Bônus atendimento', 150.0, 'import', '2025-09-26 00:00:00 bônus atendimento 00:00:00 0 150.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-08', 'Bônus atendimento', 150.0, 'import', '2025-08-08 00:00:00 bônus atendimento 00:00:00 0 150.0 tarefas 0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-08', 'Bônus atendimento', 100.0, 'import', '2025-08-21 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-07', 'Bônus atendimento', 100.0, 'import', '2025-07-15 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-07', 'Bônus atendimento', 60.0, 'import', 'bônus atendimento 00:00:00 0 60.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-06', 'Bônus atendimento', 150.0, 'import', '2025-06-01 00:00:00 bônus atendimento 00:00:00 0 150.0 pago 1502');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-06', 'Bônus atendimento', 100.0, 'import', '2025-06-10 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-06', 'Bônus atendimento', 20.0, 'import', '2025-06-22 00:00:00 bônus atendimento 00:00:00 0 20.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-04', 'Bônus atendimento', 100.0, 'import', '2025-04-14 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-08', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-08', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-08', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-08', 'Noite', 100.0, 'import', 'noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-08', 'Noite', 100.0, 'import', 'noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-07', 'Noite', 100.0, 'import', 'noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-07', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0 nota mes:');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-07', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-06', 'Noite', 100.0, 'import', '2026-06-23 00:00:00 noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-06', 'Noite', 100.0, 'import', 'noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-06', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-06', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-06', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-06', 'Noite', 100.0, 'import', '2026-06-23 00:00:00 noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-05', 'Noite', 100.0, 'import', 'noite 00:00:00 0 100.0 nota mes:');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-05', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-05', 'Noite', 100.0, 'import', 'noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-05', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-05', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-05', 'Noite', 100.0, 'import', 'noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-05', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-04', 'Bônus', 100.0, 'import', '2026-04-08 00:00:00 noite 00:00:00 0 100.0 bonus noite 300');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-04', 'Tarefas (fixo)', 100.0, 'import', '2026-04-08 00:00:00 tarefas 00:00:00 0 100.0 multas');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-04', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-04', 'Noite', 100.0, 'import', 'noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-04', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-04', 'Noite', 100.0, 'import', 'noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-04', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-03', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-03', 'Bônus atendimento', 100.0, 'import', '2026-03-20 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-03', 'Noite', 100.0, 'import', '2026-03-20 00:00:00 noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-03', 'Tarefas (fixo)', 100.0, 'import', '2026-03-20 00:00:00 tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-03', 'Noite', 100.0, 'import', 'noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-03', 'Tarefas (fixo)', 100.0, 'import', 'tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-03', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-02', 'Noite', 100.0, 'import', '2026-02-02 00:00:00 noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-02', 'Noite', 100.0, 'import', '2026-02-09 00:00:00 noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-02', 'Tarefas (fixo)', 100.0, 'import', '2026-02-09 00:00:00 tarefas 00:00:00 0 100.0 nota mes:');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-02', 'Bônus atendimento', 100.0, 'import', '2026-02-18 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-02', 'Noite', 100.0, 'import', '2026-02-18 00:00:00 noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-02', 'Tarefas (fixo)', 100.0, 'import', '2026-02-18 00:00:00 tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-02', 'Noite', 100.0, 'import', '2026-02-27 00:00:00 noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-02', 'Bônus atendimento', 100.0, 'import', '2026-02-27 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-02', 'Tarefas (fixo)', 100.0, 'import', '2026-02-27 00:00:00 tarefas 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-01', 'Noite', 100.0, 'import', '2026-01-03 00:00:00 noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-01', 'Bônus atendimento', 100.0, 'import', '2026-01-18 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-01', 'Noite', 100.0, 'import', '2026-01-18 00:00:00 noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-01', 'Noite', 100.0, 'import', '2026-01-26 00:00:00 noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-01', 'Bônus atendimento', 100.0, 'import', '2026-01-26 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-12', 'Noite', 100.0, 'import', '2025-12-06 00:00:00 noite 00:00:00 0 100.0 atendimento 1522');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-12', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0 nota mes:');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-12', 'Noite', 100.0, 'import', 'noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-12', 'Noite', 100.0, 'import', '2025-12-20 00:00:00 noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-12', 'Noite', 100.0, 'import', '2025-12-27 00:00:00 noite 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-12', 'Bônus atendimento', 100.0, 'import', '2025-12-27 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-11', 'Bônus atendimento', 100.0, 'import', '2025-11-05 00:00:00 bônus atendimento 00:00:00 0 100.0 tarefas 0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-11', 'Bônus atendimento', 100.0, 'import', '2025-11-28 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-08', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-08', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-07', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-07', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-06', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-06', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-05', 'Bônus atendimento', 100.0, 'import', '2026-05-21 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-05', 'Bônus atendimento', 100.0, 'import', '2026-05-28 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-03', 'Bônus atendimento', 100.0, 'import', '2026-03-21 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-03', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-03', 'Bônus atendimento', 100.0, 'import', 'bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-02', 'Bônus atendimento', 100.0, 'import', '2026-02-14 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-01', 'Bônus atendimento', 100.0, 'import', '2026-01-22 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2026-01', 'Bônus atendimento', 100.0, 'import', '2026-01-21 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.bonus_entries(user_id, year_month, title, amount, source, note)
    values (uid, '2025-12', 'Bônus atendimento', 100.0, 'import', '2025-12-27 00:00:00 bônus atendimento 00:00:00 0 100.0');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-08-16'::date, '2026-08', 100.0, 'Pagamento', '2026-08-16 00:00:00 pagamento 00:00:00 0 100.0 atendimento 720', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-08-01'::date, '2026-08', 432.0, 'Pagamento', 'pagamento 00:00:00 0 432.0 treinamento 0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-06-01'::date, '2026-06', 358.0, 'Pagamento', 'pagamento 00:00:00 0 358.0 atendimento 2145', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-06-16'::date, '2026-06', 375.0, 'Pagamento', '2026-06-16 00:00:00 pagamento 00:00:00 0 375.0 nota mes:', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-06-01'::date, '2026-06', 400.0, 'Pagamento', 'pagamento 00:00:00 0 400.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-06-01'::date, '2026-06', 280.0, 'Pagamento', 'pagamento 00:00:00 0 280.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-06-01'::date, '2026-06', 148.0, 'Pagamento', 'pagamento 00:00:00 0 148.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-06-01'::date, '2026-06', 360.0, 'Pagamento', 'pagamento 00:00:00 0 360.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-08-01'::date, '2026-08', 460.0, 'Pagamento', '2026-08-01 00:00:00 pagamento 00:00:00 0 460.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-05-01'::date, '2026-05', 388.0, 'Pagamento', 'pagamento 00:00:00 0 388.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-05-12'::date, '2026-05', 288.0, 'Pagamento', '2026-05-12 00:00:00 pagamento 00:00:00 0 288.0 treinamento 0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-05-01'::date, '2026-05', 371.0, 'Pagamento', 'pagamento 371.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-05-24'::date, '2026-05', 274.0, 'Pagamento', '2026-05-24 00:00:00 pagamento 00:00:00 0 274.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-02-06'::date, '2026-02', 228.0, 'Pagamento', '2026-02-06 00:00:00 pagamento 00:00:00 0 228.0 referente', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-02-14'::date, '2026-02', 328.0, 'Pagamento', '2026-02-14 00:00:00 pagamento 00:00:00 0 328.0 valor total 3596', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-02-22'::date, '2026-02', 328.0, 'Pagamento', '2026-02-22 00:00:00 pagamento 00:00:00 0 328.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-03-01'::date, '2026-03', 264.0, 'Pagamento', '2026-03-01 00:00:00 pagamento 00:00:00 0 264.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-03-07'::date, '2026-03', 168.0, 'Pagamento', '2026-03-07 00:00:00 pagamento 168.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-03-14'::date, '2026-03', 212.0, 'Pagamento', '2026-03-14 00:00:00 pagamento 212.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-03-21'::date, '2026-03', 344.0, 'Pagamento', '2026-03-21 00:00:00 pagamento 00:00:00 0 344.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-03-28'::date, '2026-03', 264.0, 'Pagamento', '2026-03-28 00:00:00 pagamento 264.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-04-04'::date, '2026-04', 288.0, 'Pagamento', '2026-04-04 00:00:00 pagamento 00:00:00 0 288.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-04-12'::date, '2026-04', 240.0, 'Pagamento', '2026-04-12 00:00:00 pagamento 00:00:00 0 240.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-04-18'::date, '2026-04', 316.0, 'Pagamento', '2026-04-18 00:00:00 pagamento 00:00:00 0 316.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-02-01'::date, '2026-02', 388.0, 'Pagamento', 'pagamento 00:00:00 0 388.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-01-01'::date, '2026-01', 200.0, 'Pagamento', '2026-01-01 00:00:00 pagamento 00:00:00 0 200.0 a pagar -2', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-01-08'::date, '2026-01', 168.0, 'Pagamento', '2026-01-08 00:00:00 pagamento 00:00:00 0 168.0 atendimento 924', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-01-16'::date, '2026-01', 388.0, 'Pagamento', '2026-01-16 00:00:00 pagamento 00:00:00 0 388.0 nota mes:', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-01-23'::date, '2026-01', 304.0, 'Pagamento', '2026-01-23 00:00:00 pagamento 00:00:00 0 304.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-01-01'::date, '2026-01', 366.0, 'Pagamento', 'pagamento 00:00:00 0 366.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-12-02'::date, '2025-12', 208.0, 'Pagamento', '2025-12-02 00:00:00 pagamento 00:00:00 0 208.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-12-02'::date, '2025-12', 72.0, 'Pagamento', '2025-12-02 00:00:00 pagamento 00:00:00 0 72.0 referente', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-12-09'::date, '2025-12', 422.0, 'Pagamento', '2025-12-09 00:00:00 pagamento 00:00:00 0 422.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-12-17'::date, '2025-12', 372.0, 'Pagamento', '2025-12-17 00:00:00 pagamento 00:00:00 0 372.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-12-26'::date, '2025-12', 362.0, 'Pagamento', '2025-12-26 00:00:00 pagamento 00:00:00 0 362.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-11-04'::date, '2025-11', 50.0, 'Pagamento', '2025-11-04 00:00:00 pagamento 00:00:00 0 50.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-11-05'::date, '2025-11', 366.0, 'Pagamento', '2025-11-05 00:00:00 pagamento 00:00:00 0 366.0 tarefas 160', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-11-12'::date, '2025-11', 254.0, 'Pagamento', '2025-11-12 00:00:00 pagamento 00:00:00 0 254.0 nota mes:', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-11-12'::date, '2025-11', 188.0, 'Pagamento', '2025-11-12 00:00:00 pagamento 00:00:00 0 188.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-11-19'::date, '2025-11', 383.0, 'Pagamento', '2025-11-19 00:00:00 pagamento 00:00:00 0 383.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-10-03'::date, '2025-10', 210.0, 'Pagamento', '2025-10-03 00:00:00 pagamento 00:00:00 0 210.0 pago 1336', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-10-10'::date, '2025-10', 316.0, 'Pagamento', '2025-10-10 00:00:00 pagamento 00:00:00 0 316.0 tarefas 0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-10-17'::date, '2025-10', 222.0, 'Pagamento', '2025-10-17 00:00:00 pagamento 00:00:00 0 222.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-10-24'::date, '2025-10', 306.0, 'Pagamento', '2025-10-24 00:00:00 pagamento 00:00:00 0 306.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-10-27'::date, '2025-10', 100.0, 'Pagamento', '2025-10-27 00:00:00 pagamento 00:00:00 0 100.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-10-30'::date, '2025-10', 182.0, 'Pagamento', '2025-10-30 00:00:00 pagamento 00:00:00 0 182.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-09-04'::date, '2025-09', 258.0, 'Pagamento', '2025-09-04 00:00:00 pagamento 00:00:00 0 258.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-09-11'::date, '2025-09', 316.0, 'Pagamento', '2025-09-11 00:00:00 pagamento 00:00:00 0 316.0 multas', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-09-18'::date, '2025-09', 222.0, 'Pagamento', '2025-09-18 00:00:00 pagamento 00:00:00 0 222.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-09-22'::date, '2025-09', 50.0, 'Pagamento', '2025-09-22 00:00:00 pagamento 00:00:00 0 50.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-09-26'::date, '2025-09', 234.0, 'Pagamento', '2025-09-26 00:00:00 pagamento 00:00:00 0 234.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-08-04'::date, '2025-08', 150.0, 'Pagamento', '2025-08-04 00:00:00 pagamento 00:00:00 0 150.0 atendimento 1074', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-08-08'::date, '2025-08', 378.0, 'Pagamento', '2025-08-08 00:00:00 pagamento 00:00:00 0 378.0 bonus atendimento 250', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-08-14'::date, '2025-08', 210.0, 'Pagamento', '2025-08-14 00:00:00 pagamento 00:00:00 0 210.0 nota mes:', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-08-21'::date, '2025-08', 316.0, 'Pagamento', '2025-08-21 00:00:00 pagamento 00:00:00 0 316.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-08-28'::date, '2025-08', 222.0, 'Pagamento', '2025-08-28 00:00:00 pagamento 00:00:00 0 222.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-07-01'::date, '2025-07', 412.0, 'Pagamento', '2025-07-01 00:00:00 pagamento 00:00:00 0 412.0 a pagar 48', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-07-06'::date, '2025-07', 120.0, 'Pagamento', '2025-07-06 00:00:00 pagamento 00:00:00 0 120.0 multas', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-07-08'::date, '2025-07', 316.0, 'Pagamento', '2025-07-08 00:00:00 pagamento 00:00:00 0 316.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-07-15'::date, '2025-07', 322.0, 'Pagamento', '2025-07-15 00:00:00 pagamento 00:00:00 0 322.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-07-22'::date, '2025-07', 414.0, 'Pagamento', '2025-07-22 00:00:00 pagamento 00:00:00 0 414.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-07-01'::date, '2025-07', 480.0, 'Pagamento', 'pagamento 00:00:00 0 480.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-06-03'::date, '2025-06', 448.0, 'Pagamento', '2025-06-03 00:00:00 pagamento 00:00:00 0 448.0 referente', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-06-11'::date, '2025-06', 448.0, 'Pagamento', '2025-06-11 00:00:00 pagamento 00:00:00 0 448.0 nota mes:', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-06-16'::date, '2025-06', 156.0, 'Pagamento', '2025-06-16 00:00:00 pagamento 00:00:00 0 156.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-06-24'::date, '2025-06', 450.0, 'Pagamento', '2025-06-24 00:00:00 pagamento 00:00:00 0 450.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-05-05'::date, '2025-05', 189.46, 'Pagamento', '2025-05-05 00:00:00 pagamento 00:00:00 0 189.46', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-05-07'::date, '2025-05', 80.0, 'Pagamento', '2025-05-07 00:00:00 pagamento 00:00:00 0 80.0 atendimento 1215', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-05-13'::date, '2025-05', 290.7, 'Pagamento', '2025-05-13 00:00:00 pagamento 00:00:00 0 290.7 nota mes:', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-05-17'::date, '2025-05', 110.0, 'Pagamento', '2025-05-17 00:00:00 pagamento 00:00:00 0 110.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-05-20'::date, '2025-05', 289.3, 'Pagamento', '2025-05-20 00:00:00 pagamento 00:00:00 0 289.3', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-05-27'::date, '2025-05', 261.0, 'Pagamento', '2025-05-27 00:00:00 pagamento 00:00:00 0 261.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-04-02'::date, '2025-04', 291.07, 'Pagamento', '2025-04-02 00:00:00 pagamento 00:00:00 0 291.07', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-04-03'::date, '2025-04', 150.0, 'Pagamento', '2025-04-03 00:00:00 pagamento 00:00:00 0 150.0 referente', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-04-08'::date, '2025-04', 164.36, 'Pagamento', '2025-04-08 00:00:00 pagamento 00:00:00 0 164.36 bonus atendimento 100', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-04-16'::date, '2025-04', 428.0, 'Pagamento', '2025-04-16 00:00:00 pagamento 00:00:00 0 428', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-04-24'::date, '2025-04', 201.31, 'Pagamento', '2025-04-24 00:00:00 pagamento 00:00:00 0 201.31', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-04-25'::date, '2025-04', 92.69, 'Pagamento', '2025-04-25 00:00:00 pagamento 00:00:00 0 92.69', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-04-30'::date, '2025-04', 230.54, 'Pagamento', '2025-04-30 00:00:00 pagamento 00:00:00 0 230.54', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-03-07'::date, '2025-03', 263.75, 'Pagamento', '2025-03-07 00:00:00 pagamento 00:00:00 0 263.75 tarefas 381', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-03-14'::date, '2025-03', 292.25, 'Pagamento', '2025-03-14 00:00:00 pagamento 00:00:00 0 292.25', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-03-19'::date, '2025-03', 215.97, 'Pagamento', '2025-03-19 00:00:00 pagamento 00:00:00 0 215.97', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-03-27'::date, '2025-03', 255.6, 'Pagamento', '2025-03-27 00:00:00 pagamento 00:00:00 0 255.6', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-02-28'::date, '2025-02', 123.0, 'Pagamento', '2025-02-28 00:00:00 pagamento 00:00:00 0 123.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-08-01'::date, '2026-08', 380.0, 'Pagamento', 'pagamento 00:00:00 0 380.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-08-01'::date, '2026-08', 250.0, 'Pagamento', 'pagamento 00:00:00 0 250.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-08-01'::date, '2026-08', 400.0, 'Pagamento', 'pagamento 00:00:00 0 400.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-07-01'::date, '2026-07', 1100.0, 'Pagamento', 'pagamento 00:00:00 0 1100.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-07-01'::date, '2026-07', 900.0, 'Pagamento', 'pagamento pagamento 00:00:00 0 900.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-06-01'::date, '2026-06', 100.0, 'Pagamento', 'pagamento 00:00:00 0 100.0 nota mes:', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-06-21'::date, '2026-06', 900.0, 'Pagamento', '2026-06-21 00:00:00 pagamento 00:00:00 0 900.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-06-01'::date, '2026-06', 824.0, 'Pagamento', 'pagamento 00:00:00 0 824.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-05-01'::date, '2026-05', 850.0, 'Pagamento', 'pagamento 00:00:00 0 850.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-05-01'::date, '2026-05', 788.0, 'Pagamento', 'pagamento 00:00:00 0 788.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-05-01'::date, '2026-05', 642.0, 'Pagamento', 'pagamento 00:00:00 0 642.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-04-08'::date, '2026-04', 680.0, 'Pagamento', '2026-04-08 00:00:00 pagamento 00:00:00 0 680.0 valor total 2146.8', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-04-01'::date, '2026-04', 900.0, 'Pagamento', 'pagamento 00:00:00 0 900.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-04-01'::date, '2026-04', 620.0, 'Pagamento', 'pagamento 00:00:00 0 620.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-03-11'::date, '2026-03', 788.0, 'Pagamento', '2026-03-11 00:00:00 pagamento 00:00:00 0 788.0 nota mes:', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-03-20'::date, '2026-03', 843.0, 'Pagamento', '2026-03-20 00:00:00 pagamento 00:00:00 0 843.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-03-01'::date, '2026-03', 720.0, 'Pagamento', 'pagamento 00:00:00 0 720.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-02-02'::date, '2026-02', 566.0, 'Pagamento', '2026-02-02 00:00:00 pagamento 00:00:00 0 566.0 referente', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-02-09'::date, '2026-02', 478.0, 'Pagamento', '2026-02-09 00:00:00 pagamento 00:00:00 0 478.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-02-18'::date, '2026-02', 590.0, 'Pagamento', '2026-02-18 00:00:00 pagamento 00:00:00 0 590.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-02-27'::date, '2026-02', 865.0, 'Pagamento', '2026-02-27 00:00:00 pagamento 00:00:00 0 865.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-01-03'::date, '2026-01', 328.0, 'Pagamento', '2026-01-03 00:00:00 pagamento 00:00:00 0 328.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-01-10'::date, '2026-01', 560.0, 'Pagamento', '2026-01-10 00:00:00 pagamento 00:00:00 0 560.0 nota mes:', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-01-18'::date, '2026-01', 660.0, 'Pagamento', '2026-01-18 00:00:00 pagamento 00:00:00 0 660.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-01-26'::date, '2026-01', 611.0, 'Pagamento', '2026-01-26 00:00:00 pagamento 00:00:00 0 611.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-12-06'::date, '2025-12', 572.0, 'Pagamento', '2025-12-06 00:00:00 pagamento 00:00:00 0 572.0 tarefas 0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-12-13'::date, '2025-12', 574.0, 'Pagamento', '2025-12-13 00:00:00 pagamento 00:00:00 0 574.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-12-20'::date, '2025-12', 500.0, 'Pagamento', '2025-12-20 00:00:00 pagamento 00:00:00 0 500.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-12-27'::date, '2025-12', 488.8, 'Pagamento', '2025-12-27 00:00:00 pagamento 00:00:00 0 488.8', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-11-02'::date, '2025-11', 500.0, 'Pagamento', '2025-11-02 00:00:00 pagamento 00:00:00 0 500.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-11-01'::date, '2025-11', 25.0, 'Pagamento', '2025-04-02 00:00:00 pagamento 1774-09-27 00:00:00 -1097976 25.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-11-05'::date, '2025-11', 257.2, 'Pagamento', '2025-11-05 00:00:00 pagamento 00:00:00 0 257.2 bonus atendimento 200', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-11-05'::date, '2025-11', 25.0, 'Pagamento', '2025-11-05 00:00:00 2025-04-03 00:00:00 pagamento 1774-09-26 00:00:00 -1098000 25.0 multas', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-11-12'::date, '2025-11', 410.0, 'Pagamento', '2025-11-12 00:00:00 pagamento 00:00:00 0 410.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-11-15'::date, '2025-11', 120.0, 'Pagamento', '2025-11-15 00:00:00 pagamento 00:00:00 0 120.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-11-20'::date, '2025-11', 438.0, 'Pagamento', '2025-11-20 00:00:00 pagamento 00:00:00 0 438.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-11-28'::date, '2025-11', 25.0, 'Pagamento', '2025-11-28 00:00:00 2025-04-04 00:00:00 pagamento 1774-09-25 00:00:00 -1098024 25.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-11-28'::date, '2025-11', 436.2, 'Pagamento', '2025-11-28 00:00:00 pagamento 00:00:00 0 436.2', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-10-01'::date, '2025-10', 1100.2, 'Pagamento', 'pagamento 00:00:00 0 total 1100.2', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-10-01'::date, '2025-10', 350.0, 'Pagamento', 'pagamento 00:00:00 0 350.0 tarefas 0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-10-25'::date, '2025-10', 328.0, 'Pagamento', '2025-10-25 00:00:00 pagamento 00:00:00 0 328.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-10-25'::date, '2025-10', 25.0, 'Pagamento', '2025-10-25 00:00:00 2025-04-01 00:00:00 pagamento 1774-09-28 00:00:00 -1097952 25.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-08-25'::date, '2026-08', 800.0, 'Pagamento', '2026-08-25 00:00:00 pagamento 00:00:00 0 800.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-08-25'::date, '2026-08', 600.0, 'Pagamento', '2026-08-25 00:00:00 pagamento 00:00:00 0 600.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-07-03'::date, '2026-07', 573.0, 'Pagamento', '2026-07-03 00:00:00 pagamento 00:00:00 0 573.0 pago 2343', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-07-12'::date, '2026-07', 970.0, 'Pagamento', '2026-07-12 00:00:00 pagamento 00:00:00 0 970.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-06-17'::date, '2026-06', 1300.0, 'Pagamento', '2026-06-17 00:00:00 pagamento 00:00:00 0 1300.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-05-16'::date, '2026-05', 600.0, 'Pagamento', '2026-05-16 00:00:00 pagamento 00:00:00 0 600.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-05-28'::date, '2026-05', 780.0, 'Pagamento', '2026-05-28 00:00:00 pagamento 00:00:00 0 780.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-03-02'::date, '2026-03', 597.87, 'Pagamento', '2026-03-02 00:00:00 pagamento 00:00:00 0 597.87 bonus atendimento 300', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-03-11'::date, '2026-03', 369.0, 'Pagamento', '2026-03-11 00:00:00 pagamento 00:00:00 0 369.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-03-21'::date, '2026-03', 507.0, 'Pagamento', '2026-03-21 00:00:00 pagamento 00:00:00 0 507.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-04-02'::date, '2026-04', 452.0, 'Pagamento', '2026-04-02 00:00:00 pagamento 00:00:00 0 452.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-04-12'::date, '2026-04', 439.0, 'Pagamento', '2026-04-12 00:00:00 pagamento 00:00:00 0 439.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-03-01'::date, '2026-03', 676.0, 'Pagamento', 'pagamento 00:00:00 0 676.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-02-06'::date, '2026-02', 354.0, 'Pagamento', '2026-02-06 00:00:00 pagamento 00:00:00 0 354.0 tarefas 0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-02-14'::date, '2026-02', 435.0, 'Pagamento', '2026-02-14 00:00:00 pagamento 00:00:00 0 435.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-01-22'::date, '2026-01', 388.33, 'Pagamento', '2026-01-22 00:00:00 pagamento 00:00:00 0 388.33', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-01-05'::date, '2026-01', 350.0, 'Pagamento', '2026-01-05 00:00:00 pagamento 00:00:00 0 350.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-01-12'::date, '2026-01', 336.4, 'Pagamento', '2026-01-12 00:00:00 pagamento 00:00:00 0 336.4', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-01-21'::date, '2026-01', 436.0, 'Pagamento', '2026-01-21 00:00:00 pagamento 00:00:00 0 436.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2026-01-29'::date, '2026-01', 337.0, 'Pagamento', '2026-01-29 00:00:00 pagamento 00:00:00 0 337.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-12-13'::date, '2025-12', 234.0, 'Pagamento', '2025-12-13 00:00:00 pagamento 00:00:00 0 234.0 tarefas 0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-12-20'::date, '2025-12', 228.0, 'Pagamento', '2025-12-20 00:00:00 pagamento 00:00:00 0 228.0 nota mes:', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.payments(user_id, paid_on, year_month, amount, title, note, source)
    values (uid, '2025-12-28'::date, '2025-12', 350.0, 'Pagamento', '2025-12-28 00:00:00 pagamento 00:00:00 0 350.0', 'import');
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-08', 820.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-05', 1459.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-06', 1258.5, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-07', 1008.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-02', 1200.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-03', 1156.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-04', 1240.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-01', 1234.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-12', 1412.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-11', 1686.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-10', 1228.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-09', 1040.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-08', 1324.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-07', 1666.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-06', 1778.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-05', 1275.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-04', 1262.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-03', 1311.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-02', 151.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-08', 1940.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-07', 2009.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-06', 2256.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-05', 2345.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-04', 2146.8, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-03', 2251.8, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-02', 2303.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-01', 1947.6, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-12', 2122.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-11', 1960.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-10', 1034.2, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'denison');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2010-10', 66.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-07', 1928.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-08', 1608.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-06', 1912.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-05', 1607.93333333, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-02', 1353.2, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-03', 1757.0666667, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-04', 1056.0, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2026-01', 1401.33333333, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;

  uid := (select id from s7ponto.profiles where username = 'milena');
  if uid is not null then
    insert into s7ponto.sheet_month_totals(user_id, year_month, expected_total, note, source)
    values (uid, '2025-12', 1018.4, 'total planilha (trabalho+extras)', 'import')
    on conflict (user_id, year_month) do update
      set expected_total = excluded.expected_total, note = excluded.note;
  end if;
end $$;
commit;

select 'bonus_import' as k, count(*) from s7ponto.bonus_entries where source='import'
union all select 'payments_import', count(*) from s7ponto.payments where source='import'
union all select 'sheet_totals', count(*) from s7ponto.sheet_month_totals;
