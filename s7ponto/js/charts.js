/* ==========================================================================
   S7 PONTO — gráficos em SVG puro, sem biblioteca.
   Paleta categórica de ordem fixa (nunca ciclada), validada para daltonismo
   sobre a superfície #1c1e18. Uma série = sem legenda, o título já diz o quê.
   ========================================================================== */
import { esc, horas, horasCurto, money, num, letraDia, nomeDia, dataCurta, diaChave } from './util.js';

/** Ordem fixa das séries. Passou nos seis testes sobre o fundo musgo. */
export const PALETA = ['#d95926', '#199e70', '#3987e5', '#c98500',
                       '#d55181', '#7d9c2f', '#9085e9', '#e66767'];
export const corDaSerie = (i) => PALETA[i] ?? '#8b8878';   // 9ª em diante: "Outras"

function cssVar(nome, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
  return v || fallback;
}
const tinta  = () => cssVar('--tinta', '#F7F4EC');
const borda  = () => cssVar('--borda-forte', '#363a2d');

/* ---------- ajudinhas ---------------------------------------------------- */

/** Topo do eixo arredondado pra um número que dá gosto de ler. */
function tetoBonito(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

/** Barra com só o topo arredondado, ancorada na linha de base. */
function barraTopoRedondo(x, y, w, h, r = 4) {
  const rr = Math.max(0, Math.min(r, w / 2, h));
  if (h <= 0.4) return '';
  return `M${x},${y + h}L${x},${y + rr}Q${x},${y} ${x + rr},${y}`
       + `L${x + w - rr},${y}Q${x + w},${y} ${x + w},${y + rr}L${x + w},${y + h}Z`;
}

/** Camada de dica que segue o mouse/dedo dentro do container. */
function ligaDica(caixa, svgEl, achaAlvo, montaHtml) {
  const dica = document.createElement('div');
  dica.className = 'dica';
  caixa.appendChild(dica);

  let ativo = null;
  const mostra = (ev) => {
    const r = svgEl.getBoundingClientRect();
    const px = (ev.touches?.[0]?.clientX ?? ev.clientX) - r.left;
    const alvo = achaAlvo(px / r.width);
    if (!alvo) return esconde();
    if (ativo !== alvo.chave) {
      ativo = alvo.chave;
      dica.innerHTML = montaHtml(alvo.dado);
    }
    const cr = caixa.getBoundingClientRect();
    const x = Math.max(58, Math.min(cr.width - 58, alvo.centro * r.width + (r.left - cr.left)));
    dica.style.left = `${x}px`;
    dica.style.top = `${Math.max(30, (ev.touches?.[0]?.clientY ?? ev.clientY) - cr.top - 4)}px`;
    dica.classList.add('on');
    svgEl.querySelectorAll('.barra').forEach((b) => b.classList.toggle('ativa', b.dataset.k === String(alvo.chave)));
  };
  const esconde = () => {
    ativo = null;
    dica.classList.remove('on');
    svgEl.querySelectorAll('.barra.ativa').forEach((b) => b.classList.remove('ativa'));
  };

  svgEl.addEventListener('mousemove', mostra);
  svgEl.addEventListener('mouseleave', esconde);
  svgEl.addEventListener('touchstart', mostra, { passive: true });
  svgEl.addEventListener('touchmove', mostra, { passive: true });
  svgEl.addEventListener('touchend', esconde);
}

/* ==========================================================================
   1. Horas por dia do mês — uma série, barras verticais.
   dados: [{ data: Date, horas: Number, valor: Number }]
   ========================================================================== */

export function graficoDias(caixa, dados, { cor = PALETA[0] } = {}) {
  caixa.innerHTML = '';
  if (!dados.length) { caixa.innerHTML = '<p class="apagado centro" style="padding:26px 0">Sem dias registrados.</p>'; return; }

  const L = 30, R = 6, T = 12, B = 24, A = 168;
  const larguraBarra = 13, vao = 4;
  const W = L + R + dados.length * larguraBarra + (dados.length - 1) * vao;
  const alturaPlot = A - T - B;
  const teto = tetoBonito(Math.max(...dados.map((d) => d.horas), 1));
  const y = (v) => T + alturaPlot - (v / teto) * alturaPlot;

  const hoje = diaChave(new Date());
  const grades = [0, teto / 2, teto];

  const partes = [];
  partes.push(`<svg viewBox="0 0 ${W} ${A}" role="img" aria-label="Horas trabalhadas por dia">`);
  grades.forEach((g) => {
    partes.push(`<line class="${g === 0 ? 'grade-base' : 'grade-linha'}" x1="${L}" x2="${W - R}" y1="${y(g)}" y2="${y(g)}"/>`);
    partes.push(`<text class="eixo-texto" x="${L - 6}" y="${y(g) + 3.5}" text-anchor="end">${g === 0 ? '0' : `${num(g, g % 1 ? 1 : 0)}h`}</text>`);
  });
  dados.forEach((d, i) => {
    const x = L + i * (larguraBarra + vao);
    const h = Math.max(d.horas > 0 ? 2 : 0, alturaPlot - (y(d.horas) - T));
    const ehHoje = diaChave(d.data) === hoje;
    if (d.horas > 0) {
      partes.push(`<path class="barra" data-k="${i}" d="${barraTopoRedondo(x, y(d.horas), larguraBarra, h)}" fill="${cor}"${ehHoje ? ` stroke="${tinta()}" stroke-width="1.2"` : ''}/>`);
    } else {
      partes.push(`<rect class="barra" data-k="${i}" x="${x}" y="${y(0) - 2}" width="${larguraBarra}" height="2" rx="1" fill="${borda()}"/>`);
    }
    // rótulo do eixo: dia 1, múltiplos de 5 e o último — sem poluir
    const dia = d.data.getDate();
    if (dia === 1 || dia % 5 === 0 || i === dados.length - 1) {
      partes.push(`<text class="eixo-texto" x="${x + larguraBarra / 2}" y="${A - 8}" text-anchor="middle">${dia}</text>`);
    }
  });
  partes.push('</svg>');

  const rolagem = document.createElement('div');
  rolagem.className = 'grafico-rolagem';
  rolagem.innerHTML = partes.join('');
  caixa.appendChild(rolagem);

  const svgEl = rolagem.querySelector('svg');
  ligaDica(caixa, svgEl,
    (frac) => {
      const i = Math.round((frac * W - L - larguraBarra / 2) / (larguraBarra + vao));
      if (i < 0 || i >= dados.length) return null;
      return { chave: i, dado: dados[i], centro: (L + i * (larguraBarra + vao) + larguraBarra / 2) / W };
    },
    (d) => `<div class="dica-titulo">${esc(nomeDia(d.data).slice(0, 3))}, ${esc(dataCurta(d.data))}</div>`
      + `<div class="dica-linha"><span class="dica-ponto" style="background:${cor}"></span>${esc(d.horas ? horas(d.horas) : 'não trabalhou')}</div>`
      + (d.valor ? `<div class="dica-linha" style="color:var(--tinta-3)">${esc(money(d.valor))}</div>` : ''));
}

/* ==========================================================================
   2. Ganhos por mês — uma série, últimos N meses.
   dados: [{ rotulo, valor, horas, atual:Boolean }]
   ========================================================================== */

export function graficoMeses(caixa, dados, { cor = PALETA[0] } = {}) {
  caixa.innerHTML = '';
  if (!dados.length) return;

  const L = 6, R = 6, T = 26, B = 24, A = 156;
  const W = 320;
  const alturaPlot = A - T - B;
  const teto = tetoBonito(Math.max(...dados.map((d) => d.valor), 1));
  const larguraBarra = (W - L - R) / dados.length;
  const w = Math.min(38, larguraBarra - 10);
  const y = (v) => T + alturaPlot - (v / teto) * alturaPlot;

  const partes = [`<svg viewBox="0 0 ${W} ${A}" preserveAspectRatio="none" role="img" aria-label="Ganhos por mês">`];
  partes.push(`<line class="grade-base" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}"/>`);
  dados.forEach((d, i) => {
    const cx = L + larguraBarra * (i + 0.5);
    const x = cx - w / 2;
    const h = Math.max(d.valor > 0 ? 2 : 0, alturaPlot - (y(d.valor) - T));
    const opac = d.atual ? 1 : 0.62;
    partes.push(`<path class="barra" data-k="${i}" d="${barraTopoRedondo(x, y(d.valor), w, h)}" fill="${cor}" opacity="${opac}"/>`);
    if (d.atual && d.valor > 0) {
      // rótulo direto só no mês em foco — nunca um número em cada barra
      partes.push(`<text class="eixo-texto" x="${cx}" y="${y(d.valor) - 8}" text-anchor="middle" style="fill:var(--tinta);font-size:11px;font-weight:600">${esc(num(d.valor, 0))}</text>`);
    }
    partes.push(`<text class="eixo-texto" x="${cx}" y="${A - 8}" text-anchor="middle"${d.atual ? ' style="fill:#F2EFE8"' : ''}>${esc(d.rotulo)}</text>`);
  });
  partes.push('</svg>');
  caixa.innerHTML = partes.join('');

  const svgEl = caixa.querySelector('svg');
  ligaDica(caixa, svgEl,
    (frac) => {
      const i = Math.floor((frac * W - L) / larguraBarra);
      if (i < 0 || i >= dados.length) return null;
      return { chave: i, dado: dados[i], centro: (L + larguraBarra * (i + 0.5)) / W };
    },
    (d) => `<div class="dica-titulo">${esc(d.rotuloLongo || d.rotulo)}</div>`
      + `<div class="dica-linha"><span class="dica-ponto" style="background:${cor}"></span>${esc(money(d.valor))}</div>`
      + `<div class="dica-linha" style="color:var(--tinta-3)">${esc(horas(d.horas))}</div>`);
}

/* ==========================================================================
   3. Quebra por tarefa — barra empilhada + legenda com rótulo direto.
   dados: [{ nome, horas, valor, cor }]
   ========================================================================== */

export function graficoTarefas(caixa, dados) {
  caixa.innerHTML = '';
  const total = dados.reduce((s, d) => s + d.horas, 0);
  if (!total) { caixa.innerHTML = '<p class="apagado centro" style="padding:26px 0">Nenhuma tarefa registrada ainda.</p>'; return; }

  const W = 320, A = 26, vao = 2;   // 2px de respiro entre fatias
  let x = 0;
  const fatias = dados.map((d, i) => {
    const w = Math.max(3, (d.horas / total) * (W - vao * (dados.length - 1)));
    const seg = { ...d, x, w, i };
    x += w + vao;
    return seg;
  });

  caixa.innerHTML = `
    <svg viewBox="0 0 ${W} ${A}" preserveAspectRatio="none" role="img"
         aria-label="Divisão das horas por tarefa" style="height:26px">
      ${fatias.map((f) => `<rect class="barra" data-k="${f.i}" x="${f.x}" y="0" width="${f.w}" height="${A}" rx="4" fill="${f.cor}"/>`).join('')}
    </svg>
    <div class="legenda">
      ${dados.map((d) => `
        <span class="legenda-item">
          <span class="legenda-cor" style="background:${d.cor}"></span>
          <strong style="font-weight:600;color:var(--tinta)">${esc(d.nome)}</strong>
          <span class="num">${esc(horas(d.horas))}</span>
          <span class="apagado num">${esc(money(d.valor))}</span>
        </span>`).join('')}
    </div>`;

  const svgEl = caixa.querySelector('svg');
  ligaDica(caixa, svgEl,
    (frac) => {
      const px = frac * W;
      const f = fatias.find((s) => px >= s.x && px <= s.x + s.w) || null;
      return f && { chave: f.i, dado: f, centro: (f.x + f.w / 2) / W };
    },
    (d) => `<div class="dica-titulo">${esc(d.nome)}</div>`
      + `<div class="dica-linha"><span class="dica-ponto" style="background:${d.cor}"></span>${esc(horas(d.horas))} · ${esc(Math.round((d.horas / total) * 100))}%</div>`
      + `<div class="dica-linha" style="color:var(--tinta-3)">${esc(money(d.valor))}</div>`);
}

/* ==========================================================================
   4. Tiras da semana — HTML puro, cada dia com letra e número por baixo.
   dias: [{ data, horas }]
   ========================================================================== */

export function tirasDaSemana(caixa, dias, { cor = PALETA[0] } = {}) {
  const maxH = Math.max(...dias.map((d) => d.horas), 1);
  const hoje = diaChave(new Date());
  caixa.innerHTML = `
    <div class="semana">
      ${dias.map((d) => {
        const alt = d.horas > 0 ? Math.max(6, (d.horas / maxH) * 100) : 3;
        const ehHoje = diaChave(d.data) === hoje;
        return `
          <div class="semana-dia ${ehHoje ? 'hoje' : ''}">
            <div class="semana-barra-caixa" title="${esc(dataCurta(d.data))} — ${esc(horas(d.horas))}">
              <div class="semana-barra ${d.horas ? '' : 'zero'}"
                   style="height:${alt}%${d.horas ? `;background:${cor}` : ''}"></div>
            </div>
            <div class="semana-letra">${esc(letraDia(d.data))}</div>
            <div class="semana-valor">${d.horas ? esc(horasCurto(d.horas)) : '–'}</div>
          </div>`;
      }).join('')}
    </div>`;
}

/* ==========================================================================
   5. Trilha do turno em andamento — os trechos por tarefa, em proporção.
   ========================================================================== */

export function trilhaDoTurno(caixa, trechos, agora = new Date()) {
  const total = trechos.reduce((s, t) =>
    s + (new Date(t.ended_at || agora) - new Date(t.started_at)), 0) || 1;
  caixa.innerHTML = `<div class="trilha">${trechos.map((t) => {
    const dur = new Date(t.ended_at || agora) - new Date(t.started_at);
    return `<div class="trilha-parte" style="flex:${Math.max(dur / total, 0.02)};background:${t.cor}"
                 title="${esc(t.task_name)}"></div>`;
  }).join('')}</div>`;
}

/* ==========================================================================
   6. Pizza / donut — distribuição (horas ou valor).
   dados: [{ nome, valor, cor }]
   formato: 'horas' | 'money'
   ========================================================================== */

function polar(cx, cy, r, a) {
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}

function fatiaDonut(cx, cy, rOut, rIn, a0, a1) {
  const large = a1 - a0 > Math.PI ? 1 : 0;
  const [x0, y0] = polar(cx, cy, rOut, a0);
  const [x1, y1] = polar(cx, cy, rOut, a1);
  const [x2, y2] = polar(cx, cy, rIn, a1);
  const [x3, y3] = polar(cx, cy, rIn, a0);
  return `M${x0} ${y0} A${rOut} ${rOut} 0 ${large} 1 ${x1} ${y1} L${x2} ${y2} A${rIn} ${rIn} 0 ${large} 0 ${x3} ${y3} Z`;
}

export function graficoPizza(caixa, dados, { formato = 'money', rotuloCentro = '' } = {}) {
  caixa.innerHTML = '';
  const limpos = (dados || []).filter((d) => (d.valor || 0) > 0.0001);
  const total = limpos.reduce((s, d) => s + d.valor, 0);
  if (!total) {
    caixa.innerHTML = '<p class="apagado centro" style="padding:22px 0">Ainda sem dados para o gráfico.</p>';
    return;
  }

  const W = 220, H = 220, cx = 110, cy = 110, rOut = 96, rIn = 58;
  const fmt = formato === 'horas' ? horas : money;
  let ang = -Math.PI / 2;
  const fatias = limpos.map((d, i) => {
    const fat = (d.valor / total) * Math.PI * 2;
    const a0 = ang;
    const a1 = ang + fat;
    ang = a1;
    return { ...d, i, a0, a1, pct: (d.valor / total) * 100 };
  });

  const anelCompleto = fatias.length === 1;
  const svgFatias = anelCompleto
    ? `<circle cx="${cx}" cy="${cy}" r="${(rOut + rIn) / 2}" fill="none"
         stroke="${fatias[0].cor}" stroke-width="${rOut - rIn}" class="barra" data-k="0"/>`
    : fatias.map((f) =>
        `<path class="barra pizza-fatia" data-k="${f.i}" fill="${f.cor}" d="${fatiaDonut(cx, cy, rOut, rIn, f.a0, f.a1)}"/>`).join('');

  caixa.innerHTML = `
    <div class="pizza-wrap">
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Distribuição em pizza" class="pizza-svg">
        ${svgFatias}
        <text x="${cx}" y="${cy - 6}" text-anchor="middle" class="pizza-centro-valor">${esc(fmt(total))}</text>
        <text x="${cx}" y="${cy + 14}" text-anchor="middle" class="pizza-centro-rotulo">${esc(rotuloCentro)}</text>
      </svg>
      <div class="legenda pizza-legenda">
        ${fatias.map((d) => `
          <span class="legenda-item">
            <span class="legenda-cor" style="background:${d.cor}"></span>
            <strong style="font-weight:600;color:var(--tinta)">${esc(d.nome)}</strong>
            <span class="num">${esc(fmt(d.valor))}</span>
            <span class="apagado num">${esc(num(d.pct, 0))}%</span>
          </span>`).join('')}
      </div>
    </div>`;

  const svgEl = caixa.querySelector('svg');
  const dica = document.createElement('div');
  dica.className = 'dica';
  caixa.appendChild(dica);
  const mostraFatia = (f, ev) => {
    if (!f) return;
    dica.innerHTML = `<div class="dica-titulo">${esc(f.nome)}</div>`
      + `<div class="dica-linha"><span class="dica-ponto" style="background:${f.cor}"></span>${esc(fmt(f.valor))} · ${esc(num(f.pct, 0))}%</div>`;
    const cr = caixa.getBoundingClientRect();
    dica.style.left = `${Math.max(70, Math.min(cr.width - 70, ev.clientX - cr.left))}px`;
    dica.style.top = `${Math.max(28, ev.clientY - cr.top - 4)}px`;
    dica.classList.add('on');
    svgEl.querySelectorAll('.barra').forEach((b) => b.classList.toggle('ativa', b.dataset.k === String(f.i)));
  };
  svgEl.querySelectorAll('.barra').forEach((el) => {
    const f = fatias[+el.dataset.k];
    el.addEventListener('mousemove', (ev) => mostraFatia(f, ev));
    el.addEventListener('mouseleave', () => {
      dica.classList.remove('on');
      svgEl.querySelectorAll('.barra.ativa').forEach((b) => b.classList.remove('ativa'));
    });
  });
}

/* ==========================================================================
   7. Tabela alternativa — todo gráfico tem como ser lido em números.
   ========================================================================== */

export function tabelaDeApoio(linhas, cabecalho) {
  return `
    <details class="bloco" style="margin-top:14px">
      <summary style="cursor:pointer;color:var(--tinta-3);font-size:13px;padding:6px 0">Ver os números em tabela</summary>
      <div class="tabela-caixa" style="margin-top:10px">
        <table>
          <thead><tr>${cabecalho.map((c, i) => `<th${i ? ' class="n"' : ''}>${esc(c)}</th>`).join('')}</tr></thead>
          <tbody>${linhas.map((l) => `<tr>${l.map((c, i) => `<td${i ? ' class="n"' : ''}>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody>
        </table>
      </div>
    </details>`;
}
