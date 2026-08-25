/* ==========================================================================
   S7 PONTO — a tela principal: começar turno, trocar tarefa, fechar turno.
   Tudo aqui é grande, direto e em português de gente.
   ========================================================================== */
import { CONFIG } from './config.js';
import { store } from './store.js';
import {
  esc, saudacao, dataLonga, hora, cronometro, horas, money, plural, maiuscula,
  paraInputLocal, deInputLocal, somaDias, horasEntre,
} from './util.js';
import { $, ICONE, abreFolha, confirma, torrada, comBotaoOcupado, carregando } from './ui.js';
import { trilhaDoTurno, tirasDaSemana } from './charts.js';
import {
  pintaTrechos, horasDoTurno, valorDoTurno, resumoDoDia, resumoDaSemana,
  serieDaSemana, agrega,
} from './metricas.js';

export async function telaDePonto(raiz, ctx) {
  const { usuario } = ctx;
  let turno = null;          // turno aberto (com trechos) ou null
  let tarefas = [];          // tarefas liberadas para esta pessoa
  let recentes = [];         // turnos dos últimos 30 dias, para hoje/semana
  let tique = null;          // cronômetro
  let lembrete = null;       // lembrete de troca de tarefa

  raiz.innerHTML = carregando('Buscando seu ponto…');

  async function buscar() {
    const desde = somaDias(new Date(), -35);
    const [t, tf, rec] = await Promise.all([
      store.turnoAberto(usuario.id),
      store.tarefasDaPessoa(usuario.id),
      store.listaTurnos({ userId: usuario.id, de: desde }),
    ]);
    tarefas = tf;
    recentes = pintaTrechos(rec, tf);
    turno = t;
    if (turno) pintaTrechos([turno], tf);
  }

  /* ---------- o trecho que está rolando agora ---------- */
  const trechoAtual = () => turno?.segments?.find((s) => !s.ended_at) || null;

  /* ---------- ações ---------- */

  async function comecar(taskId, botao) {
    try {
      await comBotaoOcupado(botao, 'Começando…', () => store.iniciaTurno(usuario.id, taskId));
      await buscar();
      desenha();
      const t = tarefas.find((x) => x.id === taskId);
      torrada(`Turno aberto em ${t?.name || 'tarefa'}. Bom trabalho!`, 'bom');
    } catch (e) { torrada(e.message, 'ruim', 6); }
  }

  function escolheTarefa({ titulo, sub, aoEscolher, excluir = null }) {
    const lista = tarefas.filter((t) => t.id !== excluir);
    if (!lista.length) {
      torrada('Não há outra tarefa liberada para você.', 'ruim', 5);
      return;
    }
    abreFolha({
      titulo, sub,
      corpo: `<div class="escolhas">${lista.map((t) => `
        <button class="escolha" data-id="${esc(t.id)}">
          <span class="escolha-cor" style="background:${esc(t.color)}"></span>
          <span class="escolha-texto">
            <span class="escolha-nome">${esc(t.name)}</span>
            <span class="escolha-preco">${esc(money(t.hourly_rate))} por hora</span>
          </span>
          <span class="escolha-seta">${ICONE.seta}</span>
        </button>`).join('')}</div>`,
      aoMontar: (caixa, fechar) => {
        caixa.querySelectorAll('.escolha').forEach((b) => {
          b.addEventListener('click', () => { fechar('escolha'); aoEscolher(b.dataset.id, b); });
        });
      },
    });
  }

  function aoClicarComecar(botao) {
    if (!tarefas.length) {
      torrada('Você ainda não tem tarefa liberada. Fale com a administração.', 'ruim', 7);
      return;
    }
    // uma tarefa só? não pergunta nada, só começa.
    if (tarefas.length === 1) return comecar(tarefas[0].id, botao);
    escolheTarefa({
      titulo: 'O que você vai fazer agora?',
      sub: 'Toque na tarefa para começar o turno.',
      aoEscolher: (id) => comecar(id),
    });
  }

  function aoClicarTrocar() {
    const atual = trechoAtual();
    escolheTarefa({
      titulo: 'Para qual tarefa você mudou?',
      sub: `Vou fechar “${atual?.task_name || 'a atual'}” agora e começar a contar a nova.`,
      excluir: atual?.task_id,
      aoEscolher: async (id) => {
        try {
          await store.trocaTarefa(turno.id, id);
          await buscar(); desenha();
          const t = tarefas.find((x) => x.id === id);
          torrada(`Anotado! Agora contando ${t?.name || 'a nova tarefa'}.`, 'bom');
          reiniciaLembrete();
        } catch (e) { torrada(e.message, 'ruim', 6); }
      },
    });
  }

  async function aoClicarFechar() {
    const h = horasDoTurno(turno);
    const v = valorDoTurno(turno);
    const quantas = new Set((turno.segments || []).map((s) => s.task_name)).size;
    const certeza = await confirma({
      titulo: 'Fechar o turno agora?',
      texto: `Você trabalhou ${horas(h)} em ${plural(quantas, 'tarefa', 'tarefas')} — ${money(v)}.`,
      ok: 'Sim, fechar turno',
      cancelar: 'Ainda não',
    });
    if (!certeza) return;
    try {
      await store.fechaTurno(turno.id);
      const resumo = { h, v, quantas };
      await buscar(); desenha();
      festeja(resumo);
    } catch (e) { torrada(e.message, 'ruim', 6); }
  }

  function festeja({ h, v }) {
    abreFolha({
      titulo: 'Turno fechado 🎉',
      sub: 'Está tudo registrado. Bom descanso!',
      corpo: `
        <div class="grade-metricas" style="margin-bottom:18px">
          <div class="metrica"><div class="metrica-rotulo">Tempo do turno</div>
            <div class="metrica-valor">${esc(horas(h))}</div></div>
          <div class="metrica"><div class="metrica-rotulo">Valor do turno</div>
            <div class="metrica-valor" style="color:var(--salvia-alt)">${esc(money(v))}</div></div>
        </div>
        <button class="btn btn-primario btn-medio btn-largo" data-fecha>Beleza!</button>`,
      aoMontar: (caixa, fechar) => {
        $('[data-fecha]', caixa).addEventListener('click', () => fechar('ok'));
      },
    });
  }

  /** Turno esquecido aberto: oferece fechar com o horário certo. */
  async function corrigeEsquecido() {
    const abertoHa = horasEntre(turno.started_at, new Date());
    abreFolha({
      titulo: 'Esqueceu de fechar?',
      sub: `Este turno está aberto há ${horas(abertoHa)}. Se você já foi embora, ajuste a hora de saída aqui.`,
      corpo: `
        <label class="campo">
          <span class="campo-rotulo">A que horas você realmente saiu?</span>
          <input class="entrada" type="datetime-local" id="hora-saida"
                 value="${esc(paraInputLocal(new Date()))}"
                 min="${esc(paraInputLocal(new Date(turno.started_at)))}"
                 max="${esc(paraInputLocal(new Date()))}">
        </label>
        <div class="linha-botoes">
          <button class="btn btn-fantasma btn-medio" data-cancela>Deixar aberto</button>
          <button class="btn btn-primario btn-medio" data-confirma>Fechar com esta hora</button>
        </div>`,
      aoMontar: (caixa, fechar) => {
        $('[data-cancela]', caixa).addEventListener('click', () => fechar('cancela'));
        $('[data-confirma]', caixa).addEventListener('click', async (ev) => {
          const quando = deInputLocal($('#hora-saida', caixa).value);
          if (!quando || quando < new Date(turno.started_at)) {
            torrada('A saída precisa ser depois da entrada.', 'ruim');
            return;
          }
          try {
            await comBotaoOcupado(ev.currentTarget, 'Fechando…',
              () => store.fechaTurno(turno.id, quando));
            fechar('ok');
            await buscar(); desenha();
            torrada('Turno corrigido e fechado.', 'bom');
          } catch (e) { torrada(e.message, 'ruim', 6); }
        });
      },
    });
  }

  /* ---------- lembrete gentil de troca de tarefa ---------- */

  function reiniciaLembrete() {
    clearInterval(lembrete);
    lembrete = null;
    if (!turno || tarefas.length < 2 || !CONFIG.REMINDER_MINUTES) return;
    lembrete = setInterval(() => {
      const atual = trechoAtual();
      if (!atual) return;
      torrada(`Ainda em ${atual.task_name}? Se mudou de tarefa, toque em “Troquei de tarefa”.`, 'lembrete', 8);
    }, CONFIG.REMINDER_MINUTES * 60 * 1000);
  }

  /* ---------- desenho ---------- */

  function desenha() {
    const hojeR = resumoDoDia(turno ? [...recentes.filter((t) => t.id !== turno.id), turno] : recentes);
    const semanaR = resumoDaSemana(turno ? [...recentes.filter((t) => t.id !== turno.id), turno] : recentes);
    const primeiroNome = usuario.full_name.split(' ')[0];

    raiz.innerHTML = `
      <header class="bloco" style="margin-bottom:20px">
        <h1 class="titulo" style="font-size:34px">${esc(saudacao())}, ${esc(primeiroNome)}.</h1>
        <p class="apagado">${esc(maiuscula(dataLonga(new Date())))}</p>
      </header>

      <div id="area-turno"></div>

      <section class="cartao" style="margin-top:20px">
        <div class="cartao-topo"><h2 class="cartao-titulo">Sua semana</h2>
          <span class="ficha ficha-neutra">${esc(plural(semanaR.dias, 'dia', 'dias'))}</span></div>
        <div id="tiras-semana"></div>
        <div class="grade-metricas" style="margin-top:16px">
          <div class="metrica"><div class="metrica-rotulo">Horas na semana</div>
            <div class="metrica-valor">${esc(horas(semanaR.horas))}</div></div>
          <div class="metrica"><div class="metrica-rotulo">A receber na semana</div>
            <div class="metrica-valor" style="color:var(--salvia-alt)">${esc(money(semanaR.valor))}</div></div>
        </div>
      </section>`;

    const area = $('#area-turno', raiz);
    turno ? desenhaEmTurno(area, hojeR) : desenhaParado(area, hojeR);

    tirasDaSemana($('#tiras-semana', raiz), serieDaSemana(new Date(),
      agrega(turno ? [...recentes.filter((t) => t.id !== turno.id), turno] : recentes).porDia));
  }

  function desenhaParado(area, hojeR) {
    const semTarefa = !tarefas.length;
    const umaSo = tarefas.length === 1;
    area.innerHTML = `
      <button class="btn-gigante ${semTarefa ? '' : 'pulsa'}" id="btn-comecar" ${semTarefa ? 'disabled' : ''}>
        ${ICONE.play}
        <span>Iniciar turno</span>
        <span class="btn-legenda">${semTarefa
          ? 'nenhuma tarefa liberada ainda'
          : umaSo ? `em ${esc(tarefas[0].name)}` : 'você escolhe a tarefa'}</span>
      </button>

      ${semTarefa ? `
        <div class="recado ruim" style="margin-top:16px">
          <span class="recado-emoji">🔒</span>
          <span>Você ainda não tem nenhuma tarefa liberada. Peça para a administração liberar
                no painel — aí o botão acende.</span>
        </div>` : ''}

      <div class="grade-metricas" style="margin-top:18px">
        <div class="metrica"><div class="metrica-rotulo">Você fez hoje</div>
          <div class="metrica-valor">${esc(hojeR.horas ? horas(hojeR.horas) : '—')}</div>
          <div class="metrica-nota">${hojeR.turnos ? esc(plural(hojeR.turnos, 'turno', 'turnos')) : 'nenhum turno ainda'}</div></div>
        <div class="metrica"><div class="metrica-rotulo">Valor de hoje</div>
          <div class="metrica-valor" style="color:var(--salvia-alt)">${esc(money(hojeR.valor))}</div></div>
      </div>`;

    const b = $('#btn-comecar', area);
    if (b && !semTarefa) b.addEventListener('click', () => aoClicarComecar(b));
  }

  function desenhaEmTurno(area, hojeR) {
    const atual = trechoAtual();
    const podeTrocar = tarefas.length > 1;
    const abertoHa = horasEntre(turno.started_at, new Date());
    const esquecido = abertoHa >= CONFIG.LONG_SHIFT_HOURS;

    area.innerHTML = `
      <section class="turno-vivo">
        <div class="turno-estado"><span class="pisca"></span> Você está em turno</div>
        <div class="cronometro num" id="cronometro">00:00:00</div>
        <p class="cronometro-legenda">começou às ${esc(hora(turno.started_at))}</p>

        <div class="turno-tarefa">
          <span class="ficha-ponto" style="background:${esc(atual?.cor || 'var(--terracota)')}"></span>
          ${esc(atual?.task_name || 'Sem tarefa')}
          <span class="apagado num" style="font-size:13px">${esc(money(atual?.hourly_rate || 0))}/h</span>
        </div>

        <div id="trilha-turno"></div>

        <div class="turno-ganho">
          <div><div class="metrica-rotulo">Neste turno</div>
            <div class="metrica-valor num" id="ganho-turno">—</div></div>
          <div><div class="metrica-rotulo">No dia todo</div>
            <div class="metrica-valor num" id="ganho-dia">${esc(money(hojeR.valor))}</div></div>
        </div>
      </section>

      ${esquecido ? `
        <button class="recado ruim" id="btn-esquecido" style="margin-top:16px;width:100%;text-align:left">
          <span class="recado-emoji">⏰</span>
          <span>Este turno está aberto há <strong>${esc(horas(abertoHa))}</strong>.
                Se você já saiu, toque aqui para corrigir a hora de saída.</span>
        </button>` : ''}

      <div style="margin-top:18px;display:flex;flex-direction:column;gap:11px">
        ${podeTrocar ? `
          <button class="btn btn-medio" id="btn-trocar">
            ${ICONE.trocar}<span>Troquei de tarefa</span>
          </button>` : ''}
        <button class="btn-gigante parar" id="btn-fechar">
          ${ICONE.parar}
          <span>Fechar turno</span>
          <span class="btn-legenda">encerra o dia e salva as horas</span>
        </button>
      </div>

      ${podeTrocar ? `
        <div class="recado" style="margin-top:16px">
          <span class="recado-emoji">💡</span>
          <span>Mudou de atividade no meio do turno? Toque em <strong>“Troquei de tarefa”</strong>.
                Cada tarefa tem um valor de hora diferente — assim a conta sai certinha.</span>
        </div>` : ''}`;

    $('#btn-fechar', area).addEventListener('click', aoClicarFechar);
    $('#btn-trocar', area)?.addEventListener('click', aoClicarTrocar);
    $('#btn-esquecido', area)?.addEventListener('click', corrigeEsquecido);

    trilhaDoTurno($('#trilha-turno', area),
      (turno.segments || []).map((s) => ({ ...s, cor: s.cor || 'var(--terracota)' })));

    pulsa();
  }

  /* ---------- cronômetro ---------- */

  function pulsa() {
    clearInterval(tique);
    const alvo = $('#cronometro', raiz);
    if (!alvo || !turno) return;
    const passo = () => {
      const rel = $('#cronometro', raiz);
      if (!rel || !turno) return clearInterval(tique);
      rel.textContent = cronometro(Date.now() - new Date(turno.started_at).getTime());
      const g = $('#ganho-turno', raiz);
      if (g) g.textContent = money(valorDoTurno(turno));
    };
    passo();
    tique = setInterval(passo, 1000);
  }

  await buscar();
  desenha();
  reiniciaLembrete();

  return {
    destruir() { clearInterval(tique); clearInterval(lembrete); },
    async recarrega() { await buscar(); desenha(); reiniciaLembrete(); },
  };
}
