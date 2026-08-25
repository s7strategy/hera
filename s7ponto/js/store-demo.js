/* ==========================================================================
   S7 PONTO — armazém do MODO DEMONSTRAÇÃO.
   Tudo fica no localStorage do próprio navegador, com três meses de
   histórico de mentira já semeado, só para você ver o sistema funcionando
   antes de ligar no Supabase. Nada sai do aparelho.
   ========================================================================== */
import { uid, diaChave, somaDias, inicioDoDia } from './util.js';

const CHAVE = 's7ponto.demo.v2';
const SESSAO = 's7ponto.demo.sessao';
const espera = (v) => new Promise((r) => setTimeout(() => r(v), 60));

const PALETA = ['#d95926', '#199e70', '#3987e5', '#c98500', '#d55181', '#7d9c2f', '#9085e9', '#e66767'];

/* ---------- semeadura ---------------------------------------------------- */

function semear() {
  const companies = [
    { id: uid(), name: 'Pessoal',  color: PALETA[3], active: true, sort_order: 1 },
    { id: uid(), name: 'Cineplay', color: PALETA[2], active: true, sort_order: 2 },
    { id: uid(), name: 'S7',       color: PALETA[0], active: true, sort_order: 3 },
  ];
  const tasks = [
    { id: uid(), name: 'Cozinha',     color: PALETA[0], hourly_rate: 22, active: true, sort_order: 1 },
    { id: uid(), name: 'Atendimento', color: PALETA[1], hourly_rate: 18, active: true, sort_order: 2 },
    { id: uid(), name: 'Produção',    color: PALETA[2], hourly_rate: 25, active: true, sort_order: 3 },
    { id: uid(), name: 'Limpeza',     color: PALETA[3], hourly_rate: 16, active: true, sort_order: 4 },
  ];
  const profiles = [
    { id: uid(), username: 'admin', full_name: 'Administração S7', role: 'admin',    active: true },
    { id: uid(), username: 'maria', full_name: 'Maria Aparecida',  role: 'employee', active: true },
    { id: uid(), username: 'joao',  full_name: 'João Pedro',       role: 'employee', active: true },
  ];
  const [adm, maria, joao] = profiles;

  const assignments = [
    { user_id: maria.id, task_id: tasks[0].id },
    { user_id: maria.id, task_id: tasks[2].id },
    { user_id: maria.id, task_id: tasks[3].id },
    { user_id: joao.id,  task_id: tasks[1].id },
    { user_id: adm.id,   task_id: tasks[0].id },
    { user_id: adm.id,   task_id: tasks[1].id },
  ];

  const companyAssignments = [
    { user_id: maria.id, company_id: companies[1].id }, // Cineplay
    { user_id: maria.id, company_id: companies[2].id }, // S7
    { user_id: joao.id,  company_id: companies[0].id }, // Pessoal
    { user_id: adm.id,   company_id: companies[0].id },
    { user_id: adm.id,   company_id: companies[1].id },
    { user_id: adm.id,   company_id: companies[2].id },
  ];

  // gerador pseudoaleatório com semente: o histórico não muda a cada reload
  let s = 20260825;
  const rnd = () => ((s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);

  const shifts = [], segments = [];
  const pessoas = [
    { p: maria, tarefas: [tasks[0], tasks[2], tasks[3]], empresas: [companies[1], companies[2]], entrada: 8,  jornada: 8   },
    { p: joao,  tarefas: [tasks[1]],                     empresas: [companies[0]],               entrada: 13, jornada: 6.5 },
  ];

  for (let atras = 96; atras >= 1; atras--) {
    const dia = inicioDoDia(somaDias(new Date(), -atras));
    if (dia.getDay() === 0) continue;                     // domingo folga
    for (const { p, tarefas, empresas, entrada, jornada } of pessoas) {
      if (rnd() < 0.12) continue;                         // uma falta aqui e ali
      const ini = new Date(dia);
      ini.setHours(entrada, Math.floor(rnd() * 25), 0, 0);
      const dur = jornada + (rnd() - 0.45) * 2.2;
      const fim = new Date(ini.getTime() + dur * 3600000);
      const emp = empresas[Math.floor(rnd() * empresas.length)];

      const turno = { id: uid(), user_id: p.id, started_at: ini.toISOString(),
                      ended_at: fim.toISOString(), source: 'app', note: null,
                      company_id: emp.id, company_name: emp.name };
      shifts.push(turno);

      // uma ou duas tarefas dentro do turno
      const quantas = tarefas.length > 1 && rnd() < 0.45 ? 2 : 1;
      let cursor = ini;
      for (let i = 0; i < quantas; i++) {
        const t = tarefas[Math.floor(rnd() * tarefas.length)];
        const ate = i === quantas - 1
          ? fim
          : new Date(cursor.getTime() + (fim - cursor) * (0.35 + rnd() * 0.3));
        segments.push({ id: uid(), shift_id: turno.id, task_id: t.id, task_name: t.name,
                        hourly_rate: t.hourly_rate,
                        started_at: cursor.toISOString(), ended_at: ate.toISOString() });
        cursor = ate;
      }
    }
  }
  return {
    profiles, tasks, companies, assignments, companyAssignments, shifts, segments,
    taskRates: [], shiftRates: [],
    senhas: { admin: '1234', maria: '1234', joao: '1234' },
  };
}

/* ---------- persistência ------------------------------------------------- */

function ler() {
  try {
    const cru = localStorage.getItem(CHAVE);
    if (cru) {
      const db = JSON.parse(cru);
      if (!Array.isArray(db.companies)) db.companies = [];
      if (!Array.isArray(db.companyAssignments)) db.companyAssignments = [];
      if (!Array.isArray(db.taskRates)) db.taskRates = [];
      if (!Array.isArray(db.shiftRates)) db.shiftRates = [];
      db.profiles.forEach((p) => { if (!p.pay_mode) p.pay_mode = 'hourly'; });
      return db;
    }
  } catch { /* storage bloqueado ou json quebrado: recomeça */ }
  const novo = semear();
  gravar(novo);
  return novo;
}
function gravar(db) {
  try { localStorage.setItem(CHAVE, JSON.stringify(db)); } catch { /* modo anônimo */ }
  return db;
}

/* ---------- adaptador ---------------------------------------------------- */

export function criaStoreDemo() {
  let db = null;
  let usuario = null;
  const carrega = () => (db ??= ler());
  const salva = () => gravar(db);
  const ehAdmin = () => usuario?.role === 'admin';
  const exigeAdmin = () => { if (!ehAdmin()) throw new Error('Só um administrador pode fazer isso.'); };

  return {
    modo: 'demo',

    async init() {
      carrega();
      try {
        const id = localStorage.getItem(SESSAO);
        usuario = db.profiles.find((p) => p.id === id && p.active) || null;
      } catch { usuario = null; }
      return usuario;
    },

    usuarioAtual: () => usuario,

    async login(username, senha) {
      carrega();
      const u = String(username || '').trim().toLowerCase();
      const p = db.profiles.find((x) => x.username === u);
      if (!p) throw new Error('Usuário não encontrado.');
      if (!p.active) throw new Error('Este acesso está desativado. Fale com a administração.');
      if (db.senhas[u] && String(senha) !== db.senhas[u]) throw new Error('Senha incorreta.');
      usuario = p;
      try { localStorage.setItem(SESSAO, p.id); } catch { /* ok */ }
      return espera(p);
    },

    async logout() {
      usuario = null;
      try { localStorage.removeItem(SESSAO); } catch { /* ok */ }
    },

    /* ---- tarefas ---- */
    async listaTarefas(incluirInativas = false) {
      carrega();
      return espera(db.tasks
        .filter((t) => incluirInativas || t.active)
        .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name))
        .map((t) => ({ ...t })));
    },
    async criaTarefa(t) {
      exigeAdmin(); carrega();
      const nova = { id: uid(), name: t.name, color: t.color || PALETA[db.tasks.length % PALETA.length],
                     hourly_rate: +t.hourly_rate || 0, active: t.active !== false,
                     sort_order: t.sort_order ?? db.tasks.length + 1 };
      db.tasks.push(nova); salva();
      return espera(nova);
    },
    async atualizaTarefa(id, patch) {
      exigeAdmin(); carrega();
      const t = db.tasks.find((x) => x.id === id);
      if (!t) throw new Error('Tarefa não encontrada.');
      Object.assign(t, patch); salva();
      return espera(t);
    },
    async apagaTarefa(id) {
      exigeAdmin(); carrega();
      db.tasks = db.tasks.filter((t) => t.id !== id);
      db.assignments = db.assignments.filter((a) => a.task_id !== id);
      db.segments.forEach((sg) => { if (sg.task_id === id) sg.task_id = null; });
      salva();
      return espera(true);
    },

    /* ---- empresas / sedes ---- */
    async listaEmpresas(incluirInativas = false) {
      carrega();
      return espera(db.companies
        .filter((c) => incluirInativas || c.active)
        .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name))
        .map((c) => ({ ...c })));
    },
    async criaEmpresa(c) {
      exigeAdmin(); carrega();
      const nova = {
        id: uid(), name: c.name,
        color: c.color || PALETA[db.companies.length % PALETA.length],
        active: c.active !== false, sort_order: c.sort_order ?? db.companies.length + 1,
      };
      db.companies.push(nova); salva();
      return espera(nova);
    },
    async atualizaEmpresa(id, patch) {
      exigeAdmin(); carrega();
      const c = db.companies.find((x) => x.id === id);
      if (!c) throw new Error('Empresa não encontrada.');
      Object.assign(c, patch); salva();
      return espera(c);
    },
    async apagaEmpresa(id) {
      exigeAdmin(); carrega();
      db.companies = db.companies.filter((c) => c.id !== id);
      db.companyAssignments = db.companyAssignments.filter((a) => a.company_id !== id);
      db.shifts.forEach((s) => { if (s.company_id === id) s.company_id = null; });
      salva();
      return espera(true);
    },
    async listaAtribuicoesEmpresa() {
      carrega();
      const todas = db.companyAssignments.map((a) => ({ ...a }));
      return espera(ehAdmin() ? todas : todas.filter((a) => a.user_id === usuario?.id));
    },
    async defineEmpresas(userId, companyIds) {
      exigeAdmin(); carrega();
      db.companyAssignments = db.companyAssignments.filter((a) => a.user_id !== userId)
        .concat(companyIds.map((company_id) => ({ user_id: userId, company_id })));
      salva();
      return espera(true);
    },
    async empresasDaPessoa(userId) {
      carrega();
      const ids = new Set(db.companyAssignments.filter((a) => a.user_id === userId).map((a) => a.company_id));
      return espera(db.companies.filter((c) => c.active && ids.has(c.id))
        .sort((a, b) => a.sort_order - b.sort_order).map((c) => ({ ...c })));
    },

    async listaTaxasTarefa(userId = null) {
      carrega();
      if (!db.taskRates) db.taskRates = [];
      const todas = db.taskRates.map((r) => ({ ...r }));
      return espera(userId ? todas.filter((r) => r.user_id === userId) : todas);
    },
    async listaTaxasTurno(userId = null) {
      carrega();
      if (!db.shiftRates) db.shiftRates = [];
      const todas = db.shiftRates.map((r) => ({ ...r }));
      return espera(userId ? todas.filter((r) => r.user_id === userId) : todas);
    },
    async definePagamento(userId, { pay_mode, ratesTarefa = [], ratesTurno = [] }) {
      exigeAdmin(); carrega();
      const p = db.profiles.find((x) => x.id === userId);
      if (!p) throw new Error('Pessoa não encontrada.');
      if (pay_mode) {
        p.pay_mode = pay_mode;
        if (usuario?.id === userId) usuario = { ...usuario, pay_mode };
      }
      if (!db.taskRates) db.taskRates = [];
      if (!db.shiftRates) db.shiftRates = [];
      db.taskRates = db.taskRates.filter((r) => r.user_id !== userId)
        .concat((ratesTarefa || []).filter((r) => r.task_id).map((r) => ({
          id: uid(), user_id: userId, task_id: r.task_id,
          hourly_rate: r.hourly_rate != null && r.hourly_rate !== '' ? +r.hourly_rate : null,
          flat_amount: r.flat_amount != null && r.flat_amount !== '' ? +r.flat_amount : null,
        })));
      db.shiftRates = db.shiftRates.filter((r) => r.user_id !== userId)
        .concat((ratesTurno || []).filter((r) => r.period).map((r) => ({
          id: uid(), user_id: userId, period: r.period, amount: +r.amount || 0,
        })));
      salva();
      return espera(true);
    },

    /* ---- equipe ---- */
    async listaPessoas() {
      exigeAdmin(); carrega();
      return espera(db.profiles.map((p) => ({ ...p })).sort((a, b) => a.full_name.localeCompare(b.full_name)));
    },
    async criaPessoa({ username, full_name, password, role }) {
      exigeAdmin(); carrega();
      const u = String(username || '').trim().toLowerCase();
      if (!/^[a-z0-9._-]{2,40}$/.test(u)) throw new Error('Usuário inválido: use letras minúsculas, números, ponto, hífen ou _.');
      if (db.profiles.some((p) => p.username === u)) throw new Error(`Já existe alguém com o usuário "${u}".`);
      if (String(password || '').length < 4) throw new Error('A senha precisa ter pelo menos 4 caracteres.');
      const novo = { id: uid(), username: u, full_name: full_name || u, role: role || 'employee',
                     pay_mode: 'hourly', active: true };
      db.profiles.push(novo); db.senhas[u] = String(password); salva();
      return espera(novo);
    },
    async atualizaPessoa(id, patch) {
      exigeAdmin(); carrega();
      const p = db.profiles.find((x) => x.id === id);
      if (!p) throw new Error('Pessoa não encontrada.');
      Object.assign(p, patch); salva();
      if (usuario?.id === id) usuario = p;
      return espera(p);
    },
    async trocaSenha(id, senha) {
      carrega();
      if (!ehAdmin() && usuario?.id !== id) throw new Error('Sem permissão para trocar esta senha.');
      if (String(senha || '').length < 4) throw new Error('A senha precisa ter pelo menos 4 caracteres.');
      const p = db.profiles.find((x) => x.id === id);
      if (!p) throw new Error('Pessoa não encontrada.');
      db.senhas[p.username] = String(senha); salva();
      return espera(true);
    },
    async apagaPessoa(id) {
      exigeAdmin(); carrega();
      if (id === usuario?.id) throw new Error('Você não pode apagar a si mesmo.');
      const p = db.profiles.find((x) => x.id === id);
      db.profiles = db.profiles.filter((x) => x.id !== id);
      db.assignments = db.assignments.filter((a) => a.user_id !== id);
      db.companyAssignments = (db.companyAssignments || []).filter((a) => a.user_id !== id);
      const turnos = db.shifts.filter((s) => s.user_id === id).map((s) => s.id);
      db.shifts = db.shifts.filter((s) => s.user_id !== id);
      db.segments = db.segments.filter((sg) => !turnos.includes(sg.shift_id));
      if (p) delete db.senhas[p.username];
      salva();
      return espera(true);
    },

    /* ---- atribuições ---- */
    async listaAtribuicoes() {
      carrega();
      const todas = db.assignments.map((a) => ({ ...a }));
      return espera(ehAdmin() ? todas : todas.filter((a) => a.user_id === usuario?.id));
    },
    async defineAtribuicoes(userId, taskIds) {
      exigeAdmin(); carrega();
      db.assignments = db.assignments.filter((a) => a.user_id !== userId)
        .concat(taskIds.map((task_id) => ({ user_id: userId, task_id })));
      salva();
      return espera(true);
    },
    async tarefasDaPessoa(userId) {
      carrega();
      const ids = new Set(db.assignments.filter((a) => a.user_id === userId).map((a) => a.task_id));
      return espera(db.tasks.filter((t) => t.active && ids.has(t.id))
        .sort((a, b) => a.sort_order - b.sort_order).map((t) => ({ ...t })));
    },

    /* ---- ponto ---- */
    async turnoAberto(userId) {
      carrega();
      const t = db.shifts.find((s) => s.user_id === userId && !s.ended_at);
      if (!t) return espera(null);
      return espera({ ...t, segments: db.segments.filter((sg) => sg.shift_id === t.id)
        .sort((a, b) => a.started_at.localeCompare(b.started_at)).map((sg) => ({ ...sg })) });
    },
    async iniciaTurno(userId, opts = {}) {
      carrega();
      const { taskId = null, companyId = null, period = null, quando = new Date() } = opts;
      if (db.shifts.some((s) => s.user_id === userId && !s.ended_at))
        throw new Error('Já existe um turno aberto para esta pessoa.');
      const perfil = db.profiles.find((x) => x.id === userId);
      const modo = perfil?.pay_mode || 'hourly';
      const emp = companyId ? db.companies.find((c) => c.id === companyId) : null;
      if (companyId && !emp) throw new Error('Escolha uma empresa para começar.');
      if (!db.taskRates) db.taskRates = [];
      if (!db.shiftRates) db.shiftRates = [];

      const inicio = new Date(quando).toISOString();
      let flatTurno = null;
      let periodo = period || null;
      let trecho;

      if (modo === 'shift') {
        if (!periodo) throw new Error('Escolha o turno: manhã, tarde ou noite.');
        const sr = db.shiftRates.find((r) => r.user_id === userId && r.period === periodo);
        flatTurno = +sr?.amount || 0;
        const rotulo = { manha: 'Manhã', tarde: 'Tarde', noite: 'Noite' }[periodo] || periodo;
        trecho = {
          id: uid(), task_id: null, task_name: `Turno ${rotulo}`,
          hourly_rate: 0, flat_amount: null, period: periodo,
          started_at: inicio, ended_at: null,
        };
      } else {
        const t = db.tasks.find((x) => x.id === taskId);
        if (!t) throw new Error('Escolha uma tarefa para começar.');
        const tr = db.taskRates.find((r) => r.user_id === userId && r.task_id === taskId);
        if (modo === 'task') {
          trecho = {
            id: uid(), task_id: t.id, task_name: t.name,
            hourly_rate: 0, flat_amount: tr?.flat_amount != null ? +tr.flat_amount : +t.hourly_rate || 0,
            period: periodo, started_at: inicio, ended_at: null,
          };
        } else {
          trecho = {
            id: uid(), task_id: t.id, task_name: t.name,
            hourly_rate: tr?.hourly_rate != null ? +tr.hourly_rate : +t.hourly_rate || 0,
            flat_amount: null, period: periodo, started_at: inicio, ended_at: null,
          };
        }
      }

      const turno = {
        id: uid(), user_id: userId, started_at: inicio, ended_at: null, source: 'app', note: null,
        company_id: emp?.id ?? null, company_name: emp?.name ?? null,
        period: periodo, pay_mode: modo, flat_amount: flatTurno,
      };
      db.shifts.push(turno);
      db.segments.push({ ...trecho, shift_id: turno.id });
      salva();
      return espera(turno);
    },
    async trocaTarefa(shiftId, taskId, period = null, quando = new Date()) {
      carrega();
      const turno = db.shifts.find((s) => s.id === shiftId);
      if ((turno?.pay_mode || 'hourly') === 'shift') {
        throw new Error('Quem recebe por turno não troca de tarefa no meio.');
      }
      const t = db.tasks.find((x) => x.id === taskId);
      if (!t) throw new Error('Tarefa não encontrada.');
      if (!db.taskRates) db.taskRates = [];
      const tr = db.taskRates.find((r) => r.user_id === turno.user_id && r.task_id === taskId);
      const modo = turno.pay_mode || 'hourly';
      const periodo = period || turno.period || null;
      const agora = new Date(quando).toISOString();
      db.segments.filter((sg) => sg.shift_id === shiftId && !sg.ended_at)
        .forEach((sg) => { sg.ended_at = agora; });
      db.segments.push({
        id: uid(), shift_id: shiftId, task_id: t.id, task_name: t.name,
        hourly_rate: modo === 'task' ? 0 : (tr?.hourly_rate != null ? +tr.hourly_rate : +t.hourly_rate || 0),
        flat_amount: modo === 'task' ? (tr?.flat_amount != null ? +tr.flat_amount : +t.hourly_rate || 0) : null,
        period: periodo, started_at: agora, ended_at: null,
      });
      salva();
      return espera(true);
    },
    async fechaTurno(shiftId, quando = new Date()) {
      carrega();
      const s = db.shifts.find((x) => x.id === shiftId);
      if (!s) throw new Error('Turno não encontrado.');
      const agora = new Date(quando).toISOString();
      s.ended_at = agora;
      db.segments.filter((sg) => sg.shift_id === shiftId && !sg.ended_at)
        .forEach((sg) => { sg.ended_at = agora; });
      salva();
      return espera(s);
    },

    /* ---- consultas ---- */
    async listaTurnos({ userId = null, de = null, ate = null } = {}) {
      carrega();
      const alvo = ehAdmin() ? userId : usuario?.id;
      const dentro = db.shifts.filter((s) => {
        if (alvo && s.user_id !== alvo) return false;
        if (!ehAdmin() && s.user_id !== usuario?.id) return false;
        const ini = new Date(s.started_at);
        if (de && ini < new Date(de)) return false;
        if (ate && ini > new Date(ate)) return false;
        return true;
      });
      const porTurno = new Map();
      db.segments.forEach((sg) => {
        if (!porTurno.has(sg.shift_id)) porTurno.set(sg.shift_id, []);
        porTurno.get(sg.shift_id).push({ ...sg });
      });
      return espera(dentro
        .map((s) => ({ ...s, segments: (porTurno.get(s.id) || [])
          .sort((a, b) => a.started_at.localeCompare(b.started_at)) }))
        .sort((a, b) => b.started_at.localeCompare(a.started_at)));
    },

    async gravaTurnoManual({ user_id, started_at, ended_at, trechos, source = 'manual', note = null,
                             company_id = null, company_name = null }) {
      carrega();
      if (!ehAdmin() && user_id !== usuario?.id) throw new Error('Sem permissão.');
      const emp = company_id ? db.companies.find((c) => c.id === company_id) : null;
      const turno = {
        id: uid(), user_id, started_at: new Date(started_at).toISOString(),
        ended_at: ended_at ? new Date(ended_at).toISOString() : null, source, note,
        company_id: emp?.id ?? company_id ?? null,
        company_name: emp?.name ?? company_name ?? null,
      };
      db.shifts.push(turno);
      (trechos || []).forEach((tr) => db.segments.push({
        id: uid(), shift_id: turno.id, task_id: tr.task_id ?? null, task_name: tr.task_name,
        hourly_rate: +tr.hourly_rate || 0,
        started_at: new Date(tr.started_at).toISOString(),
        ended_at: tr.ended_at ? new Date(tr.ended_at).toISOString() : null,
      }));
      salva();
      return espera(turno);
    },

    async atualizaTurno(shiftId, { started_at, ended_at, note, trechos, company_id, company_name }) {
      exigeAdmin(); carrega();
      const s = db.shifts.find((x) => x.id === shiftId);
      if (!s) throw new Error('Turno não encontrado.');
      if (started_at) s.started_at = new Date(started_at).toISOString();
      if (ended_at !== undefined) s.ended_at = ended_at ? new Date(ended_at).toISOString() : null;
      if (note !== undefined) s.note = note;
      if (company_id !== undefined) {
        const emp = company_id ? db.companies.find((c) => c.id === company_id) : null;
        s.company_id = emp?.id ?? company_id ?? null;
        s.company_name = company_name ?? emp?.name ?? null;
      } else if (company_name !== undefined) {
        s.company_name = company_name;
      }
      if (trechos) {
        db.segments = db.segments.filter((sg) => sg.shift_id !== shiftId);
        trechos.forEach((tr) => db.segments.push({
          id: uid(), shift_id: shiftId, task_id: tr.task_id ?? null, task_name: tr.task_name,
          hourly_rate: +tr.hourly_rate || 0,
          started_at: new Date(tr.started_at).toISOString(),
          ended_at: tr.ended_at ? new Date(tr.ended_at).toISOString() : null,
        }));
      }
      salva();
      return espera(s);
    },

    async apagaTurno(shiftId) {
      exigeAdmin(); carrega();
      db.shifts = db.shifts.filter((s) => s.id !== shiftId);
      db.segments = db.segments.filter((sg) => sg.shift_id !== shiftId);
      salva();
      return espera(true);
    },

    /* ---- utilidades da demo ---- */
    async zeraDemo() {
      try { localStorage.removeItem(CHAVE); localStorage.removeItem(SESSAO); } catch { /* ok */ }
      db = null; usuario = null;
      return true;
    },
    dicasDeAcesso: () => [
      { username: 'admin', senha: '1234', papel: 'Super admin' },
      { username: 'maria', senha: '1234', papel: 'Funcionária (2 empresas, 3 tarefas)' },
      { username: 'joao',  senha: '1234', papel: 'Funcionário (1 empresa, 1 tarefa)' },
    ],
  };
}
