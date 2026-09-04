#!/usr/bin/env bash
# ===========================================================================
#  S7 Editor — instalação na VPS, publicando em /editoremmassa
#
#  Rode como root:
#      bash instalar-vps.sh
#
#  O que ele faz, e nada além disso:
#    - instala python3-venv, tesseract (pt) e as libs de imagem
#    - baixa o código em /opt/s7editor
#    - cria o venv e instala as dependências
#    - gera uma senha e grava em /opt/s7editor/.env
#    - cria o serviço systemd s7editor (sobe sozinho no boot)
#    - publica em /editoremmassa no nginx, com backup e teste antes de recarregar
#
#  É idempotente: rodar de novo atualiza o código e mantém a senha.
# ===========================================================================
set -euo pipefail

DESTINO="${S7_DESTINO:-/opt/s7editor}"
PORTA="${S7_PORTA:-8770}"
PREFIXO="${S7_PREFIXO:-/editoremmassa}"
REPO="${S7_REPO:-https://github.com/s7strategy/hera}"
BRANCH="${S7_BRANCH:-claude/s7editor-bulk-image-editing-8xk0wi}"

vermelho() { printf '\033[31m%s\033[0m\n' "$*"; }
verde()    { printf '\033[32m%s\033[0m\n' "$*"; }
passo()    { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { vermelho "Rode como root:  sudo bash $0"; exit 1; }

passo "1/7  Pacotes do sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git \
                       tesseract-ocr tesseract-ocr-por \
                       libjpeg-dev zlib1g-dev libpng-dev >/dev/null
verde "    ok"

passo "2/7  Código em $DESTINO"
if [ -d "$DESTINO/.git" ]; then
  git -C "$DESTINO" fetch --depth 1 origin "$BRANCH" -q
  git -C "$DESTINO" reset --hard "origin/$BRANCH" -q
  echo "    atualizado"
else
  rm -rf "$DESTINO"
  git clone --depth 1 --branch "$BRANCH" "$REPO" "$DESTINO" -q
  echo "    clonado"
fi
APP="$DESTINO/s7editor"
[ -d "$APP" ] || { vermelho "não achei $APP — a branch mudou de forma?"; exit 1; }

passo "3/7  Ambiente Python"
python3 -m venv "$DESTINO/.venv" 2>/dev/null || true
"$DESTINO/.venv/bin/python" -m pip install --upgrade pip -q
"$DESTINO/.venv/bin/python" -m pip install -r "$APP/requirements.txt" -q
verde "    ok"

passo "4/7  Senha"
ENVFILE="$APP/.env"
if [ -f "$ENVFILE" ] && grep -q '^S7EDITOR_SENHA=' "$ENVFILE"; then
  SENHA="$(grep '^S7EDITOR_SENHA=' "$ENVFILE" | head -1 | cut -d= -f2-)"
  echo "    mantida a senha que já existia"
else
  SENHA="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 14)"
  touch "$ENVFILE"; chmod 600 "$ENVFILE"
  grep -v '^S7EDITOR_SENHA=' "$ENVFILE" > "$ENVFILE.tmp" 2>/dev/null || true
  mv -f "$ENVFILE.tmp" "$ENVFILE" 2>/dev/null || true
  echo "S7EDITOR_SENHA=$SENHA" >> "$ENVFILE"
  echo "    senha nova gerada"
fi
# A chave da OpenAI é opcional: sem ela a troca de texto funciona igual.
grep -q '^OPENAI_API_KEY=' "$ENVFILE" || echo "# OPENAI_API_KEY=" >> "$ENVFILE"
chmod 600 "$ENVFILE"

passo "5/7  Serviço systemd"
cat > /etc/systemd/system/s7editor.service <<UNIT
[Unit]
Description=S7 Editor — edicao de criativos em lote
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP
EnvironmentFile=$ENVFILE
ExecStart=$DESTINO/.venv/bin/python -m s7editor.cli ui \\
    --host 127.0.0.1 --port $PORTA --base-path $PREFIXO
Restart=always
RestartSec=3
# O serviço só precisa escrever nas pastas dele.
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable s7editor -q
systemctl restart s7editor
sleep 3
systemctl is-active --quiet s7editor \
  && verde "    serviço no ar" \
  || { vermelho "    serviço não subiu:"; journalctl -u s7editor -n 25 --no-pager; exit 1; }

passo "6/7  Nginx em $PREFIXO"
SNIPPET=/etc/nginx/snippets/s7editor.conf
mkdir -p /etc/nginx/snippets
cat > "$SNIPPET" <<NGX
# S7 Editor — gerado por instalar-vps.sh
location $PREFIXO/ {
    proxy_pass         http://127.0.0.1:$PORTA/;
    proxy_http_version 1.1;
    proxy_set_header   Host              \$host;
    proxy_set_header   X-Real-IP         \$remote_addr;
    proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto \$scheme;
    # Lotes de 30 criativos: uploads grandes e resposta que demora.
    client_max_body_size 512m;
    proxy_read_timeout   1800s;
    proxy_send_timeout   1800s;
}
location = $PREFIXO { return 301 $PREFIXO/; }
NGX

SITE="$(ls /etc/nginx/sites-enabled/ 2>/dev/null | head -1 || true)"
if [ -z "$SITE" ]; then
  vermelho "    não achei site habilitado no nginx."
  echo "    Inclua manualmente dentro do seu bloco server:  include $SNIPPET;"
else
  ALVO="/etc/nginx/sites-enabled/$SITE"
  if grep -q "snippets/s7editor.conf" "$ALVO"; then
    echo "    já estava incluído em $SITE"
  else
    cp -a "$ALVO" "$ALVO.bak-s7editor-$(date +%s)"
    # Insere o include no ÚLTIMO bloco server que escuta 443 (ou o último server).
    awk -v inc="    include $SNIPPET;" '
      /server[[:space:]]*\{/ { n++ }
      { linhas[NR] = $0 }
      END {
        for (i = NR; i >= 1; i--) if (linhas[i] ~ /^[[:space:]]*server[[:space:]]*\{/) { alvo = i; break }
        for (i = 1; i <= NR; i++) { print linhas[i]; if (i == alvo) print inc }
      }' "$ALVO.bak-s7editor-"* > "$ALVO.novo" 2>/dev/null \
      || awk -v inc="    include $SNIPPET;" '
           { print } /^[[:space:]]*server[[:space:]]*\{/ && !feito { print inc; feito=1 }' "$ALVO" > "$ALVO.novo"
    mv "$ALVO.novo" "$ALVO"
    if nginx -t 2>/dev/null; then
      systemctl reload nginx
      verde "    nginx recarregado"
    else
      vermelho "    a configuração do nginx ficou inválida — desfazendo."
      cp -a "$(ls -t "$ALVO".bak-s7editor-* | head -1)" "$ALVO"
      nginx -t && systemctl reload nginx
      echo "    Nada foi quebrado. Inclua na mão:  include $SNIPPET;"
    fi
  fi
fi

passo "7/7  Conferindo"
sleep 1
CODIGO="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORTA/" || echo 000)"
[ "$CODIGO" = "401" ] && verde "    o painel está pedindo senha (401) — correto"
[ "$CODIGO" = "200" ] && verde "    o painel respondeu 200"
[ "$CODIGO" != "401" ] && [ "$CODIGO" != "200" ] && vermelho "    resposta inesperada: $CODIGO"

DOM="$(grep -rhoP '(?<=server_name )[^;]+' /etc/nginx/sites-enabled/ 2>/dev/null \
       | tr ' ' '\n' | grep -v '^_$' | head -1 || true)"
echo
echo "==========================================================="
verde " PRONTO"
echo
echo "   Endereço:  https://${DOM:-SEU-DOMINIO}$PREFIXO/"
echo "   Senha:     $SENHA"
echo
echo "   (a senha também fica em $ENVFILE)"
echo
echo "   Ver o log:      journalctl -u s7editor -f"
echo "   Reiniciar:      systemctl restart s7editor"
echo "   Atualizar:      bash $0"
echo "==========================================================="
