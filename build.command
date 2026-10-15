#!/bin/sh
# Finder double-click or: ./build.command [pdflatex]
set -eu
cd -- "$(dirname -- "$0")"
if [ -d /Library/TeX/texbin ]; then
    PATH="/Library/TeX/texbin:$PATH"
    export PATH
fi
case "${1:-platex}" in
    platex) config=latexmkrc ;;
    pdflatex) config=latexmkrc-pdflatex ;;
    *) printf 'Usage: %s [platex|pdflatex]\n' "$0" >&2; exit 2 ;;
esac
if ! command -v latexmk >/dev/null 2>&1; then
    printf 'latexmk was not found. Use an existing TeX Live / MacTeX environment.\n' >&2
    exit 1
fi
exec latexmk -norc -r "$config" main.tex
