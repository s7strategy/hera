# S7 Editor

Você joga 30 criativos numa pasta, diz em uma linha o que quer mudar e recebe os 30 prontos, num ZIP, com relatório.
Trocar o CTA de um lote inteiro, converter tudo de 9:16 para 16:9 sem distorcer, ou mandar referências e receber peças novas parecidas.
E com uma garantia que ferramenta de IA não dá: **quando você pede para mudar só o CTA, todo o resto da imagem sai idêntico ao original, pixel por pixel.**

---

## 1. Instalação

Precisa de **Python 3.11 ou mais novo**. Faz uma vez e nunca mais.

### Mac

```bash
# 1. Python e o OCR (o tesseract destrava a busca por texto sem gastar API)
#    brew install tesseract tesseract-lang
brew install python@3.11

# 2. Entre na pasta do projeto
cd ~/s7editor

# 3. Crie o ambiente e instale
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Prepare as pastas e as receitas de exemplo
python -m s7editor.cli init

# 5. Confira se está tudo certo
python -m s7editor.cli doctor
```

### VPS Linux (Ubuntu / Debian)

```bash
# 1. Python, as bibliotecas que o Pillow precisa e o OCR
#    (o tesseract-ocr destrava a busca por texto sem gastar API — veja a seção 2)
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip \
                    libjpeg-dev zlib1g-dev libfreetype6-dev

# 2. Entre na pasta do projeto
cd ~/s7editor

# 3. Crie o ambiente e instale
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Prepare as pastas e as receitas de exemplo
python -m s7editor.cli init

# 5. Confira se está tudo certo
python -m s7editor.cli doctor
```

> **Por que `opencv-python-headless` e não `opencv-python`?** A versão *headless* não instala biblioteca de janela gráfica. Em VPS isso evita uma dor de cabeça de 20 minutos com dependência de GTK/Qt, e o editor não abre janela nenhuma mesmo.

### Atalho para digitar menos

Todo comando deste README começa com `python -m s7editor.cli`. Se quiser encurtar para `s7edit`, cole isto uma vez no seu `~/.zshrc` (Mac) ou `~/.bashrc` (Linux):

```bash
alias s7edit="$HOME/s7editor/.venv/bin/python -m s7editor.cli"
```

Depois abra um terminal novo e use `s7edit doctor`, `s7edit run ...` e assim por diante.

**Toda vez que abrir um terminal novo** (sem o alias), lembre de ativar o ambiente antes:

```bash
cd ~/s7editor && source .venv/bin/activate
```

---

## 2. A chave da OpenAI (e por que na maioria das vezes você não precisa dela)

Copie o modelo e preencha:

```bash
cp .env.example .env
nano .env        # ou abra no editor que preferir
```

Dentro do `.env`, a linha é exatamente esta — o nome da variável é **`OPENAI_API_KEY`**:

```
OPENAI_API_KEY=sk-sua-chave-aqui
```

A chave sai de <https://platform.openai.com/api-keys>. O arquivo `.env` fica fora do Git (já está no `.gitignore`); **nunca** cole a chave dentro de uma receita ou de um arquivo de código.

### O que funciona SEM chave nenhuma

| Funciona offline, de graça | Precisa da chave |
|---|---|
| Trocar texto (o CTA, a headline, o preço) | Variações **generativas** e **hybrid** |
| Apagar texto | Reenquadramento no modo **outpaint** |
| Reenquadrar em `pad`, `crop` e `relayout` | Leitura automática do texto por visão computacional |
| Variações no modo **template** | |
| Sobrepor logo, redimensionar, exportar | |

Ou seja: **os dois pedidos mais comuns — trocar o CTA do lote e passar tudo de 9:16 para 16:9 — rodam sem chave, sem internet e sem custo.** A chave só entra quando você quer que a IA invente pixel novo.

Se faltar a chave e você pedir uma operação de IA, o editor não quebra e não devolve erro técnico: ele diz em português o que faltou e qual é a alternativa offline.

---

## 2.1. O OCR — como achar o texto sem gastar API

Para trocar "GARANTA O SEU" por "ÚLTIMAS VAGAS", o S7 Editor precisa **achar** essa
frase. Ele consegue de três jeitos, do mais barato para o mais caro:

| Como | Precisa de quê | Comando |
|---|---|---|
| Pelo texto | Tesseract instalado (grátis) | `--de "GARANTA O SEU"` |
| Pelo papel do bloco | nada | `--papel cta` |
| Pela posição | nada | `--caixa 0.1,0.82,0.8,0.07` |

Instalar o Tesseract (uma vez só):

```bash
sudo apt install tesseract-ocr tesseract-ocr-por    # Ubuntu / VPS
brew install tesseract tesseract-lang               # macOS
```

Sem ele, `--de` só funciona com a chave da OpenAI configurada — mas `--papel` e
`--caixa` continuam funcionando de graça. `./s7edit doctor` diz o que você tem.

> Se rodar `--de` com um texto que não existe nas imagens, o S7 Editor **não**
> diz que deu certo: ele avisa quantas imagens saíram sem alteração, explica o
> motivo e termina com código de erro.

## 3. Os 3 fluxos

Em todos eles: as imagens entram numa pasta dentro de `inbox/` e o resultado sai em `outbox/`, com ZIP e relatório.

### a) Trocar o CTA de 30 imagens sem mexer no resto

```bash
python -m s7editor.cli trocar-texto inbox/campanha-agosto \
  --de "GARANTA O SEU" \
  --para "ULTIMAS VAGAS"
```

Não sabe o texto exato que está nas peças? O `--de` já ignora acento, maiúscula/minúscula e pontuação. Se ainda assim variar de peça para peça, localize pelo **papel** do bloco:

```bash
python -m s7editor.cli trocar-texto inbox/campanha-agosto --papel cta --para "COMPRE AGORA"
```

Ou pela **posição** (fração da imagem: 10% da esquerda, 82% do topo, 80% de largura, 7% de altura):

```bash
python -m s7editor.cli trocar-texto inbox/campanha-agosto \
  --caixa 0.1,0.82,0.8,0.07 --para "COMPRE AGORA"
```

Para ver o que o editor enxerga em cada peça antes de rodar:

```bash
python -m s7editor.cli inspect inbox/campanha-agosto
```

### b) Passar 30 criativos de 9:16 para 16:9 sem distorcer

```bash
python -m s7editor.cli reframe inbox/campanha-agosto --to 16:9 --mode relayout --long-edge 1920
```

O conteúdo **nunca é esticado**. Ele é reposicionado no quadro novo e a área que sobra é preenchida conforme o modo:

- `--mode pad` — o mais seguro: o criativo inteiro aparece, as laterais recebem um fundo borrado tirado da própria peça. Offline.
- `--mode crop` — corta preservando o assunto. Offline. Perde as pontas.
- `--mode relayout` — apaga o texto, estende o fundo e redesenha o texto no enquadramento novo. Offline quando o fundo é cor chapada ou degradê; é o que dá o resultado mais "desenhado para 16:9".
- `--mode outpaint` — a IA inventa as laterais. **Precisa da chave** e tem custo.

Aceita também `--to 1920x1080` (tamanho exato) e `--to 9:16@1080`.


**Os modos, e o que esperar de cada um**

| Modo | O que faz | Custo | Estado |
|---|---|---|---|
| `pad` | Põe a peça inteira no novo formato, sem esticar nada, e preenche as laterais com o fundo desfocado. | grátis | **recomendado** |
| `crop` | Corta para o novo formato preservando o texto e as áreas seguras. | grátis | pronto |
| `outpaint` | Estende o cenário com IA e recola o original por cima, intacto. | ~US$ 0,04/imagem | precisa de chave |
| `relayout` | Reposiciona os textos soltos para aproveitar o novo espaço. Texto que vive dentro de faixa ou selo colorido fica onde está, junto do seu contêiner. | grátis | **experimental** — confira antes de publicar |

O tamanho de saída sai da própria imagem: um criativo 1080x1920 vira **1920x1080**
em 16:9. Para fixar outro tamanho, use `--to 1280x720` ou `--to 16:9@1600`.

### c) Gerar 30 criativos novos parecidos com os de referência

```bash
python -m s7editor.cli vary inbox/referencias -n 30 --mode hybrid
```

O editor lê o "DNA" das referências (paleta, tipografia, arquétipo de layout, jeito de escrever a copy e o CTA) e produz peças novas no mesmo espírito.

- `--mode template` — **offline e de graça.** Reaproveita as suas peças e troca só os textos. Consistência de marca perfeita.
- `--mode hybrid` — **o recomendado com IA.** O fundo é gerado pela IA e o texto é escrito por cima pelo editor, com a tipografia certa. Isso resolve o defeito mais chato dos geradores de imagem, que é escrever palavra errada dentro da peça.
- `--mode generative` — a IA faz a imagem inteira. Mais variedade; confira a ortografia peça por peça.

### Coisas que valem para qualquer comando

```bash
--dry-run            mostra o plano e não grava nada
--out PASTA          escolhe a pasta de saída
-j 8                 processa 8 imagens em paralelo
--force              sobrescreve uma pasta de saída que já existe
--quality low        baixa o custo das operações com IA
--verbose            mostra tudo, inclusive o erro técnico completo
```

E quando o terminal cansar, existe uma interface no navegador:

```bash
python -m s7editor.cli ui        # abre em http://127.0.0.1:8770
```

---

## 4. A pasta de trabalho

```
s7editor/
├── inbox/          VOCÊ JOGA AS IMAGENS AQUI
│   ├── campanha-agosto/     ← uma subpasta por lote (30 arquivos .png/.jpg)
│   └── referencias/
│
├── recipes/        O QUE MUDAR (arquivos .yaml, editáveis no bloco de notas)
│   ├── trocar-cta.yaml
│   ├── trocar-cta-avancado.yaml
│   ├── reframe-16x9.yaml
│   └── variacoes-30.yaml
│
├── outbox/         SAI TUDO AQUI
│   └── campanha-setembro/
│       ├── criativo-01.png ...      as imagens prontas
│       ├── campanha-setembro.zip    tudo junto (o nome vem do campo 'job')
│       ├── relatorio.html           ANTES x DEPOIS + a prova de zero drift
│       ├── contato.png              mosaico para conferir as 30 de uma olhada
│       └── manifest.json            o registro técnico do lote
│
├── fonts/          as fontes da marca (.ttf/.otf) — veja fonts/README.md
├── .env            a chave da OpenAI (não vai para o Git)
└── .cache/         cache de análise; pode apagar quando quiser
```

Regra simples: **um lote = uma subpasta em `inbox/`.** Nunca misture campanhas na mesma pasta, senão o `--de "GARANTA O SEU"` vai procurar aquele texto em peça que nem tem CTA.

Caminhos escritos dentro de uma receita são relativos à raiz do projeto, não à pasta de onde você rodou o comando. Assim a receita continua funcionando de qualquer lugar.

---

## 5. A garantia de "não mudou mais nada"

Esse é o ponto que separa o S7 Editor de jogar a imagem num chat de IA e pedir "troque só o botão".

Um modelo de imagem **redesenha a peça inteira**. Mesmo quando o resultado parece igual, o logo mudou 2 tons, a foto perdeu textura e o degradê saiu diferente. Em 30 peças, ninguém confere isso a olho.

Aqui existem duas trilhas, e as duas terminam com a mesma prova.

**Trilha determinística (a padrão, offline).** O editor olha os pixels da caixa do texto, descobre a cor do fundo, o tipo de fundo (cor chapada, degradê ou foto) e a tipografia usada — família, peso, corpo, cor, espaçamento entre letras, contorno e sombra. Aí ele apaga as letras **reconstruindo o fundo** que estava atrás delas e escreve o texto novo com a mesma tipografia. Nenhum pixel fora da caixa é encostado: a escrita acontece dentro de um recorte, e todo pixel que não faz parte da letra é **copiado do original**, não recalculado.

**Trilha com IA e composição protegida.** Quando o fundo é complexo demais e a IA precisa entrar, o resultado entregue **não é** o que a IA devolveu. É o **seu original**, com apenas a região mascarada colada por cima. Fora da máscara, os pixels são os do arquivo que você mandou — sem exceção. Isso vale inclusive para o reenquadramento: no `outpaint`, o centro da peça é recolado a partir do arquivo original, e não do que o modelo devolveu.

**A prova.** Antes de gravar o arquivo, o editor compara a imagem final com a original pixel a pixel e conta quantos pixels mudaram **fora** das caixas que você autorizou editar. Esse número aparece no terminal e no `relatorio.html`:

```
  Zero drift verificado: 0 pixels alterados fora da área editada.
```

Se algum dia esse número não for zero, o relatório mostra a contagem e onde foi a maior mancha — é sinal de bug, não de "coisa da IA", e dá para reportar com o nome do arquivo.

---

## 6. Referência da receita YAML

A receita é para o que não cabe numa linha de comando: várias operações, estilos forçados, arquivos diferentes recebendo tratamentos diferentes.

```bash
python -m s7editor.cli run recipes/trocar-cta.yaml
```

Um `.yaml` é texto puro. As regras: dois espaços de indentação (nunca TAB), `chave: valor`, e `- ` na frente de cada item de lista. Erro de digitação não te deixa rodar o lote errado: o editor valida tudo antes de tocar em imagem e aponta a linha e o campo em português.

### Campos do topo

| Campo | O que é | Exemplo |
|---|---|---|
| `job` | Nome do lote. Vira o nome do ZIP. | `job: trocar-cta-setembro` |
| `input` | Pasta de entrada. | `input: inbox/campanha-agosto` |
| `output` | Pasta de saída. | `output: outbox/campanha-setembro` |
| `engine` | `deterministic` (offline, garantido) · `ai` · `auto` (tenta offline e só chama IA se precisar). Vale para todas as operações que não declararem a sua. | `engine: deterministic` |
| `operations` | A lista do que fazer. Ver abaixo. | |
| `target` | Reenquadra tudo no fim. `"16:9"`, `"1920x1080"` ou `"16:9@1920"`. | `target: "16:9"` |
| `reframe_mode` | `pad` · `crop` · `relayout` · `outpaint` | `reframe_mode: relayout` |
| `reframe_fill` | Preenchimento das sobras: `blur` · `mirror` · `color` · `white` · `black` | `reframe_fill: blur` |
| `long_edge` | Lado maior em pixels do resultado. | `long_edge: 1920` |
| `variations` | Bloco de geração de peças novas. Ver abaixo. | |
| `deliver` | O que entregar. Ver abaixo. | |
| `recursive` | `true` varre também as subpastas do `input`. | `recursive: false` |
| `quality` | `low` · `medium` · `high` — custo/qualidade da IA. | `quality: medium` |
| `notes` | Anotação sua; vai para o manifesto. | `notes: "pedido do cliente X"` |

Os nomes aceitam apelido em português: `entrada`, `saida`, `motor`, `operacoes`, `formato`, `entrega`, `variacoes`.

### Chaves comuns a qualquer operação

| Chave | O que faz |
|---|---|
| `type` | Qual operação (obrigatório). |
| `engine` | Sobrescreve o motor só nesta operação. |
| `scope` | Em quais arquivos aplicar. Glob (`"*.png"`, `"story-*"`), índices (`"1,3,5"`), intervalos (`"1-10"`, `"5-"`, `"-3"`), exclusão com `!` (`"all,!*.jpg"`). Combina com vírgula. Padrão: todas. |
| `enabled` | `false` desliga a operação sem apagá-la da receita. |
| `note` | Comentário seu. |

### As 10 operações

**`replace_text`** — troca um texto. Precisa de `replace` (o texto novo) e de **um** localizador: `find`, `role` ou `box`.

```yaml
- type: replace_text
  find: "GARANTA O SEU"      # texto atual
  match: fuzzy               # fuzzy (ignora acento/caixa) | exact
  replace: "ULTIMAS VAGAS"
  autofit: true              # reduz o corpo até caber
  max_lines: 2
  grow_box: false            # autoriza crescer a caixa se o fundo em volta permitir
  style:                     # opcional: só o que você quer FORÇAR
    family: Inter
    weight: bold             # thin|light|regular|medium|semibold|bold|black
    color: "#ffffff"         # hex, [255,255,255] ou "branco"
    uppercase: true
    align: center            # left|center|right
    valign: middle           # top|middle|bottom
    letter_spacing: 1.5
    line_height: 1.15
    stroke_width: 2
    stroke_color: "#000000"
    shadow: true
    shadow_color: "#000000"
    shadow_offset: [0, 2]
    shadow_blur: 4
    opacity: 1.0
```

O que você **não** declarar em `style` é copiado do original. Papéis válidos em `role`: `headline`, `subhead`, `cta`, `price`, `badge`, `legal`, `logo`, `other`.

**`remove_text`** — apaga um texto e reconstrói o fundo.

```yaml
- type: remove_text
  role: legal
  feather: 1
```

**`add_text`** — escreve um texto novo onde não havia nada. Precisa de `box` e `text`.

```yaml
- type: add_text
  box: {x: 0.05, y: 0.05, w: 0.4, h: 0.06, norm: true}
  text: "NOVO"
  role: badge
  style: {color: "#ffffff", weight: black, uppercase: true}
```

**`replace_color`** — troca uma cor por outra (rebranding). Precisa de `from` e `to`.

```yaml
- type: replace_color
  from: "#e01b24"
  to: "#1c71d8"
  tolerance: 12              # quanto de variação da cor original conta como "a mesma"
  box: {x: 0, y: 0.8, w: 1, h: 0.2, norm: true}    # opcional: limita a região
```

**`replace_region`** — a IA reinventa **só** o que está dentro da caixa; o resto é o original colado por cima. Precisa de `box` e `prompt`. **Usa a chave.**

```yaml
- type: replace_region
  box: {x: 0.1, y: 0.1, w: 0.5, h: 0.4, norm: true}
  prompt: "mesma mesa de madeira, sem a xícara"
  feather: 2
  strength: 0.8
```

**`remove_object`** — apaga um objeto e fecha o buraco. Precisa de `box` ou `find`.

```yaml
- type: remove_object
  box: {x: 0.6, y: 0.2, w: 0.2, h: 0.3, norm: true}
```

**`reframe`** — reenquadra. Precisa de `target`.

```yaml
- type: reframe
  target: "16:9"
  mode: relayout             # pad|crop|relayout|outpaint
  fill: blur
  long_edge: 1920
```

**`overlay`** — cola um PNG (logo, selo). Precisa de `image`.

```yaml
- type: overlay
  image: assets/logo.png
  position: bottom-right     # top-left|top|top-right|left|center|right|
                             # bottom-left|bottom|bottom-right — ou use box: {...}
  margin: 32
  scale: 0.18
  opacity: 1.0
```

**`resize`** — muda o tamanho sem mudar a proporção.

```yaml
- type: resize
  long_edge: 1080            # ou width/height, ou scale: 0.5
  keep_aspect: true
```

**`export`** — força formato e qualidade só deste lote.

```yaml
- type: export
  format: png                # png|jpg|webp
  quality: 95
  prefix: "bf_"
  suffix: "-v2"
```

### Caixas (`box`)

Duas formas. **Normalizada** (recomendada) usa fração da imagem, então a mesma caixa serve para peças de tamanhos diferentes:

```yaml
box: {x: 0.10, y: 0.82, w: 0.80, h: 0.07, norm: true}
```

Em **pixels**, para uma peça de tamanho conhecido:

```yaml
box: {x: 108, y: 1574, w: 864, h: 134}
```

### `deliver` — o que sai no fim

```yaml
deliver:
  zip: true             # junta tudo num .zip
  report: true          # relatorio.html com ANTES x DEPOIS e a prova de zero drift
  contact_sheet: true   # mosaico com todas as peças
  format: png           # png|jpg|webp — leia a seção 8 antes de pôr jpg
  quality: 95
  prefix: ""            # texto antes do nome do arquivo
  suffix: ""            # texto depois do nome do arquivo
```

### `variations` — gerar peças novas

```yaml
variations:
  n: 30
  mode: hybrid          # hybrid (recomendado) | generative
  aspect: "9:16"
  prompt: "campanha de black friday, tom de urgência"
  seed: 7               # mesma seed => mesmos textos
  copy:                 # opcional: ditar os textos em vez de a IA escrever
    - {headline: "50% OFF HOJE", subhead: "só até meia-noite", cta: "QUERO O MEU"}
```

> **Atenção:** o modo offline `template` hoje só funciona pela linha de comando
> (`vary --mode template`); dentro da receita, `variations.mode` aceita apenas
> `hybrid` e `generative`, que usam a chave.

As quatro receitas em `recipes/` já vêm comentadas e prontas para você copiar e adaptar. Se apagar `trocar-cta.yaml`, `reframe-16x9.yaml` ou `variacoes-30.yaml`, o comando `python -m s7editor.cli init` traz de volta.

---

## 7. Custo

A trilha determinística **não custa nada** e não manda seu criativo para lugar nenhum. Só o que chama a OpenAI tem preço.

Estimativa para **um lote de 30 imagens**, na qualidade padrão (`medium`):

| O que você rodou | Chama IA? | Custo dos 30 |
|---|---|---|
| `trocar-texto` (trocar o CTA) | não | **US$ 0,00** |
| `reframe --mode pad` / `crop` / `relayout` | não | **US$ 0,00** |
| `vary --mode template` | não | **US$ 0,00** |
| `run` de receita com `engine: deterministic` | não | **US$ 0,00** |
| `inspect` com leitura por visão | sim | ~US$ 0,09 |
| `reframe --mode outpaint` | sim | ~US$ 1,90 (até ~US$ 3,80 se precisar de segunda tentativa) |
| `vary --mode hybrid` | sim | ~US$ 1,90 |
| `vary --mode generative` | sim | ~US$ 1,90 |

Trocando a qualidade, os modos com IA ficam assim para os mesmos 30:

| Qualidade | Custo dos 30 | Quando usar |
|---|---|---|
| `--quality low` | ~US$ 0,50 | rascunho, testar o conceito |
| `--quality medium` (padrão) | ~US$ 1,90 | uso normal |
| `--quality high` | ~US$ 7,50 | peça final de mídia paga |

Em reais, com o dólar por volta de R$ 5,50: `medium` sai perto de **R$ 10 por lote de 30**. Preço da OpenAI muda sem aviso — o editor **sempre imprime o custo estimado antes de gastar**, e todo comando aceita `--dry-run` para ver o plano sem pagar nada.

O custo real de cada lote fica registrado no `manifest.json` e no `relatorio.html`.

---

## 8. Limites conhecidos e o que fazer quando der errado

**A fonte da marca não está instalada.**
O editor não trava: ele usa a fonte mais parecida do sistema e registra o aviso no relatório. Mas o CTA sai com um desenho de letra ligeiramente diferente do resto da peça. Solução: jogue os arquivos `.ttf`/`.otf` da marca dentro de `fonts/` (essa pasta tem prioridade sobre o sistema), com o nome que veio da fundição — `Inter-Bold.ttf`, `Montserrat-SemiBold.ttf`. Confira com `python -m s7editor.cli doctor`, que lista as famílias encontradas.

**O texto novo é muito maior que o antigo.**
"COMPRE" ocupa menos espaço que "APROVEITE ESSA CONDIÇÃO ESPECIAL". O editor tenta, nesta ordem: reduzir o corpo até 15%, quebrar em mais uma linha, apertar a entrelinha, apertar levemente o espaçamento entre letras e — se você autorizar com `grow_box: true` e o fundo em volta for da mesma cor — crescer a caixa. Se ainda assim não couber sem ficar feio (abaixo de 55% do corpo original), ele **falha aquela imagem de propósito** e diz `copy longa demais para a caixa`, em vez de entregar uma peça ilegível. Solução: encurte a copy, ou passe uma `box` maior na receita.

**JPEG e a garantia byte a byte.**
Salvar em JPEG recomprime a imagem inteira. Por causa de como o JPEG funciona (blocos de 8×8 pixels e requantização global), **mexer em 2% da imagem muda de leve quase 100% dos pixels do arquivo** — mesmo os que você não encostou. A garantia byte a byte simplesmente não existe em JPEG, e nenhuma ferramenta honesta pode prometer isso.

Por isso o master aqui é **PNG**, sempre. É lossless e a prova é aritmética. Se o cliente exigir JPEG, o editor entrega, mas: mede o drift com uma tolerância de 2 níveis por canal, escreve no relatório que aquilo é um **derivado com perdas** e **nunca** diz "verificado". Recomendação prática: entregue o PNG como master e gere o JPEG a partir dele só no final da cadeia, quando peso de arquivo importar. WebP sem perdas (`format: webp`) mantém a garantia e costuma ficar 25–40% menor que o PNG.

**O texto não foi encontrado.**
Rode `python -m s7editor.cli inspect inbox/sua-pasta` para ver o que o editor enxerga em cada peça: as caixas, os papéis e o texto lido. Se o `--de` não casar, use `--papel cta` ou `--caixa`.

**Texto sobre foto fica com um borrão retangular.**
Fundo fotográfico é o caso mais difícil: apagar letra ali significa reconstruir textura. Funciona bem na maioria das vezes, mas confira essas peças no relatório. Se ficar ruim, use `engine: ai` só naquela operação — o resultado continua sendo o seu original com apenas a caixa recomposta.

**O outpaint inventou uma pessoa / mudou a cor da campanha.**
O editor checa isso sozinho (rosto novo onde não havia, texto ilegível gerado, cor da faixa lateral fora do padrão) e, se reprovar duas vezes, cai automaticamente para o `pad` determinístico. Se o resultado ainda não agradar, rode `--mode pad` ou `--mode relayout` e siga.

**Erro de limite de requisição da OpenAI (rate limit).**
Baixe o paralelismo: `-j 2`.

**Qualquer outro erro.**
Rode de novo com `--verbose`. E antes de qualquer coisa: `python -m s7editor.cli doctor` diz exatamente o que está faltando — dependência, fonte, chave ou pasta.
