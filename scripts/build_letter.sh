#!/usr/bin/env bash
# Compile applications/<folder>/cover_letter.tex to cover_letter.pdf (same folder) and check it's one page.
# Usage: scripts/build_letter.sh applications/<company>-<role>    (or no argument: every application folder)
set -uo pipefail
cd "$(dirname "$0")/.."
dirs=("$@")
[ ${#dirs[@]} -eq 0 ] && dirs=(applications/*/)
fail=0
for d in "${dirs[@]}"; do
  f="${d%/}/cover_letter.tex"
  [ -f "$f" ] || continue
  if grep -q "%% FILL" "$f"; then echo "TODO  $f still has %% FILL %% placeholders"; fail=1; continue; fi
  if ! pdflatex -interaction=nonstopmode -halt-on-error -output-directory "${d%/}" "$f" >/dev/null 2>&1; then
    echo "FAIL  $f (compile error, see ${d%/}/cover_letter.log)"; fail=1; continue
  fi
  pages=$(pdfinfo "${d%/}/cover_letter.pdf" | awk '/^Pages:/{print $2}')
  rm -f "${d%/}/cover_letter.aux" "${d%/}/cover_letter.out"
  if [ "$pages" = "1" ]; then echo "OK    ${d%/}/cover_letter.pdf (1 page)"; else echo "FAIL  $f ($pages pages)"; fail=1; fi
done
exit $fail
