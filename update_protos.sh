#!/usr/bin/env bash
# Refreshes the game's .proto files.
#
#   ./update_protos.sh <game dir>           from the game's own binaries (the default source)
#   ./update_protos.sh --gametracking [ref] from SteamDatabase/GameTracking-CS2 (Protobufs/),
#                                           master or a commit, as a cross-check
#
# <game dir> is a CS2 install or depot download: the directory holding game/. The
# descriptors protoc compiled into game/csgo/bin/linuxsteamrt64/libserver.so,
# game/bin/linuxsteamrt64/libengine2.so and libnetworksystem.so are written out as .proto
# text by devtools/dump_protos.py, in the layout GameTracking-CS2 publishes (identical on
# 14196 and 14197), so the SDK no longer waits for anyone else's dump.
#
# Every tracked .proto outside thirdparty/ whose file name exists in the dump is
# replaced. The dump keeps Valve's own field options (boxed_type, synthetic_default,
# additional_includes) that stock protoc doesn't know; they are stripped the same way
# the SDK always has. SDK-side edits that must survive the refresh are reapplied at the
# end. Review with git diff, build with ./local-ci.sh, then commit as
# "cs2: Update protobufs".

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

REPO=SteamDatabase/GameTracking-CS2
BINARIES=(
	game/csgo/bin/linuxsteamrt64/libserver.so
	game/bin/linuxsteamrt64/libengine2.so
	game/bin/linuxsteamrt64/libnetworksystem.so
)

usage() { sed -n '4,6p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
[[ $# -ge 1 ]] || usage

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

dump="$tmp/dump"
mkdir -p "$dump"
if [[ "$1" == "--gametracking" ]]; then
	command -v gh &> /dev/null || { echo "gh is required" >&2; exit 1; }
	sha=$(gh api "repos/$REPO/commits/${2:-master}" --jq .sha)
	subject=$(gh api "repos/$REPO/commits/$sha" --jq '.commit.message | split("\n")[0] | split(" | ")[0]')
	source="GameTracking-CS2 ${sha:0:9} ($subject)"
	for name in $(gh api "repos/$REPO/contents/Protobufs?ref=$sha" --jq '.[] | select(.type == "file") | .name'); do
		curl -sfL "https://raw.githubusercontent.com/$REPO/$sha/Protobufs/$name" -o "$dump/$name"
	done
else
	game=$1
	paths=()
	for bin in "${BINARIES[@]}"; do
		[[ -f "$game/$bin" ]] || { echo "$game/$bin not found" >&2; exit 1; }
		paths+=("$game/$bin")
	done
	python3 -I devtools/dump_protos.py -o "$dump" "${paths[@]}" > /dev/null
	build=$(sed -n 's/^PatchVersion=//p' "$game/game/csgo/steam.inf" 2>/dev/null | tr -d '\r')
	source="the binaries of $game${build:+ (CS2 $build)}"
fi

updated=0
missing=()
while read -r path; do
	name=$(basename "$path")
	if [[ ! -f "$dump/$name" ]]; then
		missing+=("$path")
		continue
	fi
	normalize "$dump/$name" > "$tmp/$name.norm"
	local_edits "$path" "$tmp/$name.norm"
	if ! cmp -s "$tmp/$name.norm" "$path"; then
		cp "$tmp/$name.norm" "$path"
		updated=$((updated + 1))
	fi
done < <(git ls-files '*.proto' | grep -v '^thirdparty/')

echo "$source: $updated file(s) changed"
for path in "${missing[@]}"; do
	echo "  not in the dump, left as is: $path"
done
git --no-pager diff --stat -- '*.proto'
