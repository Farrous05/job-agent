#!/usr/bin/env bash
# Show what the suggested CV edits (branch cv-edits) would change in cv/cv.tex.
#   scripts/cv_diff.sh          tracked-changes PDF (red = removed, blue = added), opened for you
#   scripts/cv_diff.sh --text   coloured word-by-word diff in the terminal
# Merge when happy:  git merge cv-edits && git push
set -euo pipefail
cd "$(dirname "$0")/.."
branch="${CV_BRANCH:-cv-edits}"
if ! git rev-parse --verify -q "$branch" >/dev/null; then
  if git rev-parse --verify -q "origin/$branch" >/dev/null; then branch="origin/$branch"
  else echo "No cv-edits branch yet: there are no suggested CV changes."; exit 0; fi
fi
if git diff --quiet HEAD "$branch" -- cv/cv.tex; then
  echo "No differences: cv-edits has nothing your current cv/cv.tex doesn't already have."; exit 0
fi
echo "Changed lines: $(git diff --numstat HEAD "$branch" -- cv/cv.tex | awk '{print "+"$1" / -"$2}')"
if [ "${1:-}" = "--text" ] || ! command -v latexdiff >/dev/null || ! command -v pdflatex >/dev/null; then
  command -v latexdiff >/dev/null || echo "(latexdiff not installed, so showing a text diff. MacTeX includes it.)"
  git --no-pager diff --color --word-diff HEAD "$branch" -- cv/cv.tex
  exit 0
fi
tmp=$(mktemp -d)
git show "HEAD:cv/cv.tex" > "$tmp/old.tex"
git show "$branch:cv/cv.tex" > "$tmp/new.tex"
latexdiff "$tmp/old.tex" "$tmp/new.tex" > "$tmp/cv-changes.tex" 2>/dev/null
mkdir -p cv/build
if pdflatex -interaction=nonstopmode -halt-on-error -output-directory "$tmp" "$tmp/cv-changes.tex" >/dev/null 2>&1; then
  cp "$tmp/cv-changes.pdf" cv/build/cv-changes.pdf
  echo "Tracked changes: cv/build/cv-changes.pdf  (red = removed, blue = added)"
  [ "$(uname)" = "Darwin" ] && [ -z "${NO_OPEN:-}" ] && open cv/build/cv-changes.pdf || true
else
  echo "Couldn't build the tracked-changes PDF (a LaTeX package may be missing). Text diff instead:"
  git --no-pager diff --color --word-diff HEAD "$branch" -- cv/cv.tex
fi
echo "Happy with it?  git merge cv-edits && git push"
