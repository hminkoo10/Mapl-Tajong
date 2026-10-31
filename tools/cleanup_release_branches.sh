#!/usr/bin/env bash
# 이미 GitHub Release(desktop-vX.Y.Z / android-vX.Y.Z)가 나온 release/* 브랜치를 지운다.
# 릴리스가 없는(아직 배포 중이거나 실패한) 브랜치는 건드리지 않는다.
set -euo pipefail
repo="${GITHUB_REPOSITORY:?}"
gh api "repos/$repo/branches?per_page=100" --paginate --jq '.[].name' \
  | grep -E '^release/(desktop|android)-v[0-9]+(\.[0-9]+){2,3}$' \
  | while read -r branch; do
      tag="${branch#release/}"
      if gh release view "$tag" -R "$repo" > /dev/null 2>&1; then
        gh api -X DELETE "repos/$repo/git/refs/heads/$branch" > /dev/null
        echo "지움: $branch (릴리스 $tag 있음)"
      else
        echo "남김: $branch (릴리스 없음)"
      fi
    done
