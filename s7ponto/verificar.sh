#!/usr/bin/env bash
# Confere a sintaxe de todos os módulos do S7 PONTO.
# Precisa ser .mjs para o node checar como módulo — como .js ele passa batido
# em erros de template aninhado.
set -u
cd "$(dirname "$0")"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
falhas=0
for f in js/*.js; do
  cp "$f" "$tmp/$(basename "${f%.js}").mjs"
done
for m in "$tmp"/*.mjs; do
  nome="js/$(basename "${m%.mjs}").js"
  if node --check "$m" >/dev/null 2>&1; then
    echo "ok   $nome"
  else
    echo "ERRO $nome"
    node --check "$m" 2>&1 | head -5
    falhas=$((falhas + 1))
  fi
done
echo
[ "$falhas" -eq 0 ] && echo "Tudo certo." || echo "$falhas arquivo(s) com problema."
exit "$falhas"
