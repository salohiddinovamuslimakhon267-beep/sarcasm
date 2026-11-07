#!/usr/bin/env bash
set -euo pipefail
# Requires valid GitHub authentication with repository contents write access.
# The user has explicitly authorized publishing the prepared dataset to this repo.
repo='salohiddinovamuslimakhon267-beep/sarcasm'
tag=${2:-dataset-v1}
assets_dir=${1:?Usage: bash scripts/publish_dataset_release.sh /absolute/path/to/work/delivery}
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd -- "$script_dir/.." && pwd)
assets_dir=$(cd -- "$assets_dir" && pwd)
dataset_archive=sarcasm_dataset_prepared_v1_PRIVATE.zip
if test -s "$assets_dir/sarcasm_dataset_prepared_v1_1_PRIVATE.zip"; then
  dataset_archive=sarcasm_dataset_prepared_v1_1_PRIVATE.zip
  tag=${2:-dataset-v1.1}
fi
for file in "$dataset_archive" sarcasm_pipeline_code.zip; do
  test -s "$assets_dir/$file" || { echo "Missing asset: $file" >&2; exit 1; }
done
# Authenticate before any remote mutation; never print credential contents.
gh api user --jq .login >/dev/null
gh api "repos/$repo" --jq '.permissions.push' | python -c 'import sys; sys.exit(0 if sys.stdin.read().strip()=="true" else "Repository write access is required")'
staging=$(mktemp -d)
trap 'rm -rf -- "$staging"' EXIT
cp -- "$assets_dir/$dataset_archive" "$staging/sarcasm_dataset_prepared_v1.zip"
cp -- "$assets_dir/sarcasm_pipeline_code.zip" "$staging/sarcasm_pipeline_code.zip"
cp -- "$assets_dir/BOSHLASH_UZ.txt" "$staging/BOSHLASH_UZ.txt"
python - "$staging" <<'PY'
import hashlib, pathlib, sys
p=pathlib.Path(sys.argv[1])
lines=[hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.name for x in sorted(p.iterdir()) if x.is_file()]
(p/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
PY
cat > "$staging/notes.md" <<'EOF'
Prepared Uzbek irony/sarcasm dataset. See the included versioned build report for exact totals.

- Base v1: 652,132 original nonempty occurrences; 155,455 unique normalized texts.
- v1.1 additionally includes 124 screenshot-workbook comments (123 new unique texts):
  26 irony, 15 sarcasm, 59 non-ironic, 24 uncertain; initial single-annotation labels.
  Updated registry: 652,256 occurrences and 155,578 unique texts.
  Original images were not supplied; context summaries and post groups are retained.
- Original source rows and label histories retained in SQLite.
- 49,308 automatic non-detections separated from human-confirmed negatives.
- 106 historical binary label disagreements queued for review.
- Legacy provisional video-grouped train/validation/test: 618/159/197.
- 2,792 unique tasks in separate blinded A/B annotation workbooks.
- Synthetic data is train-only. Final reserved test was not evaluated.

IMPORTANT: this is a preparation release, not an independently human-verified gold
benchmark. Existing legacy labels need human review. Video titles and reply-parent
context were not recovered; no missing context was fabricated. Text may contain
personal information originally present in public comments. No redistribution
license for source comments is asserted by this release.

Download sarcasm_dataset_prepared_v1.zip for the data and annotation files.
Download sarcasm_pipeline_code.zip for the reproducible pipeline.
See BOSHLASH_UZ.txt for Uzbek instructions and SHA256SUMS.txt for checksums.
EOF
# Push the prepared branch without overwriting another branch.
git -C "$repo_dir" -c credential.helper= -c 'credential.https://github.com.helper=!gh auth git-credential' push --set-upstream origin HEAD:refs/heads/dataset-preparation
if ! gh release view "$tag" --repo "$repo" >/dev/null 2>&1; then
  gh release create "$tag" --repo "$repo" --target dataset-preparation \
    --title 'Uzbek sarcasm dataset — preparation v1' --notes-file "$staging/notes.md"
fi
gh release upload "$tag" "$staging/sarcasm_dataset_prepared_v1.zip" \
  "$staging/sarcasm_pipeline_code.zip" "$staging/BOSHLASH_UZ.txt" \
  "$staging/SHA256SUMS.txt" --repo "$repo" --clobber
gh release view "$tag" --repo "$repo" --json url,assets --jq '{url: .url, files: [.assets[] | {name, url, size}]}'
