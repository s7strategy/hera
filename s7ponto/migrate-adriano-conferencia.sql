-- Adriano: furos que sobraram depois do import, para bater com a planilha.
-- Agosto já estava certo (A PAGAR 501,53). Junho perdia R$ 1; julho tinha
-- R$ 14 a mais que o TOTAL MÊS 930,03; dezembro tinha 3 aparelhos com G=0.
begin;

-- Junho R38: 23:23–23:28 planilha créditos sem data (depois do 11/06 22:52).
insert into s7ponto.shifts (
  user_id, company_id, company_name, period, pay_mode,
  started_at, ended_at, source, note
)
select pr.id,
       '36ac470d-c5d2-4bc7-afb4-1db3c159e19f',
       'S7', 'noite', 'hourly',
       timestamptz '2026-06-11 23:23:00 America/Sao_Paulo',
       timestamptz '2026-06-11 23:28:00 America/Sao_Paulo',
       'import',
       'conferencia-planilha-20260826-adriano jun R38 sem data'
  from s7ponto.profiles pr
 where pr.username = 'adriano'
   and not exists (
     select 1 from s7ponto.shifts s
      where s.user_id = pr.id
        and s.started_at = timestamptz '2026-06-11 23:23:00 America/Sao_Paulo'
   );

insert into s7ponto.segments (
  shift_id, task_id, task_name, hourly_rate, period, started_at, ended_at
)
select s.id, t.id, t.name, 12.00, s.period, s.started_at, s.ended_at
  from s7ponto.shifts s
  join s7ponto.profiles pr on pr.id = s.user_id and pr.username = 'adriano'
  join s7ponto.tasks t on t.name = 'Planilha créditos'
 where s.started_at = timestamptz '2026-06-11 23:23:00 America/Sao_Paulo'
   and not exists (select 1 from s7ponto.segments g where g.shift_id = s.id);

-- Julho R81: 17:13–17:41 aparelhos. Na planilha o G foi colado 10 (não 14).
update s7ponto.segments
   set hourly_rate = 0, flat_amount = 10.00
 where id = '16a87b25-1423-4f8d-ba34-c13f13979bf5'
   and hourly_rate = 30;

-- Julho aquecimento dia 4: G=0 na planilha (não entra no 920,03).
delete from s7ponto.bonus_entries
 where id = 'c32568f5-a148-49f9-a6b5-f58d0e1a35dd';

-- Dezembro: aparelhos com G=0 (ligar celular em cima de outro ponto).
delete from s7ponto.shifts
 where id in (
   'fbb53b52-187f-43c0-84cc-ff9b67e905fb',
   'ec32105c-9a42-4537-85b7-ed919b8e2bc1',
   '6b4965f6-613d-4fde-87b3-8456d31681fe'
 );

-- Recalcula o ajuste de julho para agosto continuar em R$ 501,53.
delete from s7ponto.payments
 where user_id = (select id from s7ponto.profiles where username = 'adriano')
   and title = 'Ajuste'
   and year_month = '2026-07'
   and source = 'import';

do $$
declare
  uid uuid;
  disp numeric;
  alvo numeric := 501.53;
  delta numeric;
begin
  uid := (select id from s7ponto.profiles where username = 'adriano');
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
    into disp
    from (select ym from trabalho union select ym from bonus union select ym from pago) m
    left join trabalho t using (ym)
    left join bonus b using (ym)
    left join pago p using (ym)
   where m.ym <= '2026-08';

  delta := round(coalesce(disp, 0) - alvo, 2);

  if delta > 0.004 then
    insert into s7ponto.payments (user_id, paid_on, year_month, amount, title, note, source)
    values (uid, date '2026-07-31', '2026-07', delta, 'Ajuste',
            'conferencia-planilha-20260826-adriano ajuste p/ ago 501.53', 'import');
  elsif delta < -0.004 then
    insert into s7ponto.bonus_entries (user_id, year_month, title, amount, source, note, bonus_on)
    values (uid, '2026-07', 'Saldo conferido da planilha', abs(delta), 'import',
            'conferencia-planilha-20260826-adriano ajuste p/ ago 501.53', date '2026-07-31');
  end if;
end $$;

update s7ponto.sheet_month_totals t
   set expected_total = v.total,
       note = 'conferencia-planilha-20260826-adriano trabalho+bônus'
  from (values
    ('2025-12', 946.00),
    ('2026-06', 639.20),
    ('2026-07', 930.03)
  ) as v(ym, total)
  join s7ponto.profiles pr on pr.username = 'adriano'
 where t.user_id = pr.id and t.year_month = v.ym;

commit;
notify pgrst, 'reload schema';
