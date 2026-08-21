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

**Circuitos e canibalização.** Municípios vizinhos de score alto são agrupados em circuitos de 3 a
4 cidades para diluir o deslocamento do médico. O briefing sugeria DBSCAN com eps de 60 km, e foi
assim que começou — mas DBSCAN agrupa por alcançabilidade transitiva, e rodando em SC o estado
inteiro virou **um** circuito de 186 municípios. Verdade geográfica, inútil como roteiro. O que
está no lugar é guloso e explicável: pega o município de melhor score ainda sem circuito, junta os
melhores vizinhos dentro do raio até fechar o tamanho, remove todos e repete. Município que não
alcança ninguém fica avulso em vez de virar circuito de um.

E dois municípios do topo a menos de 30 km um do outro geram alerta: provavelmente compartilham
público e devem virar um circuito único, não dois eventos.

---

## O modelo de faturamento, em português claro

O score responde **onde** há demanda reprimida. Esta parte responde **quanto** isso vira dinheiro.
Os parâmetros ficam em `pipeline/config/negocio.yaml`, separados dos pesos de propósito: peso muda
quando aprendemos sobre o mercado, ticket muda quando o fornecedor reajusta.

A cadeia inteira, de habitante a lucro:

```
população 40+
  × prevalência de necessidade de correção
  × renovação anual de receita            = demanda anual da cidade
  − capacidade instalada dos oftalmos locais   ← CNES: carga horária real
                                          = demanda não atendida
  × atrito de deslocamento até o polo      = demanda represada AQUI
  × anos de fila acumulada                 = público de um primeiro evento
  × alcance da mídia × agendamento × comparecimento
  LIMITADO PELA AGENDA FÍSICA DO MÉDICO    = consultas
  × conversão em venda                     ← óticas locais, notas e avaliações
  × ticket (modulado pela renda)           = faturamento
  − custo do par − custo do evento − mídia = lucro
```

**O teto físico é o que impede o ranking de virar "ordene por população".** Um médico faz N
refrações por dia; um evento de 3 dias tem um teto que nenhuma cidade grande ultrapassa. Quando a
procura passa desse teto, o excedente não some: vira `dias_sugeridos` e `demanda_nao_capturada` —
sinal de que aquela cidade comporta um evento mais longo ou uma segunda visita.

**A "% de possibilidade" é o faturamento contra o teto teórico** (agenda cheia × conversão máxima ×
ticket máximo). Como o teto é o mesmo para todos, o percentual compara cidades — e, por construção,
se decompõe em exatamente três fatores multiplicativos:

```
potencial = ocupação da agenda × (conversão / conversão máxima) × (ticket / ticket máximo)
```

Os três aparecem separados na ficha, e o teste `test_potencial_e_exatamente_o_produto_dos_tres_fatores_mostrados_na_ficha`
garante que o número da tela é reconstruível a partir da explicação da tela. **Ocupação** vem dos
médicos e da distância; **conversão** vem das óticas, suas notas e o volume de avaliações;
**ticket** vem da renda.

**As três leituras da concorrência são independentes, e as três saem do Google Places:**

| Sinal | O que mede | Por que importa |
|---|---|---|
| Quantidade de óticas por 10 mil hab | saturação | mercado cheio converte menos |
| Nota média, ponderada por avaliações | força | concorrente nota 4,8 segura o cliente; nota 3,2 é oportunidade, não ameaça |
| Avaliações por mil habitantes | movimento real | trinta óticas sem avaliação nenhuma pesam menos que três com 400 |

**Cidade com zero ótica não herda a nota mediana do estado.** Ausência de concorrente é informação,
não buraco de coleta — imputar a média puniria justamente o município mais virgem. Já cidade que
nunca foi consultada no Places recebe a mediana do universo, **marcada como imputada** e descontada
de `projecao_confianca`.

**O custo do par não é fração fixa do ticket.** Este arquivo começou assim, e estava errado. Com
par de R$ 400 custando R$ 40 (10%) e par de R$ 1.200 custando R$ 180 (15%), a fração **sobe** com o
preço — lente melhor custa proporcionalmente mais. Uma fração única erraria os dois extremos ao
mesmo tempo: subestimaria o custo da linha de cima e superestimaria o da de baixo. O modelo
interpola entre os dois pontos informados, e como o ticket já chega limitado à faixa praticada,
nunca extrapola para fora do que a operação de fato conhece.

O efeito no negócio é grande: a margem é de 85% a 90% do preço, e o **ponto de equilíbrio de um
evento fica na casa de uma dezena de pares**. É esse número que decide o risco de ir a uma cidade.

**Onde isso se compara com o mercado.** O ticket médio do setor óptico brasileiro fica em torno de
R$ 250 por par, com cerca de 106,5 milhões de pares por ano em 71 mil pontos de venda
([Abióptica](https://atacadooptico.com/blog/mercado-optico-brasileiro-2026-numeros-e-oportunidades-reais)).
A faixa de R$ 400 a R$ 1.200 praticada aqui está bem acima da média nacional — coerente com venda
feita com a receita na mão, mas é um número a vigiar: se o mix real cair para perto do piso, a
projeção inteira encolhe. Do lado da demanda, a fila do SUS para oftalmologia passa de dois anos
segundo as associações de pacientes
([Câmara dos Deputados](https://www.camara.leg.br/noticias/1080344-associacoes-de-pacientes-com-problemas-de-visao-sugerem-prazos-para-atendimento-no-sus/)),
e o país tem 9,2 oftalmologistas por 100 mil habitantes — o que sustenta o parâmetro de anos de
fila acumulada e serve de conferência de sanidade para a contagem do CNES.

**Sobre a confiança dos parâmetros.** Cada número do `negocio.yaml` carrega sua origem:
`[informado]` veio da operação, `[estimado]` é constante clínica ou demográfica com base
defensável, `[calibrável]` é chute inicial. Os calibráveis movem o **tamanho** da projeção, não a
**ordem** do ranking, porque incidem igual em todos os municípios — e cada evento registrado na
tabela `eventos` corrige um deles.

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

Telas pensadas como terminal de análise e não como site: densidade legível e velocidade de
comparação acima de tudo.

1. **Mapa + tabela** — split redimensionável, colunas ordenáveis, filtros e exportação do conjunto
   filtrado. Mapa e tabela são ligados nos dois sentidos: hover na linha acende o município, clique
   no mapa seleciona, **shift + arrastar** no mapa filtra o conjunto pela área.

   O seletor **Ordenar por** é o controle mais forte da barra, porque "melhor cidade" muda de
   significado conforme a pergunta: *lucro estimado* (padrão), *potencial %*, *faturamento*,
   *retorno sobre o custo* e *demanda reprimida*. O choropleth acompanha a escolha — o mapa sempre
   pinta a métrica que está ordenando a tabela.

2. **Ficha do município** — a projeção financeira abre a ficha: o potencial decomposto nos três
   fatores, o funil inteiro de habitante a consulta, a leitura da concorrência e a conta fechada até
   o lucro. Depois vêm o breakdown do score, dados brutos, polo e distância, óticas encontradas,
   alertas de canibalização e o campo de notas de validação de campo (incluindo fila do SUS).

3. **Faturamento** — os parâmetros do negócio em sliders, cada um marcado com a origem do número
   (informado / estimado / calibrável), com recálculo ao vivo do ranking de lucro e comparação lado
   a lado com o que o pipeline gravou.

4. **Ajuste de pesos** — o mesmo, para os pesos do score. Em ambas as telas o selo "conferência"
   recalcula com os parâmetros originais e compara com o pipeline: se os dois modelos divergirem, a
   tela avisa em vez de fingir que está tudo certo.

5. **Sincronizar** — atualizar os dados sem terminal. Uma linha por fonte com quando ela foi
   coletada e se ainda vale, e um botão que dispara o pipeline.

**Sem tiles pagos e sem tiles nenhum, por padrão.** A malha municipal já é o mapa. Isso zera custo
de basemap (Mapbox e Google Maps JS estão fora por preço), acelera o carregamento e faz o dashboard
funcionar offline. Quem quiser contexto define `VITE_BASEMAP_STYLE` com um style MapLibre próprio.

Acessibilidade e qualidade mínima: responsivo até tablet, foco de teclado visível, cabeçalhos de
tabela operáveis por teclado, `prefers-reduced-motion` respeitado, estados de carregamento e vazio
com direção clara.

### Sincronizar sem terminal

O pipeline é Python e lê o CNES em `.DBC` — nada disso roda num navegador. Então o botão não roda o
pipeline: ele **aciona o robô**.

```
botão na aba Sincronizar
  → POST /api/sincronizar          (função serverless da Vercel; é ela que guarda o token)
  → workflow_dispatch no GitHub Actions
  → pipeline roda, grava no Supabase e commita o snapshot novo
  → deploy automático, dados novos no ar
```

O token do GitHub fica na função serverless e **nunca vai ao navegador** — quem tem o token pode
rodar workflows no repositório. O navegador só consegue pedir duas coisas: "como está" e "dispara
com estes parâmetros"; o que é aceitável em cada uma delas é decidido no servidor.

Três garantias que a tela oferece:

- **Nunca gasta sem mostrar a conta.** O Places é a única fonte que cobra. A estimativa aparece
  antes (número de consultas × preço por consulta) e o disparo exige uma confirmação separada.
  Município já consultado não é consultado de novo, então a conta real tende a ser menor.
- **Cada fonte envelhece no seu ritmo.** O CNES publica competência mensal; o Censo dura anos. Uma
  barra única de "atualizado em" esconderia justamente a fonte que precisa de atenção.
- **Falta de configuração não é erro.** Sem o `GITHUB_TOKEN` a aba explica o que falta e quem
  resolve, em vez de mostrar um botão que não funciona.

Além do botão, o workflow roda sozinho todo dia 5, quando o CNES publica a competência nova.

### Deploy

O dashboard é estático. Na Vercel, aponte um projeto para `mapa-optico/web` (o `vercel.json` de lá
já traz a configuração, inclusive a exclusão de `api/` do rewrite de SPA — sem ela a rota de
sincronização receberia HTML no lugar de JSON). O `snapshot.json` versionado é o que vai ao ar.

Variáveis de ambiente do projeto na Vercel:

| Variável | Para quê | Vai ao navegador? |
|---|---|---|
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | ler o ranking do banco em vez do snapshot | sim (por isso é a chave anônima) |
| `VITE_BASEMAP_STYLE` | basemap opcional | sim |
| `GITHUB_TOKEN` | disparar o pipeline pela aba Sincronizar | **não** |
| `GITHUB_REPO`, `GITHUB_REF_SINCRONIZACAO` | onde o workflow roda | não |

O `GITHUB_TOKEN` deve ser fine-grained, com permissão **Actions: read and write** apenas neste
repositório. A ausência do prefixo `VITE_` é o que garante que ele não entre no bundle.

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
  interface é o próximo passo. É ela que transforma o `potencial %` de índice comparativo em
  probabilidade calibrada — enquanto não houver evento executado, o número ordena cidades, mas não
  afirma chance de sucesso, e a interface diz isso.

> **Nota sobre o ambiente de desenvolvimento**: o sandbox onde este código foi escrito bloqueia
> `cnes.datasus.gov.br`, `servicodados.ibge.gov.br`, `apisidra.ibge.gov.br` e
> `router.project-osrm.org` por política de rede. Rode `mapa-optico checar-fontes` e `mapa-optico
> fase0 --uf SC` numa máquina com acesso livre para fechar a Fase 0 com dado real. O snapshot
> versionado em `web/public/data/` foi gerado com `mapa-optico demo` e é **sintético** — a interface
> exibe tarja vermelha permanente enquanto for esse o caso.
