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

    /* ---- empresas / sedes ---- */
    async listaEmpresas(incluirInativas = false) {
      let q = sb.from('companies').select('*').order('sort_order').order('name');
      if (!incluirInativas) q = q.eq('active', true);
      return ok(await q);
    },
    async criaEmpresa(c) {
      exigeAdmin();
      return ok(await sb.from('companies').insert({
        name: c.name, color: c.color, active: c.active !== false,
        sort_order: c.sort_order ?? 0,
      }).select().single());
    },
    async atualizaEmpresa(id, patch) {
      exigeAdmin();
      return ok(await sb.from('companies').update(patch).eq('id', id).select().single());
    },
    async apagaEmpresa(id) {
      exigeAdmin();
      ok(await sb.from('companies').delete().eq('id', id));
      return true;
    },
    async listaAtribuicoesEmpresa() {
      return ok(await sb.from('company_assignments').select('user_id, company_id'));
    },
    async defineEmpresas(userId, companyIds) {
      exigeAdmin();
      ok(await sb.from('company_assignments').delete().eq('user_id', userId));
      if (companyIds.length) {
        ok(await sb.from('company_assignments')
          .insert(companyIds.map((company_id) => ({ user_id: userId, company_id }))));
      }
      return true;
    },
    async empresasDaPessoa(userId) {
      const links = ok(await sb.from('company_assignments').select('company_id').eq('user_id', userId));
      const ids = links.map((l) => l.company_id);
      if (!ids.length) return [];
      return ok(await sb.from('companies').select('*').in('id', ids).eq('active', true)
        .order('sort_order').order('name'));
    },

    /* ---- pagamentos (3 modos) ---- */
    async listaTaxasTarefa(userId = null) {
      let q = sb.from('task_rates').select('*');
      if (userId) q = q.eq('user_id', userId);
      return ok(await q);
    },
    async listaTaxasTurno(userId = null) {
      let q = sb.from('shift_rates').select('*');
      if (userId) q = q.eq('user_id', userId);
      return ok(await q);
    },
    /** ratesTarefa: [{ task_id, hourly_rate?, flat_amount? }] · ratesTurno: [{ period, amount }] */
    async definePagamento(userId, { pay_mode, ratesTarefa = [], ratesTurno = [] }) {
      exigeAdmin();
      if (pay_mode) {
        ok(await sb.from('profiles').update({ pay_mode }).eq('id', userId));
        if (usuario?.id === userId) usuario = { ...usuario, pay_mode };
      }
      ok(await sb.from('task_rates').delete().eq('user_id', userId));
      ok(await sb.from('shift_rates').delete().eq('user_id', userId));
      const tarefas = (ratesTarefa || []).filter((r) => r.task_id);
      if (tarefas.length) {
        ok(await sb.from('task_rates').insert(tarefas.map((r) => ({
          user_id: userId, task_id: r.task_id,
          hourly_rate: r.hourly_rate != null && r.hourly_rate !== '' ? +r.hourly_rate : null,
          flat_amount: r.flat_amount != null && r.flat_amount !== '' ? +r.flat_amount : null,
        }))));
      }
      const turnos = (ratesTurno || []).filter((r) => r.period);
      if (turnos.length) {
        ok(await sb.from('shift_rates').insert(turnos.map((r) => ({
          user_id: userId, period: r.period, amount: +r.amount || 0,
        }))));
      }
      return true;
    },

    /* ---- bônus mensais ---- */
    async listaTemplatesBonus(userId = null) {
      let q = sb.from('bonus_templates').select('*').order('sort_order').order('created_at');
      if (userId) q = q.eq('user_id', userId);
      return ok(await q);
    },
    async criaTemplateBonus({ user_id, title, amount, active = true, sort_order = 0 }) {
      exigeAdmin();
      const titulo = String(title || '').trim();
      if (!titulo) throw new Error('Dê um título ao bônus.');
      return ok(await sb.from('bonus_templates').insert({
        user_id, title: titulo, amount: +amount || 0, active: !!active, sort_order: +sort_order || 0,
      }).select().single());
    },
    async atualizaTemplateBonus(id, patch) {
      exigeAdmin();
      const p = { ...patch };
      if (p.title != null) p.title = String(p.title).trim();
      if (p.amount != null) p.amount = +p.amount || 0;
      return ok(await sb.from('bonus_templates').update(p).eq('id', id).select().single());
    },
    async apagaTemplateBonus(id) {
      exigeAdmin();
      ok(await sb.from('bonus_templates').delete().eq('id', id));
      return true;
    },
    /**
     * Lista bônus do mês. Garante entries dos templates ativos (idempotente).
     * @param {{ userId?: string, yearMonth: string }} opts
     */
    async listaBonusMes({ userId = null, yearMonth }) {
      if (!yearMonth || !/^\d{4}-\d{2}$/.test(yearMonth)) {
        throw new Error('Mês inválido: use AAAA-MM.');
      }
      if (userId) {
        ok(await sb.rpc('garante_bonus_mes', { p_user: userId, p_year_month: yearMonth }));
      } else {
        // admin pedindo o mês inteiro: garante para todas as pessoas com template ativo
        const templates = ok(await sb.from('bonus_templates').select('user_id').eq('active', true));
        const ids = [...new Set(templates.map((t) => t.user_id))];
        for (const uid of ids) {
          ok(await sb.rpc('garante_bonus_mes', { p_user: uid, p_year_month: yearMonth }));
        }
      }
      let q = sb.from('bonus_entries').select('*').eq('year_month', yearMonth)
        .order('bonus_on', { ascending: true }).order('created_at');
      if (userId) q = q.eq('user_id', userId);
      return ok(await q);
    },
    /**
     * Lança um ou vários bônus (mesmo título/valor em datas diferentes).
     * @param {{ user_id, year_month?, title, amount, note?, dates?: string[], bonus_on?: string }}
     */
    async lancaBonus({ user_id, year_month = null, title, amount, note = null, dates = null, bonus_on = null }) {
      exigeAdmin();
      const titulo = String(title || '').trim();
      if (!titulo) throw new Error('Dê um título ao bônus.');
      const dias = [];
      if (Array.isArray(dates) && dates.length) {
        dates.forEach((d) => { if (d) dias.push(String(d).slice(0, 10)); });
      } else if (bonus_on) {
        dias.push(String(bonus_on).slice(0, 10));
      } else if (year_month && /^\d{4}-\d{2}$/.test(year_month)) {
        dias.push(`${year_month}-01`);
      } else {
        throw new Error('Escolha pelo menos uma data para o bônus.');
      }
      const uniq = [...new Set(dias)].filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d));
      if (!uniq.length) throw new Error('Escolha pelo menos uma data válida.');
      const rows = uniq.map((dia) => ({
        user_id,
        year_month: dia.slice(0, 7),
        bonus_on: dia,
        title: titulo,
        amount: +amount || 0,
        source: 'manual',
        note: note || null,
      }));
      const inserted = ok(await sb.from('bonus_entries').insert(rows).select());
      return Array.isArray(inserted) ? inserted : [inserted];
    },
    async atualizaBonus(id, patch) {
      exigeAdmin();
      const p = { ...patch };
      if (p.title != null) p.title = String(p.title).trim();
      if (p.amount != null) p.amount = +p.amount || 0;
      if (p.bonus_on) {
        p.bonus_on = String(p.bonus_on).slice(0, 10);
        p.year_month = p.bonus_on.slice(0, 7);
      }
      return ok(await sb.from('bonus_entries').update(p).eq('id', id).select().single());
    },
    async apagaBonus(id) {
      exigeAdmin();
      ok(await sb.from('bonus_entries').delete().eq('id', id));
      return true;
    },

    /* ---- pagamentos / recebimentos ---- */
    async listaPagamentos({ userId = null, yearMonth = null } = {}) {
      let q = sb.from('payments').select('*').order('paid_on', { ascending: false });
      if (userId) q = q.eq('user_id', userId);
      if (yearMonth) q = q.eq('year_month', yearMonth);
      return ok(await q);
    },
    async lancaPagamento({ user_id, paid_on, amount, title = 'Pagamento', note = null, year_month = null }) {
      exigeAdmin();
      const when = paid_on ? new Date(paid_on) : new Date();
      const ym = year_month || `${when.getFullYear()}-${String(when.getMonth() + 1).padStart(2, '0')}`;
      const titulo = String(title || 'Pagamento').trim() || 'Pagamento';
      return ok(await sb.from('payments').insert({
        user_id,
        paid_on: when.toISOString().slice(0, 10),
        year_month: ym,
        amount: +amount || 0,
        title: titulo,
        note: note || null,
        source: 'manual',
      }).select().single());
    },
    async atualizaPagamento(id, patch) {
      exigeAdmin();
      const p = { ...patch };
      if (p.amount != null) p.amount = +p.amount || 0;
      if (p.title != null) p.title = String(p.title).trim() || 'Pagamento';
      if (p.paid_on) {
        const when = new Date(p.paid_on);
        p.paid_on = when.toISOString().slice(0, 10);
        if (!p.year_month) {
          p.year_month = `${when.getFullYear()}-${String(when.getMonth() + 1).padStart(2, '0')}`;
        }
      }
      return ok(await sb.from('payments').update(p).eq('id', id).select().single());
    },
    async apagaPagamento(id) {
      exigeAdmin();
      ok(await sb.from('payments').delete().eq('id', id));
      return true;
    },
    async listaTotaisPlanilha({ userId = null, yearMonth = null } = {}) {
      let q = sb.from('sheet_month_totals').select('*').order('year_month', { ascending: false });
      if (userId) q = q.eq('user_id', userId);
      if (yearMonth) q = q.eq('year_month', yearMonth);
      return ok(await q);
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
    async iniciaTurno(userId, opts = {}) {
      const {
        taskId = null, companyId = null, period = null, quando = new Date(),
      } = opts;

      const perfil = ok(await sb.from('profiles').select('pay_mode').eq('id', userId).single());
      const modo = perfil?.pay_mode || 'hourly';

      let empresa = null;
      if (companyId) {
        empresa = ok(await sb.from('companies').select('*').eq('id', companyId).single());
      }

      const inicio = new Date(quando).toISOString();
      let flatTurno = null;
      let periodo = period || null;
      let trecho;

      if (modo === 'shift') {
        if (!periodo) throw new Error('Escolha o turno: manhã, tarde ou noite.');
        flatTurno = +ok(await sb.rpc('taxa_turno', { p_user: userId, p_period: periodo })) || 0;
        const rotulo = { manha: 'Manhã', tarde: 'Tarde', noite: 'Noite' }[periodo] || periodo;
        trecho = {
          task_id: null, task_name: `Turno ${rotulo}`,
          hourly_rate: 0, flat_amount: null, period: periodo, started_at: inicio,
        };
      } else {
        if (!taskId) throw new Error('Escolha uma tarefa para começar.');
        const tarefa = ok(await sb.from('tasks').select('*').eq('id', taskId).single());
        if (modo === 'task') {
          const fixo = +ok(await sb.rpc('taxa_tarefa', { p_user: userId, p_task: taskId })) || 0;
          trecho = {
            task_id: tarefa.id, task_name: tarefa.name,
            hourly_rate: 0, flat_amount: fixo, period: periodo, started_at: inicio,
          };
        } else {
          const taxa = +ok(await sb.rpc('taxa_hora', { p_user: userId, p_task: taskId })) || 0;
          trecho = {
            task_id: tarefa.id, task_name: tarefa.name,
            hourly_rate: taxa, flat_amount: null, period: periodo, started_at: inicio,
          };
        }
      }

      const turno = ok(await sb.from('shifts').insert({
        user_id: userId, started_at: inicio, source: 'app',
        company_id: empresa?.id ?? null, company_name: empresa?.name ?? null,
        period: periodo, pay_mode: modo, flat_amount: flatTurno,
      }).select().single());
      try {
        ok(await sb.from('segments').insert({ ...trecho, shift_id: turno.id }));
      } catch (e) {
        await sb.from('shifts').delete().eq('id', turno.id);
        throw e;
      }
      return turno;
    },
    async trocaTarefa(shiftId, taskId, period = null, quando = new Date()) {
      const turno = ok(await sb.from('shifts').select('*').eq('id', shiftId).single());
      if ((turno.pay_mode || 'hourly') === 'shift') {
        throw new Error('Quem recebe por turno não troca de tarefa no meio.');
      }
      const tarefa = ok(await sb.from('tasks').select('*').eq('id', taskId).single());
      const agora = new Date(quando).toISOString();
      const periodo = period || turno.period || null;
      const modo = turno.pay_mode || 'hourly';
      let trecho;
      if (modo === 'task') {
        const fixo = +ok(await sb.rpc('taxa_tarefa', { p_user: turno.user_id, p_task: taskId })) || 0;
        trecho = {
          shift_id: shiftId, task_id: tarefa.id, task_name: tarefa.name,
          hourly_rate: 0, flat_amount: fixo, period: periodo, started_at: agora,
        };
      } else {
        const taxa = +ok(await sb.rpc('taxa_hora', { p_user: turno.user_id, p_task: taskId })) || 0;
        trecho = {
          shift_id: shiftId, task_id: tarefa.id, task_name: tarefa.name,
          hourly_rate: taxa, flat_amount: null, period: periodo, started_at: agora,
        };
      }
      ok(await sb.from('segments').update({ ended_at: agora })
        .eq('shift_id', shiftId).is('ended_at', null));
      ok(await sb.from('segments').insert(trecho));
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

    async gravaTurnoManual({ user_id, started_at, ended_at, trechos, source = 'manual', note = null,
                             company_id = null, company_name = null }) {
      let empresaNome = company_name;
      let empresaId = company_id;
      if (empresaId && !empresaNome) {
        const c = ok(await sb.from('companies').select('id, name').eq('id', empresaId).maybeSingle());
        if (c) { empresaNome = c.name; empresaId = c.id; }
      }
      const turno = ok(await sb.from('shifts').insert({
        user_id, source, note,
        company_id: empresaId, company_name: empresaNome,
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

    async atualizaTurno(shiftId, { started_at, ended_at, note, trechos, company_id, company_name }) {
      exigeAdmin();
      const patch = {};
      if (started_at) patch.started_at = new Date(started_at).toISOString();
      if (ended_at !== undefined) patch.ended_at = ended_at ? new Date(ended_at).toISOString() : null;
      if (note !== undefined) patch.note = note;
      if (company_id !== undefined) patch.company_id = company_id;
      if (company_name !== undefined) patch.company_name = company_name;
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
