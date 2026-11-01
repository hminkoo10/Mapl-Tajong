#!/usr/bin/env bash
# 이미 GitHub Release(desktop-vX.Y.Z / android-vX.Y.Z)가 나온 release/* 브랜치를 지운다.
# 릴리스가 없는(아직 배포 중이거나 실패한) 브랜치는 건드리지 않는다.
set -euo pipefail
repo="${GITHUB_REPOSITORY:?}"
# 지울 브랜치가 하나도 없으면 grep 이 1 로 끝나므로 성공으로 친다 (pipefail 때문에 작업 전체가 실패하지 않게)
gh api "repos/$repo/branches?per_page=100" --paginate --jq '.[].name' \
  | { grep -E '^release/(desktop|android)-v[0-9]+(\.[0-9]+){2,3}$' || true; } \
  | while read -r branch; do
      tag="${branch#release/}"
      if gh release view "$tag" -R "$repo" > /dev/null 2>&1; then
        gh api -X DELETE "repos/$repo/git/refs/heads/$branch" > /dev/null
        echo "지움: $branch (릴리스 $tag 있음)"
      else
        echo "남김: $branch (릴리스 없음)"
      fi
    done
