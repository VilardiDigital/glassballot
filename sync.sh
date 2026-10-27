#!/bin/sh
# Commit-and-publish helper: rebase on the nightly job's commits, rebuilding generated files if they clash.
set -e
cd "$(dirname "$0")"
if ! git pull -q --rebase; then
  git checkout --theirs dist site/glassballot.html site/region.json 2>/dev/null || true
  python -m pipeline.refresh --offline >/dev/null
  git add -A
  GIT_EDITOR=true git rebase --continue >/dev/null
fi
python -m pipeline.refresh --offline >/dev/null
if ! git diff --quiet; then git add -A; git commit -qm "Rebuild" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01SbucN7eT2yuPfmwq5x7Te8"; fi
git push -q
git status -sb | head -1
