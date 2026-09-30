#!/usr/bin/env bash
# PASSO 0 - decimacao.
#
# A estetica pede chapas metalicas GRANDES. Com 177.516 triangulos o flat shading
# vira superficie lisa e o visual se perde, entao reduzimos para a casa dos milhares
# ANTES de qualquer coisa. O alvo e 3.000-6.000 triangulos.
#
#   ./scripts/decimate.sh [RAZAO] [ERRO] [ENTRADA] [SAIDA]
#
#   RAZAO   fracao de triangulos a manter, 0..1   (default 0.025 -> ~4.4k tris)
#   ERRO    tolerancia de erro do meshoptimizer   (default 0.05)
#           o default do gltf-transform (0.0001) e apertado demais e trava a
#           simplificacao muito antes da razao pedida - por isso passamos alto.
set -euo pipefail
cd "$(dirname "$0")/.."

RATIO="${1:-0.025}"
ERROR="${2:-0.05}"
IN="${3:-boto.glb}"
OUT="${4:-boto_low.glb}"
TMP=".weld.tmp.glb"

# CLI instalado localmente (npm i -D @gltf-transform/cli). Chamar via `npx @gltf-transform/cli`
# sem instalar baixa o pacote inteiro - sharp junto - a cada execucao, o que levava minutos.
GLTF="./node_modules/.bin/gltf-transform"
if [ ! -x "$GLTF" ]; then
  echo "gltf-transform nao encontrado. rode: npm install" >&2
  exit 1
fi

echo "==> entrada"
node scripts/glbinfo.mjs "$IN"

# A malha vem sem indices (POSITION solto, 177k triangulos independentes).
# O meshoptimizer precisa de topologia costurada, entao soldamos primeiro -
# sem isso o simplify nao encontra arestas compartilhadas e nao remove nada.
echo
echo "==> weld"
"$GLTF" weld "$IN" "$TMP"

echo
echo "==> simplify (razao ${RATIO}, erro ${ERROR})"
"$GLTF" simplify "$TMP" "$OUT" --ratio "$RATIO" --error "$ERROR"

rm -f "$TMP"

echo
echo "==> saida"
node scripts/glbinfo.mjs "$OUT"
