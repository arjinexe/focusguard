#!/usr/bin/env bash
# FocusGuard.ai v5.0 — Setup
# Usage: chmod +x install.sh && ./install.sh

set -e
GREEN="\033[92m"; RED="\033[91m"; AMBER="\033[93m"; CYAN="\033[96m"; BOLD="\033[1m"; R="\033[0m"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$DIR"

echo -e "\n${BOLD}${CYAN}  FocusGuard.ai v5.0 — Setup${R}\n"

# Python
PYTHON=""
for cmd in python3 python; do
  $cmd --version &>/dev/null && { PYTHON=$cmd; break; }
done
[ -z "$PYTHON" ] && { echo -e "${RED}[ERROR] Python 3 not found.${R}"; exit 1; }
echo -e "${GREEN}[OK]${R} $($PYTHON --version)"

VER=$($PYTHON -c "import sys; print(sys.version_info.major*10+sys.version_info.minor)")
[ "$VER" -lt 39 ] && { echo -e "${RED}[ERROR] Python 3.9+ required.${R}"; exit 1; }

# tkinter
$PYTHON -c "import tkinter" 2>/dev/null \
  && echo -e "${GREEN}[OK]${R} tkinter" \
  || { echo -e "${AMBER}[WARN] tkinter missing — install python3-tk / brew install python-tk${R}"; }

# pip + deps
echo -e "\n${BOLD}Installing dependencies...${R}"
$PYTHON -m pip install --upgrade pip --quiet
$PYTHON -m pip install -r requirements.txt --quiet \
  && echo -e "${GREEN}[OK]${R} All packages installed" \
  || { echo -e "${RED}[ERROR] pip install failed. Run: pip install -r requirements.txt${R}"; exit 1; }

# macOS extras
[[ "$OSTYPE" == "darwin"* ]] && $PYTHON -m pip install pyobjc-framework-Quartz --quiet 2>/dev/null && echo -e "${GREEN}[OK]${R} macOS extras"

# Ollama (optional)
if command -v ollama &>/dev/null; then
    echo -e "${GREEN}[OK]${R} Ollama found"
    ollama list 2>/dev/null | grep -q "llava" \
      && echo -e "${GREEN}[OK]${R} LLaVA model ready" \
      || { echo -e "${AMBER}[INFO]${R} Pulling LLaVA..."; ollama pull llava || true; }
else
    echo -e "${AMBER}[SKIP]${R} Ollama not found — OCR+CV mode. Better: https://ollama.com"
fi

echo -e "\n${BOLD}${GREEN}  Setup complete!${R}"
echo -e "  Run: ${BOLD}$PYTHON -m focusguard${R}"
echo -e "  Run: ${BOLD}$PYTHON -m focusguard --lang tr${R}\n"

read -rp "Launch FocusGuard now? (y/N): " GO
[[ "$GO" =~ ^[Yy]$ ]] && nohup $PYTHON -m focusguard &>/dev/null & echo -e "${GREEN}Launched!${R}"
