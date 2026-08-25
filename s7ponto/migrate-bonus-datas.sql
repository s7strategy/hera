-- ============================================================================
--  S7 PONTO — data do bônus (pode haver vários no mesmo mês)
-- ============================================================================

alter table s7ponto.bonus_entries
  add column if not exists bonus_on date;

comment on column s7ponto.bonus_entries.bonus_on is
  'Dia em que o bônus entra. Null = só o mês (legado / automático sem dia).';

-- Backfill: usa o dia 1 do year_month quando ainda não tem data
update s7ponto.bonus_entries
   set bonus_on = (year_month || '-01')::date
 where bonus_on is null
   and year_month ~ '^\d{4}-\d{2}$';

create index if not exists bonus_entries_por_data
  on s7ponto.bonus_entries (user_id, bonus_on);

-- Garante auto com data no 1º dia do mês
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

  insert into s7ponto.bonus_entries (user_id, year_month, title, amount, source, template_id, bonus_on)
  select t.user_id, p_year_month, t.title, t.amount, 'auto', t.id,
         (p_year_month || '-01')::date
    from s7ponto.bonus_templates t
   where t.user_id = p_user and t.active
     and not exists (
       select 1 from s7ponto.bonus_entries e
        where e.user_id = t.user_id
          and e.year_month = p_year_month
          and e.template_id = t.id
     );
end $$;
