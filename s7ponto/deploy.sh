#!/usr/bin/env bash
# ============================================================================
#  S7 PONTO — publica o app na VPS.
#
#  Rode do SEU computador, de dentro da pasta s7ponto/:
#
#      VPS=usuario@ip.da.sua.vps ./deploy.sh
#
#  Ou, se você já configurou o atalho no ~/.ssh/config:
#
#      VPS=s7 ./deploy.sh
#
#  Nunca coloque senha aqui. Use chave SSH:
#      ssh-keygen -t ed25519            # uma vez, no seu computador
#      ssh-copy-id usuario@ip.da.vps    # uma vez, para instalar a chave
# ============================================================================
set -euo pipefail

VPS="${VPS:-}"
DESTINO="${DESTINO:-/var/www/s7ponto}"

if [ -z "$VPS" ]; then
  echo "Falta dizer para onde enviar."
  echo "  Exemplo: VPS=root@203.0.113.10 ./deploy.sh"
  exit 1
fi

cd "$(dirname "$0")"

# 1. o config precisa estar preenchido, senão sobe em modo demonstração
if grep -q "SUPABASE_URL: ''" js/config.js; then
  echo "⚠️  js/config.js ainda está vazio — o app vai subir em MODO DEMONSTRAÇÃO."
  printf "    Continuar mesmo assim? [s/N] "
  read -r resposta
  [ "$resposta" = "s" ] || [ "$resposta" = "S" ] || exit 1
fi

# 2. sintaxe dos módulos
./verificar.sh >/dev/null || { echo "❌ Tem erro de sintaxe. Rode ./verificar.sh"; exit 1; }

# 3. cria a pasta no servidor
ssh "$VPS" "mkdir -p '$DESTINO'"

# 4. envia só o que o navegador precisa
rsync -az --delete --info=stats1 \
  --exclude '.git' --exclude 'deploy.sh' --exclude 'verificar.sh' \
  --exclude 'schema.sql' --exclude 'nginx-s7ponto.conf' --exclude 'README.md' \
  ./ "$VPS:$DESTINO/"

# 5. permissões de leitura para o nginx
ssh "$VPS" "chmod -R a+rX '$DESTINO'"

echo
echo "✅ Publicado em $DESTINO"
echo "   Confira em: https://s7strategy.com.br/s7ponto/"
echo
echo "   Primeira vez? Falta ainda colar o bloco do nginx-s7ponto.conf"
echo "   na configuração do site e recarregar o nginx."
