-- David: aba AGOSTO (cola 26/08/2026) tem A PAGAR = R$ 288 e saldo anterior 0.
-- O R$ 460 com data 01/08 está na aba JUNHO (entra no PAGO 2.381 daquela aba,
-- não nos 532 de agosto). Outros furos do xlsx entram abaixo; o resto vira
-- um ajuste em julho para o saldo que agosto puxa ficar R$ 0.
begin;

-- Pagamento da aba junho, datado 01/08, estava no year_month de agosto.
update s7ponto.payments p
   set year_month = '2026-06'
  from s7ponto.profiles pr
 where p.user_id = pr.id
   and pr.username = 'david'
   and p.id = '5b50d501-1e6b-4f8c-807f-9e7505da78ce'
   and p.amount = 460
   and p.year_month = '2026-08';

-- Janeiro: A27=30 foi lido como valor; na aba o bônus é R$ 100.
update s7ponto.bonus_entries
   set amount = 100,
       note = 'conferencia-planilha-20260826-david jan bonus 100 (era 30)'
 where id = '2bb78151-cd7c-43bd-a7e4-b36847f61dd9'
   and amount = 30;

-- 17/11 escrito "17//11" — import pulou (16:00–22:00, R$ 72).
insert into s7ponto.shifts (
  user_id, company_id, company_name, period, pay_mode,
  started_at, ended_at, source, note
)
select pr.id,
       '1a12cb07-1a59-4e59-a4f8-11d446ff07df',
       'Cineplay', 'tarde', 'hourly',
       timestamptz '2025-11-17 16:00:00 America/Sao_Paulo',
       timestamptz '2025-11-17 22:00:00 America/Sao_Paulo',
       'import',
       'conferencia-planilha-20260826-david nov 17//11'
  from s7ponto.profiles pr
 where pr.username = 'david'
   and not exists (
     select 1 from s7ponto.shifts s
      where s.user_id = pr.id
        and (s.started_at at time zone 'America/Sao_Paulo')::date = date '2025-11-17'
   );

insert into s7ponto.segments (
  shift_id, task_id, task_name, hourly_rate, period, started_at, ended_at
)
select s.id,
       '1e32ff4d-7614-4422-9b99-877e959a8c6f',
       'Atendimento', 12.00, 'tarde',
       s.started_at, s.ended_at
  from s7ponto.shifts s
  join s7ponto.profiles pr on pr.id = s.user_id and pr.username = 'david'
 where (s.started_at at time zone 'America/Sao_Paulo')::date = date '2025-11-17'
   and not exists (
     select 1 from s7ponto.segments g where g.shift_id = s.id
   );

insert into s7ponto.bonus_entries (user_id, year_month, title, amount, source, note, bonus_on)
select pr.id, v.year_month, v.title, v.amount, 'import', v.note, v.bonus_on
  from s7ponto.profiles pr
  cross join (values
    ('2025-07', 'Bônus atendimento', 100.00, 'conferencia-planilha-20260826-david jul25 bonus', date '2025-07-08'),
    ('2025-09', 'Bônus atendimento', 100.00, 'conferencia-planilha-20260826-david set25 bonus', date '2025-09-11')
  ) as v(year_month, title, amount, note, bonus_on)
 where pr.username = 'david'
   and not exists (
     select 1 from s7ponto.bonus_entries b
      where b.user_id = pr.id and b.note = v.note
   );

-- Novembro H31=349 em linha SELECIONAR (entra no PAGO 1.590 da aba).
insert into s7ponto.payments (user_id, paid_on, year_month, amount, title, note, source)
select pr.id, date '2025-11-27', '2025-11', 349.00, 'Pagamento',
       'conferencia-planilha-20260826-david nov pago-349', 'import'
  from s7ponto.profiles pr
 where pr.username = 'david'
   and not exists (
     select 1 from s7ponto.payments p
      where p.user_id = pr.id
        and p.note = 'conferencia-planilha-20260826-david nov pago-349'
   );

-- Aba agosto puxa R$ 0. Fecha julho nesse valor.
do $$
declare
  uid uuid;
  carry numeric;
begin
  uid := (select id from s7ponto.profiles where username = 'david');
  if uid is null then return; end if;

  with trabalho as (
    select to_char(g.started_at at time zone 'America/Sao_Paulo', 'YYYY-MM') ym,
           round(sum(
             case when g.flat_amount is not null then g.flat_amount
                  else g.hourly_rate * extract(epoch from (g.ended_at - g.started_at))/3600.0
             end
           )::numeric, 2) v
      from s7ponto.segments g
      join s7ponto.shifts s on s.id = g.shift_id
     where s.user_id = uid and g.ended_at is not null
     group by 1
  ),
  bonus as (
    select year_month ym, round(sum(amount), 2) v
      from s7ponto.bonus_entries where user_id = uid group by 1
  ),
  pago as (
    select year_month ym, round(sum(amount), 2) v
      from s7ponto.payments where user_id = uid group by 1
  )
  select round(coalesce(sum(
           coalesce(t.v,0) + coalesce(b.v,0) - coalesce(p.v,0)
         ), 0), 2)
    into carry
    from (select ym from trabalho union select ym from bonus union select ym from pago) m
    left join trabalho t using (ym)
    left join bonus b using (ym)
    left join pago p using (ym)
   where m.ym < '2026-08';

  carry := coalesce(carry, 0);

  if carry > 0.004 then
    insert into s7ponto.payments (user_id, paid_on, year_month, amount, title, note, source)
    values (uid, date '2026-07-31', '2026-07', carry, 'Ajuste',
            'conferencia-planilha-20260826-david ajuste julho p/ saldo ago=0', 'import');
  elsif carry < -0.004 then
    insert into s7ponto.bonus_entries (user_id, year_month, title, amount, source, note, bonus_on)
    values (uid, '2026-07', 'Saldo conferido da planilha', abs(carry), 'import',
            'conferencia-planilha-20260826-david ajuste julho p/ saldo ago=0', date '2026-07-31');
  end if;
end $$;

commit;
notify pgrst, 'reload schema';
