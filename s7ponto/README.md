# S7 PONTO

Ponto digital da S7. A pessoa entra com usuário e senha, aperta **iniciar
turno**, escolhe a tarefa (se tiver mais de uma), e no fim do dia aperta
**fechar turno**. Ela vê quanto fez de horas e quanto vai receber; você vê
tudo de todo mundo, define o valor da hora de cada tarefa e importa as
planilhas antigas.

Feito para caber num celular e para ser óbvio: botão gigante, uma decisão
por tela, nada escondido em menu.

---

## Índice

1. [Ver funcionando agora (modo demonstração)](#1-ver-funcionando-agora)
2. [Ligar no Supabase da VPS](#2-ligar-no-supabase-da-vps)
3. [Publicar em s7strategy.com.br/s7ponto](#3-publicar-em-s7strategycombrs7ponto)
4. [Primeiro uso: tarefas e equipe](#4-primeiro-uso-tarefas-e-equipe)
5. [Importar as planilhas antigas](#5-importar-as-planilhas-antigas)
6. [Como funciona por dentro](#6-como-funciona-por-dentro)
7. [Segurança](#7-segurança)
8. [Problemas comuns](#8-problemas-comuns)

---

## 1. Ver funcionando agora

Não precisa instalar nada. Abra `index.html` num servidor local:

```bash
cd s7ponto
python3 -m http.server 8080
# depois abra http://localhost:8080
```

Enquanto o `js/config.js` estiver sem as chaves do Supabase, o app roda em
**modo demonstração**: três pessoas de mentira, quatro tarefas e uns três
meses de histórico, tudo guardado só no navegador do aparelho.

| Usuário | Senha | O que é |
|---|---|---|
| `admin` | `1234` | super admin — vê o painel inteiro |
| `maria` | `1234` | funcionária com 3 tarefas (tem que escolher ao iniciar) |
| `joao`  | `1234` | funcionário com 1 tarefa (inicia direto, sem perguntar) |

> Precisa abrir por `http://`, não por `file://` — o navegador bloqueia
> módulos JavaScript em arquivos locais.

Já configurou o Supabase mas quer rever a demonstração? Acrescente `?demo=1`
no fim da URL.

---

## 2. Ligar no Supabase da VPS

O projeto vive num **schema próprio do Postgres** chamado `s7ponto`. É o
"workspace separado": nada é criado em `public`, nada se mistura com o que
já existe no seu banco.

### 2.1 Rodar o schema

Abra o **SQL Editor** do Supabase Studio (logado como `postgres`), cole o
conteúdo inteiro de [`schema.sql`](schema.sql) e rode. Ele cria as tabelas,
as regras de acesso (RLS) e quatro tarefas de exemplo.

### 2.2 Expor o schema na API

O PostgREST só enxerga os schemas que estiverem na lista. No `.env` da sua
instalação do Supabase (normalmente `/opt/supabase/docker/.env` ou onde
estiver o `docker-compose.yml`), ajuste:

```dotenv
PGRST_DB_SCHEMAS=public,storage,graphql_public,s7ponto
GOTRUE_MAILER_AUTOCONFIRM=true
GOTRUE_DISABLE_SIGNUP=true
```

- **`PGRST_DB_SCHEMAS`** — sem isso a API responde *"schema does not exist"*.
- **`GOTRUE_MAILER_AUTOCONFIRM=true`** — os logins usam e-mail sintético
  (`maria@s7ponto.local`), que ninguém consegue confirmar por caixa de
  entrada. Sem esta linha, ninguém entra.
- **`GOTRUE_DISABLE_SIGNUP=true`** — ninguém se cadastra sozinho. As contas
  são criadas pelo painel do admin, que usa uma função do banco protegida por
  permissão. **Este app não depende do cadastro aberto** — pode deixar
  desligado com tranquilidade.

Reinicie os serviços:

```bash
cd /opt/supabase/docker      # ajuste para o seu caminho
docker compose up -d rest auth
```

### 2.3 Criar o primeiro admin

De volta ao SQL Editor, rode uma vez (trocando a senha):

```sql
select s7ponto._cria_usuario('admin', 'Administração S7', 'uma-senha-boa', 'admin');
```

### 2.4 Preencher o `js/config.js`

```js
SUPABASE_URL: 'https://supabase.s7strategy.com.br',   // sem barra no final
SUPABASE_ANON_KEY: 'eyJhbGciOi...',                   // a chave "anon", pública
```

Pegue as duas em **Settings → API** no Studio (ou no `.env`, como
`ANON_KEY`). A chave `anon` é pública por desenho — quem protege os dados é o
RLS. **Nunca** ponha aqui a `service_role`.

---

## 3. Publicar em s7strategy.com.br/s7ponto

### 3.1 Enviar os arquivos

Do seu computador, dentro da pasta `s7ponto/`:

```bash
VPS=usuario@ip-da-vps ./deploy.sh
```

O script confere a sintaxe, avisa se o `config.js` está vazio e sincroniza
tudo para `/var/www/s7ponto` na VPS.

Antes da primeira vez, instale sua chave SSH (é mais seguro e não pede senha
toda hora):

```bash
ssh-keygen -t ed25519          # se ainda não tiver
ssh-copy-id usuario@ip-da-vps
```

### 3.2 Configurar o nginx

Cole o conteúdo de [`nginx-s7ponto.conf`](nginx-s7ponto.conf) dentro do
`server { ... }` do site `s7strategy.com.br` e recarregue:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Pronto: **https://s7strategy.com.br/s7ponto/**

> Atualizar depois é só rodar o `./deploy.sh` de novo.

---

## 4. Primeiro uso: tarefas e equipe

Entre como admin e vá em **Painel**.

**1. Tarefas.** Crie cada atividade com o quanto vale a hora. O nome é o que
a equipe vê na hora de escolher — use algo curto: *Cozinha*, *Atendimento*,
*Produção*.

> O valor da hora é **congelado** no momento em que a pessoa começa o trecho.
> Se você reajustar o preço mês que vem, o que já foi trabalhado continua
> valendo o preço de hoje. O passado nunca é reescrito.

**2. Equipe.** Cadastre cada pessoa com nome, usuário e uma senha inicial.
Depois toque nela → **Liberar tarefas** e marque o que ela pode fazer.

- Marcou **uma** tarefa → ela aperta *Iniciar turno* e já começa, sem
  perguntar nada.
- Marcou **duas ou mais** → aparece a tela de escolher a tarefa, e o botão
  *Troquei de tarefa* fica disponível durante o turno.

**3. Turnos.** Aqui você conserta o mundo real: quem esqueceu de bater,
quem esqueceu de fechar, quem trabalhou num dia que não registrou. Dá para
lançar turno na mão e corrigir horário.

**4. Relatórios.** Custo de mão de obra do mês, quebra por pessoa e por
tarefa, e o CSV para levar ao contador.

---

## 5. Importar as planilhas antigas

**Painel → Importar.** Aceita `.xlsx`, `.xls` e `.csv`. São quatro passos:

1. **Arquivo** — arraste ou escolha.
2. **Colunas** — o sistema adivinha pelo cabeçalho; você confere. Precisa de
   *pessoa* e *data*, mais *entrada/saída* **ou** um total de horas do dia.
3. **Nomes** — cada nome da planilha aponta para uma pessoa cadastrada, ou
   você manda criar o acesso na hora. O mesmo para as tarefas.
4. **Conferir** — mostra quantos turnos entram, o total de horas e de
   dinheiro, e lista as linhas que não deu para ler. Só então importa.

O formato ideal está em [`exemplo-planilha.csv`](exemplo-planilha.csv):

```csv
Funcionário;Data;Entrada;Saída;Tarefa
Maria Aparecida;01/07/2026;08:00;17:00;Cozinha
```

O leitor é tolerante: entende `12/08/2026`, `2026-08-12`, `12-08-26` e o
número serial do Excel; entende `8:30`, `08h30`, `0830` e `8`. Turno que
atravessa a meia-noite é reconhecido sozinho.

Os turnos importados ficam marcados como *importado* e podem ser apagados um
a um na aba Turnos.

---

## 6. Como funciona por dentro

### Turno e trecho

Um **turno** vai da batida de entrada até a de saída. Dentro dele existem
**trechos** — um por tarefa. Trocar de tarefa fecha o trecho atual e abre o
próximo; cada trecho guarda o valor da hora daquele momento.

```
Turno de Maria — 08:00 → 17:00
├── trecho 1  08:00 → 12:00  Cozinha    R$ 22/h  → 4h00  R$ 88,00
└── trecho 2  12:00 → 17:00  Produção   R$ 25/h  → 5h00  R$ 125,00
                                              total: 9h00  R$ 213,00
```

O banco garante, com índice único, que ninguém tenha **dois turnos abertos**
ao mesmo tempo, nem **dois trechos abertos** no mesmo turno.

### Arquivos

```
s7ponto/
├── index.html              a página
├── app.css                 todo o visual
├── schema.sql              o banco: tabelas, RLS e funções
├── deploy.sh               publica na VPS
├── nginx-s7ponto.conf      bloco do nginx
├── verificar.sh            confere a sintaxe dos módulos
├── exemplo-planilha.csv    modelo de importação
└── js/
    ├── config.js           ⚙️ o ÚNICO arquivo que você edita
    ├── app.js              casca, navegação, login/logout
    ├── store.js            escolhe Supabase ou demonstração
    ├── store-supabase.js   conversa com o banco
    ├── store-demo.js       dados de mentira no navegador
    ├── util.js             datas, dinheiro, horas, leitura de planilha
    ├── metricas.js         todas as contas
    ├── charts.js           gráficos em SVG, sem biblioteca
    ├── ui.js               botões, folhas, avisos
    ├── view-login.js       tela de entrar
    ├── view-ponto.js       iniciar / trocar / fechar turno
    ├── view-numeros.js     "Meus números"
    ├── view-admin.js       painel do super admin
    └── importador.js       importação de planilhas
```

Sem build, sem `npm install`, sem framework: são arquivos estáticos que o
navegador lê direto. As duas únicas coisas que vêm de fora são a fonte do
Google Fonts e, só quando você abre um `.xlsx`, a biblioteca de leitura de
planilha.

### As cores dos gráficos

A paleta categórica foi escolhida rodando um validador de daltonismo e
contraste sobre o fundo escuro do app: nenhum par de cores vizinhas fica
indistinguível para quem tem protanopia ou deuteranopia, e toda cor tem pelo
menos 3:1 de contraste com o fundo. Além disso nenhum gráfico depende só de
cor — todos têm o nome escrito do lado.

---

## 7. Segurança

- **A senha da VPS nunca entra neste repositório.** Use chave SSH.
- A chave `anon` do Supabase pode ficar no `config.js` — ela é pública por
  desenho. Já a `service_role` **nunca** pode aparecer no navegador.
- Quem manda de verdade é o **RLS**, dentro do Postgres:
  - funcionário lê e escreve **só os próprios turnos**;
  - só admin cria pessoas, mexe em tarefas, corrige e apaga turnos;
  - as funções que criam usuário e trocam senha checam permissão antes de
    fazer qualquer coisa.
- O app é `noindex`: não aparece no Google.
- Se alguma senha vazar, troque no painel (**Equipe → a pessoa → Definir
  nova senha**) — leva dez segundos.

---

## 8. Problemas comuns

| O que aparece | O que é | Como resolver |
|---|---|---|
| *"O schema s7ponto não está exposto na API"* | falta o schema na lista do PostgREST | passo 2.2, e reinicie o container `rest` |
| *"O Supabase está exigindo confirmação de e-mail"* | falta o autoconfirm | `GOTRUE_MAILER_AUTOCONFIRM=true` e reinicie o `auth` |
| *"Usuário ou senha incorretos"* mesmo estando certo | o usuário foi criado fora do padrão | recrie com `select s7ponto._cria_usuario(...)` |
| *"Este acesso ainda não foi liberado"* | existe no `auth` mas não tem perfil | cadastre pela aba Equipe, ou insira em `s7ponto.profiles` |
| O botão de iniciar turno está apagado | a pessoa não tem tarefa liberada | Painel → Equipe → a pessoa → Liberar tarefas |
| *"Já existe um turno aberto para esta pessoa"* | esqueceram de fechar ontem | Painel → Turnos → toque no turno → ajuste a saída |
| Tela em branco | erro de JavaScript | abra o console do navegador (F12) e rode `./verificar.sh` |
| Mudei o código e não muda na tela | cache | Ctrl+Shift+R; o nginx já manda o HTML sem cache |

---

Dúvida sobre alguma conta que apareceu na tela? Todo número vem de
`js/metricas.js` — está tudo em um arquivo só, comentado, em português.
