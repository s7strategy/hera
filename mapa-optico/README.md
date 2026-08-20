# Mapa Óptico

Ranking de municípios brasileiros por atratividade para eventos itinerantes de saúde ocular.

A pergunta que o sistema responde: **em que cidade o próximo evento tem mais chance de encher e
converter?** A receita vem da venda de óculos, não da consulta — então o driver do modelo não é
"não ter oftalmologista", é o **custo de acesso a uma receita**: quanto o morador precisa se
deslocar e esperar. Uma cidade com oftalmologista e fila de 8 meses no SUS pode valer tanto quanto
uma sem nenhum.

```
mapa-optico/
├── pipeline/          # Python: ingestão, score, exportação (uv)
│   ├── src/mapa_optico/
│   │   ├── ingest/    # um módulo por fonte: ibge, cnes, places, osrm, mirrors
│   │   ├── transform/ # normalização de código IBGE, deduplicação de profissionais
│   │   ├── score/     # o modelo
│   │   └── load/      # CSV/XLSX, snapshot do dashboard, Supabase
│   ├── config/
│   │   ├── weights.yaml   # pesos do score — editável, nada hardcoded
│   │   └── fontes.yaml    # ids externos (tabelas SIDRA, CBO) que precisam ser conferidos
│   └── tests/
├── web/               # React + Vite + TypeScript + MapLibre
├── supabase/migrations/
└── README.md
```

---

## Começando do zero

### 1. Pipeline

```bash
cd pipeline
uv venv && uv pip install -e ".[dev]"      # ou: poetry install
cp .env.example .env                       # preencher as chaves que você tiver
```

Confira o que está de pé antes de qualquer coisa:

```bash
uv run mapa-optico checar-fontes
```

### 2. Fase 0 — provar que dá para ler o CNES

Esse é o maior risco técnico do projeto e por isso é o primeiro passo:

```bash
uv pip install -e ".[cnes]"        # traz o pysus, que descompacta o .DBC
uv run mapa-optico fase0 --uf SC
```

Critério de saída: a tabela impressa mostra municípios de SC com contagem de oftalmologistas, e
**Florianópolis e Joinville batem com a realidade** (dezenas, não 2 e não 500).

Se o `pysus` falhar, o comando cai sozinho para o CSV manual: baixe a extração de profissionais da
UF em <https://cnes.datasus.gov.br/pages/profissionais/extracao.jsp> (selecione a UF e **não**
selecione município), salve em `pipeline/data/manual/` e rode de novo. Se os dois caminhos
falharem, o comando **para e reporta** em vez de improvisar um terceiro — decisão explícita do
briefing.

### 3. Fase 1 — pipeline completo em SC

```bash
uv run mapa-optico ingest --uf SC --sem-places   # sem gastar com o Places
uv run mapa-optico ingest --uf SC                # com Places (estima o custo antes)
```

Saídas:

- `pipeline/out/ranking-v1.csv` e `.xlsx` — para uso comercial
- `pipeline/data/base-SC.json` — base intermediária (permite recalcular o score sem rede)
- `web/public/data/snapshot.json` + `malha-SC.geojson` — o que o dashboard lê

Mexeu nos pesos? Recalcule sem tocar a rede:

```bash
uv run mapa-optico score --uf SC
```

### 4. Banco (opcional)

O pipeline funciona inteiro sem Supabase — ele exporta arquivo. Com Supabase:

1. rode `supabase/migrations/0001_init.sql` no SQL Editor do projeto;
2. preencha `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` no `.env`;
3. `uv run mapa-optico carregar --uf SC`.

Toda escrita é `upsert` por chave natural: rodar duas vezes não duplica nada.

### 5. Dashboard

```bash
cd web
npm install
cp .env.example .env      # opcional: só para ler do Supabase em vez do snapshot
npm run dev
```

Sem `VITE_SUPABASE_*`, o dashboard lê `public/data/snapshot.json` — funciona offline, sem banco e
sem chave de nada.

---

## O modelo de score, em português claro

Cada município recebe uma nota de 0 a 100 por fator, e o score final é a média ponderada dessas
notas. Os pesos ficam em `pipeline/config/weights.yaml` — **nenhum número do modelo vive no
código**.

| Fator | Peso | Leitura |
|---|---|---|
| Distância ao polo | 30 | Quanto o morador precisa rodar para conseguir uma receita. Provavelmente o preditor mais forte. |
| Ausência de oftalmologista | 25 | Oferta local, ponderada por carga horária. Bônus fixo para quem não tem nenhum. |
| População 40+ | 20 | Mercado endereçável real: presbiopia começa aí. Não é a população total. |
| Concorrência de óticas | 15 | Óticas já instaladas disputando o mesmo comprador. |
| Renda | 10 | Faixa ótima, não "quanto mais melhor". |

Quatro decisões que valem explicação:

**Normalização por percentil, não min-max.** Um município a 900 km do polo destruiria uma escala
min-max inteira. O percentil é calculado dentro do universo já filtrado — "longe" em SC não é
"longe" no Amazonas.

**Renda é curva, não linha.** Renda baixa demais derruba o ticket médio; renda alta demais
significa que a pessoa vai comprar na ótica da cidade grande. Por isso a nota é 100 dentro da faixa
ótima (padrão: R$ 1.200–3.500) e cai proporcionalmente para fora dela.

**Dado ausente nunca vira zero.** Se falta o CNES de um município, o fator sai da conta e os pesos
dos fatores restantes são renormalizados — o município não é punido por um buraco na nossa coleta.
Em troca, a **confiança** cai, e a confiança aparece na tela ao lado do score. Municípios abaixo do
mínimo de confiança saem do ranking principal mas continuam visíveis, marcados com ⚠.

**O score é rastreável.** A coluna `componentes` (JSONB no banco) guarda, para cada fator, o valor
bruto, a nota normalizada, o peso efetivo e quantos pontos ele contribuiu. A soma das contribuições
é exatamente o score — é isso que a ficha do município mostra. Sem isso o modelo vira caixa preta,
e caixa preta não sustenta decisão comercial.

**Circuitos e canibalização.** Municípios vizinhos de score alto são agrupados em circuitos
sugeridos (DBSCAN sobre os centroides, eps ≈ 60 km) para diluir o deslocamento do médico. E dois
municípios do topo a menos de 30 km um do outro geram alerta: provavelmente compartilham público e
devem virar um circuito único, não dois eventos.

---

## As fontes, e o que dá errado em cada uma

| Fonte | O que traz | Armadilha tratada |
|---|---|---|
| **CNES** (DATASUS) | oftalmologistas por município | `.DBC` é DBF comprimido proprietário (usa `pysus`); código IBGE de 6 dígitos vs. 7; vínculos duplicados do mesmo médico; carga horária |
| **IBGE localidades** | código, nome, UF, micro e mesorregião | — |
| **IBGE SIDRA** | população total e 40+, renda | faixas etárias são somadas **pelo rótulo** ("40 a 44 anos"), não pelo código da classificação, para uma renumeração no SIDRA não devolver número errado em silêncio |
| **IBGE malhas** | geometria e centroides | centroide e área são calculados da geometria, evitando mais uma chamada |
| **Google Places** | óticas concorrentes | única fonte paga: cache eterno em disco, custo estimado antes do lote, raio proporcional à área, dedup por `place_id` |
| **OSRM** | distância rodoviária ao polo | pré-filtro por distância em linha reta antes de chamar o roteador (senão vira 5.570 × 5.570) |

**Código de município.** O CNES usa 6 dígitos, o IBGE usa 7. Um join direto não dá erro — ele
devolve zero linha, e a cidade some do ranking sem ninguém perceber. O pipeline normaliza tudo para
7 dígitos calculando o dígito verificador, e há teste unitário que falha se aparecer órfão.

**Espelhos.** Quando as APIs do IBGE estão inacessíveis (rede corporativa, apagão, ambiente sem
egress), `--espelho` usa cópias públicas dos dados do IBGE para a dimensão município (código, nome,
UF, centroide, geometria). Isso **não** cobre população, renda nem CNES: esses campos ficam nulos e
a confiança cai. A origem de cada bloco aparece no resumo de proveniência ao fim da execução.

---

## Requisitos não-funcionais atendidos

- **Idempotência**: upsert por chave natural em todas as tabelas.
- **Cache em disco** de toda requisição externa, com TTL por fonte no `.env`. Desenvolvimento não
  depende de rede.
- **Logs estruturados** por etapa, com entrada, saída e motivo de cada descarte. Queda de volume
  sem motivo declarado vira aviso.
- **Retry com backoff exponencial** (2s, 4s, 8s, 16s) e rate limit por fonte.
- **Segredos** só em `.env` (gitignored).
- **Testes**: normalização de código IBGE, deduplicação de profissionais, agregação do CNES,
  parsing do SIDRA e cálculo do score com fixtures conhecidas (`uv run pytest`).

---

## Dashboard

Três telas, pensadas como terminal de análise e não como site: densidade legível e velocidade de
comparação acima de tudo.

1. **Mapa + tabela** — split redimensionável, choropleth por score, colunas ordenáveis, filtros e
   exportação do conjunto filtrado. Mapa e tabela são ligados nos dois sentidos: hover na linha
   acende o município, clique no mapa seleciona, **shift + arrastar** no mapa filtra o conjunto pela
   área.
2. **Ficha do município** — breakdown do score fator a fator, dados brutos, polo e distância,
   óticas encontradas, alertas de canibalização e campo de notas de validação de campo (incluindo
   fila do SUS, preenchida à mão).
3. **Ajuste de pesos** — sliders com recálculo ao vivo e comparação lado a lado com o ranking
   atual. O selo "conferência" recalcula com os pesos originais e compara com o que o pipeline
   gravou: se os dois modelos divergirem, a tela avisa.

**Sem tiles pagos e sem tiles nenhum, por padrão.** A malha municipal já é o mapa. Isso zera custo
de basemap (Mapbox e Google Maps JS estão fora por preço), acelera o carregamento e faz o dashboard
funcionar offline. Quem quiser contexto define `VITE_BASEMAP_STYLE` com um style MapLibre próprio.

Acessibilidade e qualidade mínima: responsivo até tablet, foco de teclado visível, cabeçalhos de
tabela operáveis por teclado, `prefers-reduced-motion` respeitado, estados de carregamento e vazio
com direção clara.

### Deploy

O dashboard é estático. Na Vercel, aponte um projeto para `mapa-optico/web` (o `vercel.json` de lá
já traz a configuração). O `snapshot.json` versionado é o que vai ao ar — republicar dados novos é
rodar o pipeline, commitar o snapshot e fazer deploy.

---

## Onde estamos no plano de execução

- **Fase 0 — validação do CNES**: implementada e pronta para rodar (`mapa-optico fase0 --uf SC`).
  Ainda **não executada contra o DATASUS**: veja a nota abaixo.
- **Fase 1 — pipeline completo em SC**: implementada ponta a ponta.
- **Fase 2 — validação de campo**: a ficha do município já tem o campo de notas e o de fila do SUS.
- **Fase 3 — dashboard**: as três telas estão de pé.
- **Fase 4 — escala nacional**: o pipeline aceita `--uf` com várias UFs ou nenhuma (Brasil inteiro);
  o Places tem estimativa de custo e limite de chamadas.
- **Fase 5 — loop de calibração**: tabela `eventos` criada no schema; a entrada de resultados pela
  interface é o próximo passo.

> **Nota sobre o ambiente de desenvolvimento**: o sandbox onde este código foi escrito bloqueia
> `cnes.datasus.gov.br`, `servicodados.ibge.gov.br`, `apisidra.ibge.gov.br` e
> `router.project-osrm.org` por política de rede. Rode `mapa-optico checar-fontes` e `mapa-optico
> fase0 --uf SC` numa máquina com acesso livre para fechar a Fase 0 com dado real. O snapshot
> versionado em `web/public/data/` foi gerado com `mapa-optico demo` e é **sintético** — a interface
> exibe tarja vermelha permanente enquanto for esse o caso.
