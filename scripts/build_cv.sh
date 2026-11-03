#!/usr/bin/env bash
# Compile cv/cv.tex and cv/tailored/*.tex to cv/build/*.pdf and check each is exactly one page.
# Usage: scripts/build_cv.sh [file.tex ...]
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p cv/build
files=("$@")
[ ${#files[@]} -eq 0 ] && files=(cv/cv.tex cv/tailored/*.tex)
fail=0
for f in "${files[@]}"; do
  [ -f "$f" ] || continue
  name=$(basename "$f" .tex)
  if ! pdflatex -interaction=nonstopmode -halt-on-error -output-directory cv/build -jobname "$name" "$f" >/dev/null 2>&1; then
    echo "FAIL  $f (compile error, see cv/build/$name.log)"; fail=1; continue
  fi
  pages=$(pdfinfo "cv/build/$name.pdf" | awk '/^Pages:/{print $2}')
  if [ "$pages" = "1" ]; then echo "OK    $f (1 page)"; else echo "FAIL  $f ($pages pages)"; fail=1; fi
done
rm -f cv/build/*.aux cv/build/*.out
exit $fail
