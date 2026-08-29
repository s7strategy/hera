-- Milena esqueceu de encerrar em 28/08. O turno rodou até 29/08 09:54
-- (~24h). Ela parou às 16:00 e entrou hoje (29/08) às 10:00 (já correto).

begin;

update s7ponto.shifts
   set ended_at = ('2026-08-28 16:00:00'::timestamp AT TIME ZONE 'America/Sao_Paulo'),
       note = coalesce(nullif(note, ''), 'ajuste: esqueceu de encerrar 28/08, parou 16:00')
 where id = '5b4989d0-033b-4a13-91b6-d5e482ec1295'
   and user_id = (select id from s7ponto.profiles where username = 'milena');

update s7ponto.segments
   set ended_at = ('2026-08-28 16:00:00'::timestamp AT TIME ZONE 'America/Sao_Paulo')
 where shift_id = '5b4989d0-033b-4a13-91b6-d5e482ec1295'
   and ended_at is distinct from ('2026-08-28 16:00:00'::timestamp AT TIME ZONE 'America/Sao_Paulo');

-- Aviso de ~18h extra veio do turno que ficou a noite toda aberto.
delete from s7ponto.overtime_notices
 where shift_id = '5b4989d0-033b-4a13-91b6-d5e482ec1295';

commit;

-- Conferência
select s.id,
       s.started_at at time zone 'America/Sao_Paulo' as inicio_br,
       s.ended_at   at time zone 'America/Sao_Paulo' as fim_br,
       round(extract(epoch from (coalesce(s.ended_at, now()) - s.started_at))/3600.0, 2) as horas,
       s.note
  from s7ponto.shifts s
  join s7ponto.profiles p on p.id = s.user_id
 where p.username = 'milena'
   and s.started_at >= ('2026-08-27 00:00:00'::timestamp AT TIME ZONE 'America/Sao_Paulo')
 order by s.started_at;
