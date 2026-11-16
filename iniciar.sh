#!/usr/bin/env bash
set -e
cd -- "$(dirname -- "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Instale Python 3.10 ou superior antes de iniciar."
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Este programa requer Python 3.10 ou superior. Confira com: python3 --version"
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || { echo "Não foi possível criar o ambiente. No Ubuntu/Debian, instale python3-venv e tente novamente."; exit 1; }
fi
if ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "O ambiente .venv usa um Python antigo. Renomeie .venv e execute novamente com Python 3.10 ou superior."
  exit 1
fi
.venv/bin/python -m pip install -r requirements.txt
exec .venv/bin/python app.py "$@"
