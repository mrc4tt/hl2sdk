#!/usr/bin/env bash
# Refreshes the game's .proto files from SteamDatabase/GameTracking-CS2 (Protobufs/),
# the same source the upstream "cs2: Update protobufs" commits are taken from.
#
#   ./update_protos.sh             latest GameTracking-CS2 master
#   ./update_protos.sh <ref>       a GameTracking-CS2 commit, e.g. the one for a build
#
# Every tracked .proto outside thirdparty/ whose file name exists in the dump is
# replaced. GameTracking's dump keeps Valve's own field options (boxed_type,
# synthetic_default, additional_includes) that stock protoc doesn't know; they are
# stripped the same way the SDK always has. SDK-side edits that must survive the
# refresh are reapplied at the end. Review with git diff, build with ./local-ci.sh,
# then commit as "cs2: Update protobufs".

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

REPO=SteamDatabase/GameTracking-CS2
REF="${1:-master}"

command -v gh &> /dev/null || { echo "gh is required" >&2; exit 1; }

sha=$(gh api "repos/$REPO/commits/$REF" --jq .sha)
subject=$(gh api "repos/$REPO/commits/$sha" --jq '.commit.message | split("\n")[0] | split(" | ")[0]')
available=$(gh api "repos/$REPO/contents/Protobufs?ref=$sha" --jq '.[].name')

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

normalize() {
	python3 -I - "$1" <<'EOF'
import re, sys

text = open(sys.argv[1], encoding='utf-8').read().replace('\r\n', '\n')
# descriptor.proto goes with Valve's options, unless the file extends it itself
valve_options = re.search(r'additional_includes|boxed_type|synthetic_default', text) is not None
extends = re.search(r'^\s*extend\s+\.?google\.protobuf\.', text, re.M) is not None
keep_descriptor = extends or not valve_options
out = []
for line in text.split('\n'):
	if re.match(r'\s*option\s+additional_includes\s*=', line):
		continue
	if not keep_descriptor and re.match(r'\s*import\s+"google/protobuf/descriptor\.proto"\s*;', line):
		continue
	line = re.sub(r',?\s*(boxed_type|synthetic_default)\s*=\s*"[^"]*"', '', line)
	line = re.sub(r'\[\s*,\s*', '[', line)
	line = re.sub(r'\s*\[\s*\]', '', line)
	out.append(line)
text = re.sub(r'\n{3,}', '\n\n', '\n'.join(out)).lstrip('\n')
sys.stdout.write(text)
EOF
}

# SDK-side edits kept across refreshes
local_edits() {
	case "$1" in
	# the SDK reserves extension 201 (alliedmodders/s2sdk#176)
	game/shared/usermessages.proto) sed -i 's/^\(\s*extensions 100 to \)200;/\1201;/' "$2" ;;
	esac
}

updated=0
missing=()
while read -r path; do
	name=$(basename "$path")
	if ! grep -qx "$name" <<< "$available"; then
		missing+=("$path")
		continue
	fi
	curl -sfL "https://raw.githubusercontent.com/$REPO/$sha/Protobufs/$name" -o "$tmp/$name"
	normalize "$tmp/$name" > "$tmp/$name.norm"
	local_edits "$path" "$tmp/$name.norm"
	if ! cmp -s "$tmp/$name.norm" "$path"; then
		cp "$tmp/$name.norm" "$path"
		updated=$((updated + 1))
	fi
done < <(git ls-files '*.proto' | grep -v '^thirdparty/')

echo "GameTracking-CS2 ${sha:0:9} ($subject): $updated file(s) changed"
for path in "${missing[@]}"; do
	echo "  not in the dump, left as is: $path"
done
git --no-pager diff --stat -- '*.proto'
