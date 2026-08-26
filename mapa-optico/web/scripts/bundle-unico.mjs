/**
 * Empacota o dashboard inteiro num unico arquivo .html.
 *
 * POR QUE ISSO EXISTE: o app normal precisa de um servidor (os assets e os
 * dados vem por fetch). Um arquivo so abre com dois cliques, roda offline e
 * cabe num anexo de e-mail — que e como ele chega em quem vai decidir a cidade
 * sem ter servidor nenhum. Tambem e o formato aceito por hospedagens que
 * servem uma pagina e nada mais.
 *
 *   node scripts/bundle-unico.mjs [saida.html] [--fragmento]
 *
 * --fragmento emite so o conteudo interno (sem doctype/html/head/body), que e
 * o que hospedagens que injetam o proprio esqueleto esperam receber.
 *
 * Pre-requisito: `vite build` ja rodou e dist/ existe.
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(raiz, "dist");
const dados = join(raiz, "public", "data");

const args = process.argv.slice(2);
const fragmento = args.includes("--fragmento");
const saida = resolve(args.find((a) => !a.startsWith("--")) ?? join(dist, "mapa-optico.html"));

if (!existsSync(join(dist, "index.html"))) {
  console.error("dist/index.html não existe. Rode `npm run build` antes.");
  process.exit(1);
}

/** Dentro de <script>, a sequência `</script` fecha a tag mesmo em string. */
const escapar = (texto) => texto.replace(/<\/script/gi, "<\\/script");

// --------------------------------------------------------------- os dados
const malhas = {};
for (const arquivo of readdirSync(dados)) {
  const m = /^malha-([A-Z]{2})\.geojson$/.exec(arquivo);
  if (m) malhas[m[1]] = JSON.parse(readFileSync(join(dados, arquivo), "utf8"));
}
const snapshot = JSON.parse(readFileSync(join(dados, "snapshot.json"), "utf8"));
const embutido =
  `<script>window.__MAPA_OPTICO__=${escapar(JSON.stringify({ snapshot, malhas }))}</script>`;

// ------------------------------------------------------------- os assets
let html = readFileSync(join(dist, "index.html"), "utf8");

// Cada <script src> e <link stylesheet> vira o próprio conteúdo. A ordem dos
// módulos importa (o entry importa os chunks), então preservamos a posição.
html = html.replace(
  /<script[^>]*\ssrc="([^"]+)"[^>]*><\/script>/g,
  (_m, src) => `<script type="module">${escapar(ler(src))}</script>`,
);
html = html.replace(
  /<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"[^>]*>/g,
  (_m, href) => `<style>${ler(href)}</style>`,
);
// modulepreload aponta para arquivo que já foi inlinado: vira ruído e 404.
html = html.replace(/<link[^>]*rel="modulepreload"[^>]*>/g, "");

function ler(url) {
  const caminho = join(dist, url.replace(/^https?:\/\/[^/]+/, "").replace(/^.*\/assets\//, "assets/"));
  return readFileSync(caminho, "utf8");
}

// Os dados entram antes de qualquer módulo: o app lê window.__MAPA_OPTICO__ na
// carga, então precisa já estar lá.
html = html.replace("</head>", `${embutido}</head>`);

if (fragmento) {
  const cabeca = /<head[^>]*>([\s\S]*?)<\/head>/i.exec(html)?.[1] ?? "";
  const corpo = /<body[^>]*>([\s\S]*?)<\/body>/i.exec(html)?.[1] ?? "";
  // O esqueleto vem de fora; charset e viewport também. Sobra o que é nosso.
  html = `${cabeca.replace(/<meta[^>]*charset[^>]*>/gi, "").trim()}\n${corpo.trim()}`;
}

mkdirSync(dirname(saida), { recursive: true });
writeFileSync(saida, html);
const mb = (Buffer.byteLength(html) / 1024 / 1024).toFixed(2);
console.log(`${saida} — ${mb} MB · ${snapshot.municipios.length} municípios · malhas: ${Object.keys(malhas).join(", ") || "nenhuma"}`);
