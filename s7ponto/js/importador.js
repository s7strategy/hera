/* ==========================================================================
   S7 PONTO — importador de planilhas.
   Aceita CSV, XLSX e XLS. Quatro passos: arquivo → colunas → nomes → conferir.
   ========================================================================== */
import { store } from './store.js';
import {
  esc, chave, leData, leHora, leNumero, juntaDataHora, dataBR, hora,
  horas, money, num, plural, maiuscula, dataLonga,
} from './util.js';
import { $, $$, ICONE, torrada, confirma, vazio, comBotaoOcupado } from './ui.js';

const CDN_XLSX = 'https://cdn.sheetjs.com/xlsx-0.20.3/package/xlsx.mjs';

/** Os campos que o sistema entende, e como adivinhá-los pelo cabeçalho. */
const CAMPOS = [
  { id: 'pessoa',  nome: 'Pessoa',          obrigatorio: true,
    dica: 'nome ou usuário de quem trabalhou',
    pistas: /pessoa|funcionar|colaborad|empregad|nome|usuario|user|equipe/ },
  { id: 'data',    nome: 'Data',            obrigatorio: true,
    dica: 'dia do turno',
    pistas: /^data|^dia|date|competencia/ },
  { id: 'entrada', nome: 'Hora de entrada', obrigatorio: false,
    dica: 'que horas começou',
    pistas: /entrada|inicio|início|comec|começ|start|^de$|abertura/ },
  { id: 'saida',   nome: 'Hora de saída',   obrigatorio: false,
    dica: 'que horas terminou',
    pistas: /saida|saída|fim|termin|encerr|end|^ate$|^até$|fechamento/ },
  { id: 'horas',   nome: 'Total de horas',  obrigatorio: false,
    dica: 'use quando a planilha não tem entrada/saída',
    pistas: /horas|total|duracao|duração|carga|jornada|trabalhad/ },
  { id: 'tarefa',  nome: 'Tarefa',          obrigatorio: false,
    dica: 'se ficar vazio, você escolhe uma tarefa padrão',
    pistas: /tarefa|task|funcao|função|atividade|servic|serviç|setor|cargo|projeto/ },
];

/* ==========================================================================
   Leitura de arquivo
   ========================================================================== */

/** Descobre o separador olhando a primeira linha de verdade. */
function separadorDo(texto) {
  const linha = texto.split(/\r?\n/).find((l) => l.trim()) || '';
  const contas = [[';', 0], [',', 0], ['\t', 0]].map(([sep]) =>
    [sep, (linha.match(new RegExp(`\\${sep === '\t' ? 't' : sep}`, 'g')) || []).length]);
  contas.sort((a, b) => b[1] - a[1]);
  return contas[0][1] ? contas[0][0] : ';';
}

function leCSV(texto) {
  const sep = separadorDo(texto);
  const linhas = [];
  let campo = '', linha = [], aspas = false;

  for (let i = 0; i < texto.length; i++) {
    const c = texto[i];
    if (aspas) {
      if (c === '"') {
        if (texto[i + 1] === '"') { campo += '"'; i++; }
        else aspas = false;
      } else campo += c;
    } else if (c === '"') aspas = true;
    else if (c === sep) { linha.push(campo); campo = ''; }
    else if (c === '\n') { linha.push(campo); linhas.push(linha); linha = []; campo = ''; }
    else if (c !== '\r') campo += c;
  }
  if (campo || linha.length) { linha.push(campo); linhas.push(linha); }
  return linhas.map((l) => l.map((c) => c.trim())).filter((l) => l.some((c) => c !== ''));
}

async function leXLSX(buffer) {
  const XLSX = await import(/* @vite-ignore */ CDN_XLSX);
  const wb = XLSX.read(buffer, { type: 'array', cellDates: true });
  const ws = wb.Sheets[wb.SheetNames[0]];
  return XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, blankrows: false, defval: '' })
    .filter((l) => l.some((c) => c !== '' && c != null));
}

async function leArquivo(file) {
  const ext = file.name.toLowerCase().split('.').pop();
  if (ext === 'csv' || ext === 'txt') {
    let texto = await file.text();
    if (texto.charCodeAt(0) === 0xFEFF) texto = texto.slice(1);
    return leCSV(texto);
  }
  if (ext === 'xlsx' || ext === 'xls' || ext === 'xlsm') {
    return leXLSX(await file.arrayBuffer());
  }
  throw new Error('Formato não reconhecido. Envie um arquivo .csv, .xlsx ou .xls.');
}

/* ==========================================================================
   Montagem da tela
   ========================================================================== */

export function montaImportador(alvo, { pessoas, tarefas, aoTerminar }) {
  let passo = 1;
  let nomeArquivo = '';
  let cabecalho = [];
  let dados = [];              // linhas cruas (sem o cabeçalho)
  let mapa = {};               // campo -> índice da coluna (-1 = nenhum)
  let vinculoPessoas = {};     // nome cru -> id do perfil ('' = pular)
  let vinculoTarefas = {};     // nome cru -> id da tarefa
  let tarefaPadrao = tarefas.find((t) => t.active)?.id || '';
  let senhaPadrao = '1234';

  const ativas = tarefas.filter((t) => t.active);

  const desenha = () => {
    alvo.innerHTML = `
      <div class="passo-trilha">
        ${[1, 2, 3, 4].map((n) => `<div class="passo ${n < passo ? 'feito' : n === passo ? 'agora' : ''}"></div>`).join('')}
      </div>
      <div id="passo-corpo"></div>`;
    ({ 1: passoArquivo, 2: passoColunas, 3: passoNomes, 4: passoConferir }[passo])($('#passo-corpo', alvo));
  };

  /* ---------- passo 1: arquivo ---------- */

  function passoArquivo(caixa) {
    caixa.innerHTML = `
      <div class="recado info" style="margin-bottom:16px">
        <span class="recado-emoji">📄</span>
        <span>Traga a planilha que você já usa. O ideal é ter uma linha por turno, com
              <strong>pessoa, data, entrada e saída</strong>. Se a sua só tem o total de horas
              do dia, também serve.</span>
      </div>

      <div class="solta" id="solta" role="button" tabindex="0">
        <span class="solta-emoji">📊</span>
        <p class="solta-titulo">Escolher planilha</p>
        <p class="apagado">Arraste aqui ou toque para procurar · .xlsx, .xls ou .csv</p>
      </div>
      <input type="file" id="arquivo" accept=".csv,.xlsx,.xls,.xlsm,text/csv" hidden>
      <p class="campo-erro" id="erro-arquivo" hidden></p>`;

    const solta = $('#solta', caixa);
    const input = $('#arquivo', caixa);
    const erro = $('#erro-arquivo', caixa);

    const abrir = () => input.click();
    solta.addEventListener('click', abrir);
    solta.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); abrir(); } });
    ['dragenter', 'dragover'].forEach((e) => solta.addEventListener(e, (ev) => {
      ev.preventDefault(); solta.classList.add('sobre');
    }));
    ['dragleave', 'drop'].forEach((e) => solta.addEventListener(e, () => solta.classList.remove('sobre')));
    solta.addEventListener('drop', (ev) => {
      ev.preventDefault();
      if (ev.dataTransfer.files[0]) carrega(ev.dataTransfer.files[0]);
    });
    input.addEventListener('change', () => { if (input.files[0]) carrega(input.files[0]); });

    async function carrega(file) {
      erro.hidden = true;
      solta.innerHTML = '<div class="giro" style="margin:0 auto"></div><p style="margin-top:12px">Lendo a planilha…</p>';
      try {
        const linhas = await leArquivo(file);
        if (linhas.length < 2) throw new Error('A planilha parece vazia — preciso de um cabeçalho e pelo menos uma linha.');
        nomeArquivo = file.name;
        cabecalho = linhas[0].map((c) => String(c ?? '').trim());
        dados = linhas.slice(1);
        adivinhaColunas();
        passo = 2;
        desenha();
      } catch (e) {
        erro.textContent = e.message;
        erro.hidden = false;
        passoArquivo(caixa);
      }
    }
  }

  function adivinhaColunas() {
    mapa = {};
    const usados = new Set();
    for (const campo of CAMPOS) {
      const i = cabecalho.findIndex((h, idx) => !usados.has(idx) && campo.pistas.test(chave(h)));
      mapa[campo.id] = i;
      if (i >= 0) usados.add(i);
    }
  }

  /* ---------- passo 2: colunas ---------- */

  function passoColunas(caixa) {
    const exemplo = (i) => {
      if (i < 0) return '';
      const v = dados.slice(0, 3).map((l) => l[i]).filter((x) => x !== '' && x != null)[0];
      return v == null ? '' : String(v instanceof Date ? dataBR(v) : v).slice(0, 26);
    };

    caixa.innerHTML = `
      <div class="cartao">
        <div class="cartao-topo">
          <h2 class="cartao-titulo">De onde vem cada coisa?</h2>
          <span class="ficha ficha-neutra">${esc(nomeArquivo)}</span>
        </div>
        <p class="apagado" style="margin-bottom:14px">
          Já adivinhei o que deu. Confira e ajuste o que estiver errado.
          ${esc(plural(dados.length, 'linha encontrada', 'linhas encontradas'))}.
        </p>

        ${CAMPOS.map((c) => `
          <div class="mapa-coluna">
            <div>
              <div class="mapa-coluna-nome">${esc(c.nome)}${c.obrigatorio ? ' <span style="color:var(--terracota-alt)">*</span>' : ''}</div>
              <div class="apagado" style="font-size:12px">${esc(c.dica)}</div>
            </div>
            <div>
              <select class="entrada" data-campo="${c.id}" style="min-height:44px;padding:8px 12px">
                <option value="-1">— não tem —</option>
                ${cabecalho.map((h, i) => `<option value="${i}" ${mapa[c.id] === i ? 'selected' : ''}>${esc(h || `coluna ${i + 1}`)}</option>`).join('')}
              </select>
              <div class="mapa-coluna-exemplo" data-ex="${c.id}">${esc(exemplo(mapa[c.id]))}</div>
            </div>
          </div>`).join('')}
      </div>

      <div class="recado" id="aviso-colunas" hidden style="margin-top:16px">
        <span class="recado-emoji">⚠️</span><span id="aviso-texto"></span>
      </div>

      <div class="linha-botoes" style="margin-top:18px">
        <button class="btn btn-medio btn-fantasma" data-volta>Trocar planilha</button>
        <button class="btn btn-primario btn-medio" data-segue>Continuar</button>
      </div>`;

    const aviso = $('#aviso-colunas', caixa);
    const avisoTexto = $('#aviso-texto', caixa);

    const revisa = () => {
      const faltando = CAMPOS.filter((c) => c.obrigatorio && mapa[c.id] < 0).map((c) => c.nome);
      const semHorario = mapa.entrada < 0 && mapa.horas < 0;
      let msg = '';
      if (faltando.length) msg = `Preciso saber de onde vem: ${faltando.join(' e ')}.`;
      else if (semHorario) msg = 'Preciso da hora de entrada, ou então de uma coluna com o total de horas do dia.';
      else if (mapa.entrada >= 0 && mapa.saida < 0) msg = 'Sem a hora de saída, cada turno entra em aberto e você terá que fechar na mão. Melhor apontar a coluna de saída, se existir.';
      aviso.hidden = !msg;
      avisoTexto.textContent = msg;
      $('[data-segue]', caixa).disabled = !!(faltando.length || semHorario);
    };

    $$('[data-campo]', caixa).forEach((s) => s.addEventListener('change', () => {
      mapa[s.dataset.campo] = +s.value;
      $(`[data-ex="${s.dataset.campo}"]`, caixa).textContent = exemplo(+s.value);
      revisa();
    }));
    revisa();

    $('[data-volta]', caixa).addEventListener('click', () => { passo = 1; desenha(); });
    $('[data-segue]', caixa).addEventListener('click', () => { preparaVinculos(); passo = 3; desenha(); });
  }

  /* ---------- passo 3: nomes ---------- */

  const nomesCrus = (campo) => [...new Set(dados
    .map((l) => String(l[mapa[campo]] ?? '').trim())
    .filter(Boolean))];

  function preparaVinculos() {
    vinculoPessoas = {};
    for (const cru of nomesCrus('pessoa')) {
      const k = chave(cru);
      const achou = pessoas.find((p) => chave(p.username) === k || chave(p.full_name) === k)
        || pessoas.find((p) => chave(p.full_name).startsWith(k) || k.startsWith(chave(p.username)));
      vinculoPessoas[cru] = achou ? achou.id : '__novo__';
    }
    vinculoTarefas = {};
    if (mapa.tarefa >= 0) {
      for (const cru of nomesCrus('tarefa')) {
        const k = chave(cru);
        const achou = ativas.find((t) => chave(t.name) === k)
          || ativas.find((t) => chave(t.name).startsWith(k) || k.startsWith(chave(t.name)));
        vinculoTarefas[cru] = achou ? achou.id : (tarefaPadrao || '');
      }
    }
  }

  function passoNomes(caixa) {
    const crusPessoas = nomesCrus('pessoa');
    const crusTarefas = mapa.tarefa >= 0 ? nomesCrus('tarefa') : [];
    const novos = crusPessoas.filter((c) => vinculoPessoas[c] === '__novo__');

    caixa.innerHTML = `
      <div class="cartao">
        <div class="cartao-topo"><h2 class="cartao-titulo">Quem é quem</h2></div>
        <p class="apagado" style="margin-bottom:14px">
          Liguei os nomes da planilha às pessoas já cadastradas. Confira os que ficaram como “criar”.
        </p>
        ${crusPessoas.map((cru) => `
          <div class="mapa-coluna">
            <div class="mapa-coluna-nome">${esc(cru)}</div>
            <select class="entrada" data-pessoa="${esc(cru)}" style="min-height:44px;padding:8px 12px">
              <option value="__novo__" ${vinculoPessoas[cru] === '__novo__' ? 'selected' : ''}>➕ criar acesso novo</option>
              <option value="" ${vinculoPessoas[cru] === '' ? 'selected' : ''}>⨯ pular estas linhas</option>
              ${pessoas.map((p) => `<option value="${esc(p.id)}" ${vinculoPessoas[cru] === p.id ? 'selected' : ''}>${esc(p.full_name)} (@${esc(p.username)})</option>`).join('')}
            </select>
          </div>`).join('')}

        <div id="bloco-senha" ${novos.length ? '' : 'hidden'} style="margin-top:16px">
          <label class="campo" style="margin-bottom:0">
            <span class="campo-rotulo">Senha inicial de quem for criado agora</span>
            <input class="entrada" id="senha-nova" value="${esc(senhaPadrao)}">
            <span class="campo-dica">Todo mundo criado nesta importação começa com esta senha e pode trocar depois.</span>
          </label>
        </div>
      </div>

      <div class="cartao">
        <div class="cartao-topo"><h2 class="cartao-titulo">Qual tarefa</h2></div>
        ${crusTarefas.length ? `
          <p class="apagado" style="margin-bottom:14px">
            Cada nome da planilha aponta para uma tarefa cadastrada — é dela que sai o valor da hora.
          </p>
          ${crusTarefas.map((cru) => `
            <div class="mapa-coluna">
              <div class="mapa-coluna-nome">${esc(cru)}</div>
              <select class="entrada" data-tarefa="${esc(cru)}" style="min-height:44px;padding:8px 12px">
                ${ativas.map((t) => `<option value="${esc(t.id)}" ${vinculoTarefas[cru] === t.id ? 'selected' : ''}>${esc(t.name)} — ${esc(money(t.hourly_rate))}/h</option>`).join('')}
              </select>
            </div>`).join('')}
        ` : `
          <p class="apagado" style="margin-bottom:14px">
            A planilha não tem coluna de tarefa. Todos os turnos importados vão entrar nesta:
          </p>
          <select class="entrada" id="tarefa-padrao">
            ${ativas.map((t) => `<option value="${esc(t.id)}" ${tarefaPadrao === t.id ? 'selected' : ''}>${esc(t.name)} — ${esc(money(t.hourly_rate))}/h</option>`).join('')}
          </select>
        `}
      </div>

      <div class="linha-botoes" style="margin-top:18px">
        <button class="btn btn-medio btn-fantasma" data-volta>Voltar</button>
        <button class="btn btn-primario btn-medio" data-segue>Conferir antes de importar</button>
      </div>`;

    $$('[data-pessoa]', caixa).forEach((s) => s.addEventListener('change', () => {
      vinculoPessoas[s.dataset.pessoa] = s.value;
      const temNovo = Object.values(vinculoPessoas).includes('__novo__');
      $('#bloco-senha', caixa).hidden = !temNovo;
    }));
    $$('[data-tarefa]', caixa).forEach((s) => s.addEventListener('change', () => {
      vinculoTarefas[s.dataset.tarefa] = s.value;
    }));
    $('#tarefa-padrao', caixa)?.addEventListener('change', (ev) => { tarefaPadrao = ev.target.value; });
    $('#senha-nova', caixa)?.addEventListener('input', (ev) => { senhaPadrao = ev.target.value; });

    $('[data-volta]', caixa).addEventListener('click', () => { passo = 2; desenha(); });
    $('[data-segue]', caixa).addEventListener('click', () => { passo = 4; desenha(); });
  }

  /* ---------- interpretação de uma linha ---------- */

  function interpreta(linha) {
    const pega = (campo) => (mapa[campo] >= 0 ? linha[mapa[campo]] : null);

    const nomeCru = String(pega('pessoa') ?? '').trim();
    if (!nomeCru) return { erro: 'sem o nome da pessoa' };
    const destino = vinculoPessoas[nomeCru];
    if (destino === '') return { pulada: true };

    const data = leData(pega('data'));
    if (!data) return { erro: `não entendi a data "${String(pega('data') ?? '').slice(0, 18)}"` };

    let inicio, fim;
    const hEnt = leHora(pega('entrada'));
    const hSai = leHora(pega('saida'));

    if (hEnt) {
      inicio = juntaDataHora(data, hEnt);
      if (hSai) {
        fim = juntaDataHora(data, hSai);
        // saiu depois da meia-noite: o turno atravessa o dia
        if (fim <= inicio) fim = new Date(fim.getTime() + 86400000);
      } else if (mapa.horas >= 0) {
        const h = leNumero(pega('horas'));
        if (h) fim = new Date(inicio.getTime() + h * 3600000);
      }
    } else {
      const h = leNumero(pega('horas'));
      if (!h) return { erro: 'sem hora de entrada e sem total de horas' };
      inicio = juntaDataHora(data, { h: 8, m: 0 });
      fim = new Date(inicio.getTime() + h * 3600000);
    }

    if (fim && fim < inicio) return { erro: 'a saída ficou antes da entrada' };

    const tarefaCru = mapa.tarefa >= 0 ? String(pega('tarefa') ?? '').trim() : '';
    const tarefaId = (tarefaCru && vinculoTarefas[tarefaCru]) || tarefaPadrao;
    const tarefa = tarefas.find((t) => t.id === tarefaId);
    if (!tarefa) return { erro: 'sem tarefa definida' };

    return { nomeCru, destino, inicio, fim, tarefa };
  }

  /* ---------- passo 4: conferir e importar ---------- */

  function passoConferir(caixa) {
    const lidas = dados.map(interpreta);
    const boas = lidas.filter((l) => !l.erro && !l.pulada);
    const ruins = lidas.filter((l) => l.erro);
    const puladas = lidas.filter((l) => l.pulada).length;
    const criar = [...new Set(boas.filter((l) => l.destino === '__novo__').map((l) => l.nomeCru))];

    const totalHoras = boas.reduce((s, l) => s + (l.fim ? (l.fim - l.inicio) / 3600000 : 0), 0);
    const totalValor = boas.reduce((s, l) => s + (l.fim ? ((l.fim - l.inicio) / 3600000) * (+l.tarefa.hourly_rate || 0) : 0), 0);
    const emAberto = boas.filter((l) => !l.fim).length;

    caixa.innerHTML = `
      <div class="cartao">
        <div class="cartao-topo"><h2 class="cartao-titulo">Conferindo</h2></div>
        <div class="grade-metricas">
          <div class="metrica"><div class="metrica-rotulo">Turnos a importar</div>
            <div class="metrica-valor" style="color:var(--salvia-alt)">${boas.length}</div></div>
          <div class="metrica"><div class="metrica-rotulo">Horas somadas</div>
            <div class="metrica-valor">${esc(horas(totalHoras))}</div></div>
          <div class="metrica"><div class="metrica-rotulo">Valor somado</div>
            <div class="metrica-valor">${esc(money(totalValor))}</div></div>
          <div class="metrica"><div class="metrica-rotulo">Linhas com problema</div>
            <div class="metrica-valor" style="${ruins.length ? 'color:var(--alerta)' : ''}">${ruins.length}</div></div>
        </div>

        ${criar.length ? `
          <div class="recado" style="margin-top:16px">
            <span class="recado-emoji">👤</span>
            <span>Vou criar acesso para: <strong>${esc(criar.join(', '))}</strong>,
                  todos com a senha <strong>${esc(senhaPadrao)}</strong>.</span>
          </div>` : ''}
        ${emAberto ? `
          <div class="recado" style="margin-top:12px">
            <span class="recado-emoji">⏳</span>
            <span>${esc(plural(emAberto, 'turno vai entrar sem hora de saída', 'turnos vão entrar sem hora de saída'))}
                  — dá para fechar depois, na aba Turnos.</span>
          </div>` : ''}
        ${puladas ? `<p class="apagado" style="margin-top:12px">${esc(plural(puladas, 'linha pulada', 'linhas puladas'))} por escolha sua.</p>` : ''}
      </div>

      ${ruins.length ? `
        <div class="cartao">
          <div class="cartao-topo"><h2 class="cartao-titulo">O que eu não consegui ler</h2></div>
          <p class="apagado" style="margin-bottom:12px">
            Estas linhas ficam de fora. O resto entra normalmente.
          </p>
          <div class="tabela-caixa">
            <table><thead><tr><th>Linha</th><th>Motivo</th></tr></thead>
              <tbody>${ruins.slice(0, 12).map((l) => {
                const i = lidas.indexOf(l) + 2;
                return `<tr><td class="num">${i}</td><td>${esc(l.erro)}</td></tr>`;
              }).join('')}</tbody></table>
          </div>
          ${ruins.length > 12 ? `<p class="apagado" style="margin-top:10px">…e mais ${ruins.length - 12}.</p>` : ''}
        </div>` : ''}

      ${boas.length ? `
        <div class="cartao">
          <div class="cartao-topo"><h2 class="cartao-titulo">Prévia</h2>
            <span class="apagado" style="font-size:13px">primeiros 8 turnos</span></div>
          <div class="tabela-caixa">
            <table>
              <thead><tr><th>Pessoa</th><th>Data</th><th>Entrada</th><th>Saída</th><th>Tarefa</th><th class="n">Horas</th><th class="n">Valor</th></tr></thead>
              <tbody>${boas.slice(0, 8).map((l) => {
                const h = l.fim ? (l.fim - l.inicio) / 3600000 : 0;
                return `<tr>
                  <td>${esc(l.nomeCru)}</td>
                  <td>${esc(dataBR(l.inicio))}</td>
                  <td>${esc(hora(l.inicio))}</td>
                  <td>${l.fim ? esc(hora(l.fim)) : '—'}</td>
                  <td>${esc(l.tarefa.name)}</td>
                  <td class="n">${esc(h ? num(h, 2) : '—')}</td>
                  <td class="n">${esc(money(h * (+l.tarefa.hourly_rate || 0)))}</td>
                </tr>`;
              }).join('')}</tbody>
            </table>
          </div>
        </div>` : vazio({ emoji: '🤔', titulo: 'Nenhuma linha aproveitável',
                          texto: 'Volte e confira o mapeamento das colunas.' })}

      <div id="barra-progresso"></div>

      <div class="linha-botoes" style="margin-top:18px">
        <button class="btn btn-medio btn-fantasma" data-volta>Voltar</button>
        <button class="btn btn-primario btn-medio" data-importa ${boas.length ? '' : 'disabled'}>
          Importar ${boas.length ? esc(plural(boas.length, 'turno', 'turnos')) : ''}
        </button>
      </div>`;

    $('[data-volta]', caixa).addEventListener('click', () => { passo = 3; desenha(); });
    $('[data-importa]', caixa).addEventListener('click', (ev) => importa(boas, criar, caixa, ev.currentTarget));
  }

  /* ---------- gravação ---------- */

  async function importa(boas, criar, caixa, botao) {
    const certeza = await confirma({
      titulo: `Importar ${plural(boas.length, 'turno', 'turnos')}?`,
      texto: 'Eles entram no histórico como “importado”. Se der errado, dá para apagar um a um na aba Turnos.',
      ok: 'Importar agora',
    });
    if (!certeza) return;

    const progresso = $('#barra-progresso', caixa);
    const marca = (feitos) => {
      progresso.innerHTML = `
        <div class="cartao" style="margin-top:16px">
          <p class="rotulo" style="margin-bottom:8px">Importando…</p>
          <div style="height:10px;border-radius:6px;background:rgba(255,255,255,.06);overflow:hidden">
            <div style="height:100%;width:${(feitos / boas.length) * 100}%;background:var(--salvia);transition:width .2s"></div>
          </div>
          <p class="apagado" style="margin-top:8px">${feitos} de ${boas.length}</p>
        </div>`;
    };

    botao.disabled = true;
    marca(0);

    try {
      // 1. cria quem falta
      const novosIds = {};
      for (const nomeCru of criar) {
        const base = chave(nomeCru).replace(/[^a-z0-9]+/g, '.').replace(/^\.|\.$/g, '').slice(0, 30) || 'pessoa';
        let user = base, n = 1;
        // eslint-disable-next-line no-await-in-loop
        while (pessoas.some((p) => p.username === user)) { user = `${base}${++n}`; }
        // eslint-disable-next-line no-await-in-loop
        const p = await store.criaPessoa({
          username: user, full_name: nomeCru, password: senhaPadrao || '1234', role: 'employee',
        });
        pessoas.push(p);
        novosIds[nomeCru] = p.id;
      }

      // 2. libera para cada pessoa nova as tarefas que ela usa na planilha
      for (const [nomeCru, id] of Object.entries(novosIds)) {
        const ids = [...new Set(boas.filter((l) => l.nomeCru === nomeCru).map((l) => l.tarefa.id))];
        if (ids.length) await store.defineAtribuicoes(id, ids);
      }

      // 3. grava os turnos
      let feitos = 0, falhas = 0;
      for (const l of boas) {
        const userId = l.destino === '__novo__' ? novosIds[l.nomeCru] : l.destino;
        try {
          // eslint-disable-next-line no-await-in-loop
          await store.gravaTurnoManual({
            user_id: userId,
            started_at: l.inicio,
            ended_at: l.fim || null,
            source: 'import',
            note: `importado de ${nomeArquivo}`,
            trechos: [{
              task_id: l.tarefa.id, task_name: l.tarefa.name,
              hourly_rate: l.tarefa.hourly_rate,
              started_at: l.inicio, ended_at: l.fim || null,
            }],
          });
        } catch { falhas++; }
        marca(++feitos);
      }

      progresso.innerHTML = `
        <div class="recado bom" style="margin-top:16px">
          <span class="recado-emoji">🎉</span>
          <span><strong>${esc(plural(feitos - falhas, 'turno importado', 'turnos importados'))}.</strong>
            ${falhas ? ` ${esc(plural(falhas, 'linha falhou', 'linhas falharam'))} — provavelmente turno repetido ou sobreposto.` : ''}
            Confira na aba Turnos.</span>
        </div>`;
      torrada(`${plural(feitos - falhas, 'turno importado', 'turnos importados')}.`, 'bom', 6);
      await aoTerminar();
    } catch (e) {
      progresso.innerHTML = `
        <div class="recado ruim" style="margin-top:16px">
          <span class="recado-emoji">⚠️</span>
          <span><strong>A importação parou.</strong><br>${esc(e.message)}</span>
        </div>`;
      botao.disabled = false;
    }
  }

  desenha();
}
