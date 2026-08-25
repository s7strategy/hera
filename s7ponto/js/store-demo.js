/* ==========================================================================
   S7 PONTO — armazém do MODO DEMONSTRAÇÃO.
   Tudo fica no localStorage do próprio navegador, com três meses de
   histórico de mentira já semeado, só para você ver o sistema funcionando
   antes de ligar no Supabase. Nada sai do aparelho.
   ========================================================================== */
import { uid, diaChave, somaDias, inicioDoDia } from './util.js';

const CHAVE = 's7ponto.demo.v1';
const SESSAO = 's7ponto.demo.sessao';
const espera = (v) => new Promise((r) => setTimeout(() => r(v), 60));

const PALETA = ['#d95926', '#199e70', '#3987e5', '#c98500', '#d55181', '#7d9c2f', '#9085e9', '#e66767'];

/* ---------- semeadura ---------------------------------------------------- */

function semear() {
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

  // gerador pseudoaleatório com semente: o histórico não muda a cada reload
  let s = 20260825;
  const rnd = () => ((s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);

  const shifts = [], segments = [];
  const pessoas = [
    { p: maria, tarefas: [tasks[0], tasks[2], tasks[3]], entrada: 8,  jornada: 8   },
    { p: joao,  tarefas: [tasks[1]],                     entrada: 13, jornada: 6.5 },
  ];

  for (let atras = 96; atras >= 1; atras--) {
    const dia = inicioDoDia(somaDias(new Date(), -atras));
    if (dia.getDay() === 0) continue;                     // domingo folga
    for (const { p, tarefas, entrada, jornada } of pessoas) {
      if (rnd() < 0.12) continue;                         // uma falta aqui e ali
      const ini = new Date(dia);
      ini.setHours(entrada, Math.floor(rnd() * 25), 0, 0);
      const dur = jornada + (rnd() - 0.45) * 2.2;
      const fim = new Date(ini.getTime() + dur * 3600000);

      const turno = { id: uid(), user_id: p.id, started_at: ini.toISOString(),
                      ended_at: fim.toISOString(), source: 'app', note: null };
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
  return { profiles, tasks, assignments, shifts, segments, senhas: { admin: '1234', maria: '1234', joao: '1234' } };
}

/* ---------- persistência ------------------------------------------------- */

function ler() {
  try {
    const cru = localStorage.getItem(CHAVE);
    if (cru) return JSON.parse(cru);
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
      const novo = { id: uid(), username: u, full_name: full_name || u, role: role || 'employee', active: true };
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
    async iniciaTurno(userId, taskId, quando = new Date()) {
      carrega();
      if (db.shifts.some((s) => s.user_id === userId && !s.ended_at))
        throw new Error('Já existe um turno aberto para esta pessoa.');
      const t = db.tasks.find((x) => x.id === taskId);
      if (!t) throw new Error('Escolha uma tarefa para começar.');
      const turno = { id: uid(), user_id: userId, started_at: new Date(quando).toISOString(),
                      ended_at: null, source: 'app', note: null };
      db.shifts.push(turno);
      db.segments.push({ id: uid(), shift_id: turno.id, task_id: t.id, task_name: t.name,
                         hourly_rate: t.hourly_rate, started_at: turno.started_at, ended_at: null });
      salva();
      return espera(turno);
    },
    async trocaTarefa(shiftId, taskId, quando = new Date()) {
      carrega();
      const t = db.tasks.find((x) => x.id === taskId);
      if (!t) throw new Error('Tarefa não encontrada.');
      const agora = new Date(quando).toISOString();
      db.segments.filter((sg) => sg.shift_id === shiftId && !sg.ended_at)
        .forEach((sg) => { sg.ended_at = agora; });
      db.segments.push({ id: uid(), shift_id: shiftId, task_id: t.id, task_name: t.name,
                         hourly_rate: t.hourly_rate, started_at: agora, ended_at: null });
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

    async gravaTurnoManual({ user_id, started_at, ended_at, trechos, source = 'manual', note = null }) {
      carrega();
      if (!ehAdmin() && user_id !== usuario?.id) throw new Error('Sem permissão.');
      const turno = { id: uid(), user_id, started_at: new Date(started_at).toISOString(),
                      ended_at: ended_at ? new Date(ended_at).toISOString() : null, source, note };
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

    async atualizaTurno(shiftId, { started_at, ended_at, note, trechos }) {
      exigeAdmin(); carrega();
      const s = db.shifts.find((x) => x.id === shiftId);
      if (!s) throw new Error('Turno não encontrado.');
      if (started_at) s.started_at = new Date(started_at).toISOString();
      if (ended_at !== undefined) s.ended_at = ended_at ? new Date(ended_at).toISOString() : null;
      if (note !== undefined) s.note = note;
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
      { username: 'maria', senha: '1234', papel: 'Funcionária (3 tarefas)' },
      { username: 'joao',  senha: '1234', papel: 'Funcionário (1 tarefa)' },
    ],
  };
}
