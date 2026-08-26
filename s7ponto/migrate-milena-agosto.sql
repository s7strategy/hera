-- Milena: aba AGOSTO (cola 26/08/2026) tem A PAGAR = R$ 729,33.
-- Os dias 23–31/jul ficam em julho (data certa); a planilha soma eles em agosto.
-- Turnos com data digitada errada (17/fve, 28/fe, 08a/abr, 30/abri, tarde de 13/jun)
-- entram abaixo. O pagamento/bônus de 22/jan que está na aba fevereiro vai para
-- fevereiro. O R$ 800 em SELECIONAR na aba julho é o mesmo 800 de 25/ago — não duplica.
begin;

-- 22/jan na aba FEVEREIRO (PAGO 1.177,33 e bônus 200 daquela aba).
update s7ponto.payments p
   set year_month = '2026-02'
  from s7ponto.profiles pr
 where p.user_id = pr.id
   and pr.username = 'milena'
   and p.id = 'fac9fa37-debd-4c97-bf56-c9b040c8a0b4'
   and p.year_month = '2026-01';

update s7ponto.bonus_entries b
   set year_month = '2026-02',
       bonus_on   = date '2026-01-22'
  from s7ponto.profiles pr
 where b.user_id = pr.id
   and pr.username = 'milena'
   and b.id = '9c1c4b0b-f979-4ce8-8090-21c5839d2567'
   and b.year_month = '2026-01';

insert into s7ponto.shifts (
  user_id, company_id, company_name, period, pay_mode,
  started_at, ended_at, source, note
)
select pr.id,
       '1a12cb07-1a59-4e59-a4f8-11d446ff07df',
       'Cineplay', v.period, 'hourly',
       v.ini, v.fim, 'import', v.note
  from s7ponto.profiles pr
  cross join (values
    (timestamptz '2026-02-17 09:00:00 America/Sao_Paulo',
     timestamptz '2026-02-17 13:00:00 America/Sao_Paulo',
     'manha', 'conferencia-planilha-20260826-milena 17/fve'),
    (timestamptz '2026-02-28 09:00:00 America/Sao_Paulo',
     timestamptz '2026-02-28 10:50:00 America/Sao_Paulo',
     'manha', 'conferencia-planilha-20260826-milena 28/fe'),
    (timestamptz '2026-04-08 14:04:00 America/Sao_Paulo',
     timestamptz '2026-04-08 16:00:00 America/Sao_Paulo',
     'tarde', 'conferencia-planilha-20260826-milena 08a/abr'),
    (timestamptz '2026-04-30 09:00:00 America/Sao_Paulo',
     timestamptz '2026-04-30 13:00:00 America/Sao_Paulo',
     'manha', 'conferencia-planilha-20260826-milena 30/abri'),
    (timestamptz '2026-06-13 13:35:00 America/Sao_Paulo',
     timestamptz '2026-06-13 16:00:00 America/Sao_Paulo',
     'tarde', 'conferencia-planilha-20260826-milena 13/jun tarde')
  ) as v(ini, fim, period, note)
 where pr.username = 'milena'
   and not exists (
     select 1 from s7ponto.shifts s
      where s.user_id = pr.id
        and s.started_at = v.ini
   );

insert into s7ponto.segments (
  shift_id, task_id, task_name, hourly_rate, period, started_at, ended_at
)
select s.id,
       '1e32ff4d-7614-4422-9b99-877e959a8c6f',
       'Atendimento', 12.00, s.period,
       s.started_at, s.ended_at
  from s7ponto.shifts s
  join s7ponto.profiles pr on pr.id = s.user_id and pr.username = 'milena'
 where s.note like 'conferencia-planilha-20260826-milena%'
   and not exists (
     select 1 from s7ponto.segments g where g.shift_id = s.id
   );

-- Fecha agosto em R$ 729,33 (A PAGAR da aba).
do $$
declare
  uid uuid;
  disp numeric;
  alvo numeric := 729.33;
  delta numeric;
begin
  uid := (select id from s7ponto.profiles where username = 'milena');
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
            'conferencia-planilha-20260826-milena ajuste p/ ago 729.33', 'import');
  elsif delta < -0.004 then
    insert into s7ponto.bonus_entries (user_id, year_month, title, amount, source, note, bonus_on)
    values (uid, '2026-07', 'Saldo conferido da planilha', abs(delta), 'import',
            'conferencia-planilha-20260826-milena ajuste p/ ago 729.33', date '2026-07-31');
  end if;
end $$;

commit;
notify pgrst, 'reload schema';
