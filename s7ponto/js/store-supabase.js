/* ==========================================================================
   S7 PONTO — armazém do Supabase (self-hosted).
   Fala com o schema dedicado do projeto (CONFIG.DB_SCHEMA), sempre com a
   chave pública. Quem decide o que cada um enxerga é o RLS do banco.
   ========================================================================== */
import { CONFIG } from './config.js';

const CDN = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm';

/** "maria" -> "maria@s7ponto.local" (e-mail sintético, nunca real). */
const paraEmail = (username) =>
  `${String(username || '').trim().toLowerCase()}@${CONFIG.EMAIL_DOMAIN}`;

/** Transforma o erro cru do Postgres em português de gente. */
function traduzErro(e) {
  const msg = String(e?.message || e || 'Falha inesperada.');
  if (/Invalid login credentials/i.test(msg)) return new Error('Usuário ou senha incorretos.');
  if (/Email not confirmed/i.test(msg))
    return new Error('O Supabase está exigindo confirmação de e-mail. Ligue GOTRUE_MAILER_AUTOCONFIRM=true (ver README, passo 3).');
  if (/shifts_um_aberto_por_pessoa/.test(msg)) return new Error('Já existe um turno aberto para esta pessoa.');
  if (/segments_um_aberto_por_turno/.test(msg)) return new Error('Este turno já tem uma tarefa em andamento.');
  if (/profiles_username_key|duplicate key/i.test(msg)) return new Error('Já existe alguém com esse usuário.');
  if (/row-level security|permission denied/i.test(msg)) return new Error('Sem permissão para esta ação.');
  if (/schema .* does not exist|Could not find the table/i.test(msg))
    return new Error(`O schema "${CONFIG.DB_SCHEMA}" não está exposto na API. Ver README, passo 3.`);
  if (/Failed to fetch|NetworkError/i.test(msg))
    return new Error('Não consegui falar com o servidor. Confira a internet e a URL do Supabase.');
  return new Error(msg);
}
const ok = ({ data, error }) => { if (error) throw traduzErro(error); return data; };

export async function criaStoreSupabase() {
  const { createClient } = await import(/* @vite-ignore */ CDN);
  const sb = createClient(CONFIG.SUPABASE_URL, CONFIG.SUPABASE_ANON_KEY, {
    db: { schema: CONFIG.DB_SCHEMA },
    auth: { persistSession: true, autoRefreshToken: true, storageKey: 's7ponto.auth' },
  });

  let usuario = null;

  async function carregaPerfil(authUser) {
    if (!authUser) return null;
    const p = ok(await sb.from('profiles').select('*').eq('id', authUser.id).maybeSingle());
    if (!p) { await sb.auth.signOut(); throw new Error('Este acesso ainda não foi liberado pela administração.'); }
    if (!p.active) { await sb.auth.signOut(); throw new Error('Este acesso está desativado. Fale com a administração.'); }
    return p;
  }

  const ehAdmin = () => usuario?.role === 'admin';
  const exigeAdmin = () => { if (!ehAdmin()) throw new Error('Só um administrador pode fazer isso.'); };

  return {
    modo: 'supabase',

    async init() {
      const { data } = await sb.auth.getSession();
      usuario = data?.session ? await carregaPerfil(data.session.user).catch(() => null) : null;
      return usuario;
    },

    usuarioAtual: () => usuario,

    async login(username, senha) {
      const { data, error } = await sb.auth.signInWithPassword({
        email: paraEmail(username), password: String(senha ?? ''),
      });
      if (error) throw traduzErro(error);
      usuario = await carregaPerfil(data.user);
      return usuario;
    },

    async logout() { await sb.auth.signOut(); usuario = null; },

    /* ---- tarefas ---- */
    async listaTarefas(incluirInativas = false) {
      let q = sb.from('tasks').select('*').order('sort_order').order('name');
      if (!incluirInativas) q = q.eq('active', true);
      return ok(await q);
    },
    async criaTarefa(t) {
      exigeAdmin();
      return ok(await sb.from('tasks').insert({
        name: t.name, color: t.color, hourly_rate: +t.hourly_rate || 0,
        active: t.active !== false, sort_order: t.sort_order ?? 0,
      }).select().single());
    },
    async atualizaTarefa(id, patch) {
      exigeAdmin();
      return ok(await sb.from('tasks').update(patch).eq('id', id).select().single());
    },
    async apagaTarefa(id) {
      exigeAdmin();
      ok(await sb.from('tasks').delete().eq('id', id));
      return true;
    },

    /* ---- equipe ---- */
    async listaPessoas() {
      exigeAdmin();
      return ok(await sb.from('profiles').select('*').order('full_name'));
    },
    async criaPessoa({ username, full_name, password, role }) {
      exigeAdmin();
      const id = ok(await sb.rpc('admin_cria_usuario', {
        p_username: String(username || '').trim().toLowerCase(),
        p_full_name: full_name || username,
        p_password: password,
        p_role: role || 'employee',
      }));
      return ok(await sb.from('profiles').select('*').eq('id', id).single());
    },
    async atualizaPessoa(id, patch) {
      exigeAdmin();
      const p = ok(await sb.from('profiles').update(patch).eq('id', id).select().single());
      if (usuario?.id === id) usuario = p;
      return p;
    },
    async trocaSenha(id, senha) {
      ok(await sb.rpc('troca_senha', { p_user_id: id, p_senha: senha }));
      return true;
    },
    async apagaPessoa(id) {
      exigeAdmin();
      ok(await sb.rpc('admin_apaga_usuario', { p_user_id: id }));
      return true;
    },

    /* ---- atribuições ---- */
    async listaAtribuicoes() {
      return ok(await sb.from('task_assignments').select('user_id, task_id'));
    },
    async defineAtribuicoes(userId, taskIds) {
      exigeAdmin();
      ok(await sb.from('task_assignments').delete().eq('user_id', userId));
      if (taskIds.length) {
        ok(await sb.from('task_assignments')
          .insert(taskIds.map((task_id) => ({ user_id: userId, task_id }))));
      }
      return true;
    },
    async tarefasDaPessoa(userId) {
      const links = ok(await sb.from('task_assignments').select('task_id').eq('user_id', userId));
      const ids = links.map((l) => l.task_id);
      if (!ids.length) return [];
      return ok(await sb.from('tasks').select('*').in('id', ids).eq('active', true)
        .order('sort_order').order('name'));
    },

    /* ---- ponto ---- */
    async turnoAberto(userId) {
      const turnos = ok(await sb.from('shifts').select('*')
        .eq('user_id', userId).is('ended_at', null)
        .order('started_at', { ascending: false }).limit(1));
      const t = turnos[0];
      if (!t) return null;
      const segs = ok(await sb.from('segments').select('*').eq('shift_id', t.id).order('started_at'));
      return { ...t, segments: segs };
    },
    async iniciaTurno(userId, taskId, quando = new Date()) {
      const tarefa = ok(await sb.from('tasks').select('*').eq('id', taskId).single());
      const inicio = new Date(quando).toISOString();
      const turno = ok(await sb.from('shifts')
        .insert({ user_id: userId, started_at: inicio, source: 'app' }).select().single());
      try {
        ok(await sb.from('segments').insert({
          shift_id: turno.id, task_id: tarefa.id, task_name: tarefa.name,
          hourly_rate: tarefa.hourly_rate, started_at: inicio,
        }));
      } catch (e) {
        // não deixa turno órfão sem tarefa nenhuma
        await sb.from('shifts').delete().eq('id', turno.id);
        throw e;
      }
      return turno;
    },
    async trocaTarefa(shiftId, taskId, quando = new Date()) {
      const tarefa = ok(await sb.from('tasks').select('*').eq('id', taskId).single());
      const agora = new Date(quando).toISOString();
      ok(await sb.from('segments').update({ ended_at: agora })
        .eq('shift_id', shiftId).is('ended_at', null));
      ok(await sb.from('segments').insert({
        shift_id: shiftId, task_id: tarefa.id, task_name: tarefa.name,
        hourly_rate: tarefa.hourly_rate, started_at: agora,
      }));
      return true;
    },
    async fechaTurno(shiftId, quando = new Date()) {
      const agora = new Date(quando).toISOString();
      // o gatilho do banco fecha os trechos abertos junto
      return ok(await sb.from('shifts').update({ ended_at: agora })
        .eq('id', shiftId).select().single());
    },

    /* ---- consultas ---- */
    async listaTurnos({ userId = null, de = null, ate = null } = {}) {
      let q = sb.from('shifts').select('*').order('started_at', { ascending: false });
      if (userId) q = q.eq('user_id', userId);
      if (de) q = q.gte('started_at', new Date(de).toISOString());
      if (ate) q = q.lte('started_at', new Date(ate).toISOString());
      const turnos = ok(await q);
      if (!turnos.length) return [];
      const segs = ok(await sb.from('segments').select('*')
        .in('shift_id', turnos.map((t) => t.id)).order('started_at'));
      const porTurno = new Map();
      segs.forEach((s) => {
        if (!porTurno.has(s.shift_id)) porTurno.set(s.shift_id, []);
        porTurno.get(s.shift_id).push(s);
      });
      return turnos.map((t) => ({ ...t, segments: porTurno.get(t.id) || [] }));
    },

    async gravaTurnoManual({ user_id, started_at, ended_at, trechos, source = 'manual', note = null }) {
      const turno = ok(await sb.from('shifts').insert({
        user_id, source, note,
        started_at: new Date(started_at).toISOString(),
        ended_at: ended_at ? new Date(ended_at).toISOString() : null,
      }).select().single());
      if (trechos?.length) {
        ok(await sb.from('segments').insert(trechos.map((tr) => ({
          shift_id: turno.id, task_id: tr.task_id ?? null, task_name: tr.task_name,
          hourly_rate: +tr.hourly_rate || 0,
          started_at: new Date(tr.started_at).toISOString(),
          ended_at: tr.ended_at ? new Date(tr.ended_at).toISOString() : null,
        }))));
      }
      return turno;
    },

    async atualizaTurno(shiftId, { started_at, ended_at, note, trechos }) {
      exigeAdmin();
      const patch = {};
      if (started_at) patch.started_at = new Date(started_at).toISOString();
      if (ended_at !== undefined) patch.ended_at = ended_at ? new Date(ended_at).toISOString() : null;
      if (note !== undefined) patch.note = note;
      const turno = Object.keys(patch).length
        ? ok(await sb.from('shifts').update(patch).eq('id', shiftId).select().single())
        : ok(await sb.from('shifts').select('*').eq('id', shiftId).single());
      if (trechos) {
        ok(await sb.from('segments').delete().eq('shift_id', shiftId));
        if (trechos.length) {
          ok(await sb.from('segments').insert(trechos.map((tr) => ({
            shift_id: shiftId, task_id: tr.task_id ?? null, task_name: tr.task_name,
            hourly_rate: +tr.hourly_rate || 0,
            started_at: new Date(tr.started_at).toISOString(),
            ended_at: tr.ended_at ? new Date(tr.ended_at).toISOString() : null,
          }))));
        }
      }
      return turno;
    },

    async apagaTurno(shiftId) {
      exigeAdmin();
      ok(await sb.from('shifts').delete().eq('id', shiftId));
      return true;
    },
  };
}
