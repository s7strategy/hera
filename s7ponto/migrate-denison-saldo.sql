-- Denison: o import trouxe o TOTAL da aba outubro como pagamento
-- (R$ 1.100,20) e um turno com ano 2010. A planilha de agosto tem
-- A PAGAR = R$ 1.523 (já puxa R$ 613 de julho).
begin;

delete from s7ponto.payments p
 using s7ponto.profiles pr
 where p.user_id = pr.id
   and pr.username = 'denison'
   and p.source = 'import'
   and p.amount = 1100.20
   and coalesce(p.note, '') ilike '%total 1100.2%';

update s7ponto.shifts
   set started_at = started_at + interval '15 years',
       ended_at   = ended_at   + interval '15 years'
 where id = 'b0d3e06a-8d15-4666-83c9-90c0defdc83a';

update s7ponto.segments
   set started_at = started_at + interval '15 years',
       ended_at   = ended_at   + interval '15 years'
 where shift_id = 'b0d3e06a-8d15-4666-83c9-90c0defdc83a';

-- Fecha o saldo de julho em R$ 613 (A PAGAR da aba julho / saldo que agosto puxa).
insert into s7ponto.bonus_entries (user_id, year_month, title, amount, source, note)
select pr.id, '2026-07', 'Saldo conferido da planilha', 618.80, 'import',
       'A PAGAR da aba julho = R$ 613. Compensa lançamentos antigos que não bateram com a planilha.'
  from s7ponto.profiles pr
 where pr.username = 'denison'
   and not exists (
     select 1 from s7ponto.bonus_entries b
      where b.user_id = pr.id
        and b.title = 'Saldo conferido da planilha'
        and b.year_month = '2026-07'
   );

commit;
notify pgrst, 'reload schema';
