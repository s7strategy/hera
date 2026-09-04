-- S7 PONTO — tema por pessoa + senha padrão dos funcionários (usuário + 321*).
-- Aplicar no container s7hub-supabase-db, schema s7ponto. Depois: NOTIFY pgrst.

alter table s7ponto.profiles
  add column if not exists theme text not null default 'escuro';

do $$
begin
  alter table s7ponto.profiles drop constraint if exists profiles_theme_check;
  alter table s7ponto.profiles
    add constraint profiles_theme_check check (theme in ('escuro', 'claro'));
exception when others then
  null;
end $$;

create or replace function s7ponto.define_tema(p_tema text)
returns void
language plpgsql security definer
set search_path = s7ponto, public as $$
begin
  if coalesce(p_tema, '') not in ('escuro', 'claro') then
    raise exception 'Tema inválido.';
  end if;
  update s7ponto.profiles set theme = p_tema where id = auth.uid();
end $$;

revoke all on function s7ponto.define_tema(text) from public, anon;
grant execute on function s7ponto.define_tema(text) to authenticated;

create or replace function s7ponto.troca_senha(p_user_id uuid, p_senha text)
returns void
language plpgsql security definer
set search_path = s7ponto, auth, extensions, public as $$
begin
  if not (s7ponto.is_admin() or p_user_id = auth.uid()) then
    raise exception 'Você só pode trocar a própria senha.';
  end if;
  if length(coalesce(p_senha, '')) < 4 then
    raise exception 'A senha precisa ter pelo menos 4 caracteres.';
  end if;
  update auth.users
     set encrypted_password = extensions.crypt(p_senha, extensions.gen_salt('bf')),
         updated_at = now()
   where id = p_user_id;
end $$;

-- Senha inicial de todo funcionário: username + 321*  (admin não muda)
update auth.users u
   set encrypted_password = extensions.crypt(p.username || '321*', extensions.gen_salt('bf')),
       updated_at = now()
  from s7ponto.profiles p
 where u.id = p.id
   and p.role = 'employee';
