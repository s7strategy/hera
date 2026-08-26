-- Denison: a aba de agosto (cola de 26/08/2026) tem A PAGAR = R$ 1.823.
-- A planilha .xlsx em disco ainda está na versão antiga (A PAGAR 1.523).
-- Também completa extras/pagamentos/turnos que o import pulou (SELECIONAR,
-- data "13//04", dia 7 de junho gravado como 7 de maio).
begin;

-- Turno de teste no app (25/08 18:56, R$ 0,07) não está na planilha.
delete from s7ponto.shifts
 where id = 'a027a952-c8d9-4e92-8b7b-508b270f7169';

-- Aba junho, linha 8: data Excel 2026-05-07 (typo) — é 07/jun, 16:00–22:00.
update s7ponto.shifts
   set started_at = started_at + interval '31 days',
       ended_at   = ended_at   + interval '31 days'
 where id = 'a8bd3687-feaf-45c7-9813-fb0e5410b41b'
   and (started_at at time zone 'America/Sao_Paulo')::date = date '2026-05-07';

update s7ponto.segments
   set started_at = started_at + interval '31 days',
       ended_at   = ended_at   + interval '31 days'
 where shift_id = 'a8bd3687-feaf-45c7-9813-fb0e5410b41b'
   and (started_at at time zone 'America/Sao_Paulo')::date = date '2026-05-07';

-- Abril linha 17: data escrita "13//04" — o import pulou o dia 13 (5h × R$12 = R$60).
insert into s7ponto.shifts (
  user_id, company_id, company_name, period, pay_mode,
  started_at, ended_at, source, note
)
select pr.id,
       '1a12cb07-1a59-4e59-a4f8-11d446ff07df',
       'Cineplay', 'noite', 'hourly',
       timestamptz '2026-04-13 18:00:00 America/Sao_Paulo',
       timestamptz '2026-04-13 23:00:00 America/Sao_Paulo',
       'import',
       'conferencia-planilha-20260826 abril 13//04'
  from s7ponto.profiles pr
 where pr.username = 'denison'
   and not exists (
     select 1 from s7ponto.shifts s
      where s.user_id = pr.id
        and (s.started_at at time zone 'America/Sao_Paulo')::date = date '2026-04-13'
   );

insert into s7ponto.segments (
  shift_id, task_id, task_name, hourly_rate, period, started_at, ended_at
)
select s.id,
       '1e32ff4d-7614-4422-9b99-877e959a8c6f',
       'Atendimento', 12.00, 'noite',
       s.started_at, s.ended_at
  from s7ponto.shifts s
  join s7ponto.profiles pr on pr.id = s.user_id and pr.username = 'denison'
 where (s.started_at at time zone 'America/Sao_Paulo')::date = date '2026-04-13'
   and not exists (
     select 1 from s7ponto.segments g where g.shift_id = s.id
   );

-- O lote de R$ 618,80 só servia para forçar julho = 613. Os furos reais
-- entram abaixo; o resto (R$ 1,20 de arredondamento da planilha) vira pagamento.
delete from s7ponto.bonus_entries b
 using s7ponto.profiles pr
 where b.user_id = pr.id
   and pr.username = 'denison'
   and b.title = 'Saldo conferido da planilha'
   and b.year_month = '2026-07';

insert into s7ponto.bonus_entries (user_id, year_month, title, amount, source, note, bonus_on)
select pr.id, v.year_month, v.title, v.amount, 'import', v.note, v.bonus_on
  from s7ponto.profiles pr
  cross join (values
    -- Janeiro: 4× Noite na aba; import trouxe 3. + 3× R$100 em linha SELECIONAR (tarefas).
    ('2026-01', 'Noite',            100.00, 'conferencia-planilha-20260826 jan noite',              date '2026-01-03'),
    ('2026-01', 'Tarefas (fixo)',   100.00, 'conferencia-planilha-20260826 jan selecionar-10',      date '2026-01-10'),
    ('2026-01', 'Tarefas (fixo)',   100.00, 'conferencia-planilha-20260826 jan selecionar-18',      date '2026-01-18'),
    ('2026-01', 'Tarefas (fixo)',   100.00, 'conferencia-planilha-20260826 jan selecionar-26',      date '2026-01-26'),
    -- Fevereiro: G6=100 em SELECIONAR (entra no TOTAL da aba).
    ('2026-02', 'Tarefas (fixo)',   100.00, 'conferencia-planilha-20260826 fev selecionar-02',      date '2026-02-02'),
    -- Março: 3× Noite na aba; import trouxe 2.
    ('2026-03', 'Noite',            100.00, 'conferencia-planilha-20260826 mar noite',              date '2026-03-01'),
    -- Julho: 2× Noite na aba; import trouxe 1.
    ('2026-07', 'Noite',            100.00, 'conferencia-planilha-20260826 jul noite',              date '2026-07-01'),
    -- Agosto atualizado: +1 atendimento, +1 tarefas, +1 noite (depois do dia 25).
    ('2026-08', 'Bônus atendimento',100.00, 'conferencia-planilha-20260826 ago bonus at',           date '2026-08-25'),
    ('2026-08', 'Tarefas (fixo)',   100.00, 'conferencia-planilha-20260826 ago tarefas',            date '2026-08-25'),
    ('2026-08', 'Noite',            100.00, 'conferencia-planilha-20260826 ago noite',              date '2026-08-25')
  ) as v(year_month, title, amount, note, bonus_on)
 where pr.username = 'denison'
   and not exists (
     select 1 from s7ponto.bonus_entries b
      where b.user_id = pr.id and b.note = v.note
   );

insert into s7ponto.payments (user_id, paid_on, year_month, amount, title, note, source)
select pr.id, v.paid_on, v.year_month, v.amount, v.title, v.note, 'import'
  from s7ponto.profiles pr
  cross join (values
    -- Janeiro I35=50 em linha SELECIONAR (entra no PAGO da aba).
    (date '2026-01-26', '2026-01', 50.00,  'Pagamento', 'conferencia-planilha-20260826 jan pago-50'),
    -- Fevereiro H16=90 em linha SELECIONAR (PAGO 2589 = 2499 + 90).
    (date '2026-02-09', '2026-02', 90.00,  'Pagamento', 'conferencia-planilha-20260826 fev pago-90'),
    -- Planilha arredonda jan 246,60→246 e não puxa R$ 0,60 de maio em junho.
    (date '2026-07-31', '2026-07',  1.20,  'Ajuste',    'conferencia-planilha-20260826 ajuste 1.20')
  ) as v(paid_on, year_month, amount, title, note)
 where pr.username = 'denison'
   and not exists (
     select 1 from s7ponto.payments p
      where p.user_id = pr.id and p.note = v.note
   );

-- Abril: o 3º "Noite" veio como título genérico "Bônus".
update s7ponto.bonus_entries b
   set title = 'Noite'
  from s7ponto.profiles pr
 where b.user_id = pr.id
   and pr.username = 'denison'
   and b.year_month = '2026-04'
   and b.title = 'Bônus'
   and b.amount = 100;

commit;
notify pgrst, 'reload schema';
