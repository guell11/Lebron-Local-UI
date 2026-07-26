#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v git >/dev/null 2>&1; then
  echo "Git não encontrado. Instale o Git e tente novamente."
  exit 1
fi
if [ -d ../Lebron/.git ]; then
  git -C ../Lebron pull --ff-only
else
  git clone https://github.com/guell11/Lebron.git ../Lebron
fi
echo "Repositório disponível em: $(cd ../Lebron && pwd)"
