#!/usr/bin/env bash
# The Windows half of CheckScript, cross-compiled from Linux with clang-cl + lld-link
# against an MSVC CRT/SDK splatted by xwin (https://github.com/Jake-Shadle/xwin).
#
# Like CheckScript it compiles every header on its own, the sources plugins compile
# themselves and the template instantiations in tests/, links them into a DLL against
# the libraries hl2sdk-manifests gives cs2 plugins (so a declaration the libraries
# don't export fails the link), and links the tests/run programs. The programs are
# not run: they need the game's tier0.dll.
#
#   .github/local/check-windows.sh [output dir]
#
# XWIN_ROOT (default ~/.xwin) and LLVM_BIN (default: the newest /usr/lib/llvm-*/bin
# with clang-cl) pick the CRT/SDK and the toolchain. The MSVC STL needs clang >= 19.

set -euo pipefail

SDK=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUT=$(mkdir -p "${1:-$SDK/build/check-win64}" && cd "${1:-$SDK/build/check-win64}" && pwd)
XWIN_ROOT=${XWIN_ROOT:-$HOME/.xwin}

if [ -z "${LLVM_BIN:-}" ]; then
	LLVM_BIN=$(find /usr/lib -mindepth 2 -maxdepth 2 -type d -path '/usr/lib/llvm-*/bin' | sort -V | tac |
		while read -r dir; do [ -x "$dir/clang-cl" ] && [ -x "$dir/lld-link" ] && { echo "$dir"; break; }; done)
fi
[ -x "${LLVM_BIN:-}/clang-cl" ] || { echo "No clang-cl found, set LLVM_BIN" >&2; exit 1; }
[ -d "$XWIN_ROOT/crt/include" ] || { echo "No MSVC CRT at $XWIN_ROOT/crt, run xwin splat or set XWIN_ROOT" >&2; exit 1; }
echo "clang-cl: $("$LLVM_BIN/clang-cl" --version | head -1)"
echo "xwin:     $XWIN_ROOT"

mkdir -p "$OUT/pb" "$OUT/headers" "$OUT/obj" "$OUT/logs"

# Same protos CheckScript generates
(cd "$SDK/common" && "$SDK/devtools/bin/linux/protoc" -I. -I"$SDK/thirdparty/protobuf-3.21.8/src" --cpp_out="$OUT/pb" \
	network_connection.proto networkbasetypes.proto netmessages.proto valveextensions.proto source2_steam_stats.proto 2>/dev/null)

# AMBuildScript's msvc + windows settings for a release build, and what
# hl2sdk-manifests' SdkHelpers.configureCxx adds for cs2
CXXFLAGS=(
	--target=x86_64-pc-windows-msvc /nologo /std:c++20 /EHsc /MT /Ox /W0
	/imsvc"$XWIN_ROOT/crt/include" /imsvc"$XWIN_ROOT/sdk/include/ucrt"
	/imsvc"$XWIN_ROOT/sdk/include/um" /imsvc"$XWIN_ROOT/sdk/include/shared"
	# Windows SDK 10.0.26100 does not declare _recalloc_base, which memoverride.cpp calls
	/FI"$SDK/.github/local/xwin-crt-shim.h"
	# MSVC assumes cmpxchg16b on x64, clang needs it spelled out for _InterlockedCompareExchange128
	-mcx16
	-DCOMPILER_MSVC -DCOMPILER_MSVC64 -DNDEBUG -DX64BITS -DPLATFORM_64BITS -D_LIB
	-D_WINDOWS -DWINDOWS -DWIN32 -DWIN64 -D_CRT_SECURE_NO_DEPRECATE -D_CRT_NONSTDC_NO_DEPRECATE
	-DSOURCE_ENGINE=25 -DGAME_DLL -DRAD_TELEMETRY_DISABLED -D_ITERATOR_DEBUG_LEVEL=0
	-I"$SDK/thirdparty/protobuf-3.21.8/src" -I"$SDK/public" -I"$SDK/public/engine2" -I"$SDK/public/mathlib"
	-I"$SDK/public/tier0" -I"$SDK/public/entity2" -I"$SDK/game/shared" -I"$SDK/common" -I"$OUT/pb"
)
LDFLAGS=(
	/nologo /libpath:"$XWIN_ROOT/crt/lib/x86_64" /libpath:"$XWIN_ROOT/sdk/lib/ucrt/x86_64" /libpath:"$XWIN_ROOT/sdk/lib/um/x86_64"
	"$SDK/lib/public/win64/2015/libprotobuf.lib" "$SDK/lib/public/win64/mathlib.lib" "$SDK/lib/public/win64/tier0.lib"
	"$SDK/lib/public/win64/interfaces.lib" "$SDK/lib/public/win64/steam_api64.lib" legacy_stdio_definitions.lib
)

# Every header but the ones CheckScript skips
(cd "$SDK" && find common game public -name '*.h' | sort) | while read -r header; do
	case "$header" in
		public/vscript/vscript_templates.h) continue ;;
		public/steam/steam_api.h|public/steam/steam_gameserver.h) ;;
		public/steam/*) continue ;;
	esac
	file="$OUT/headers/${header//\//_}.cpp"
	content="#include \"$SDK/$header\""
	[ -f "$file" ] && [ "$(cat "$file")" = "$content" ] || echo "$content" > "$file"
done

obj() { local name=${1#"$SDK"/}; name=${name#"$OUT"/}; echo "$OUT/obj/${name//\//_}.obj"; }

CHECK_SOURCES=("$OUT"/headers/*.cpp "$SDK"/entity2/*.cpp "$SDK"/tier0_perproject/*.cpp "$SDK/public/tier0/memoverride.cpp" "$SDK"/tests/*.cpp "$OUT"/pb/*.pb.cc)
RUN_SOURCES=("$SDK"/tests/run/*.cpp)

compile() {
	local src=$1 out log
	out=$(obj "$src"); log="$OUT/logs/$(basename "$out").log"
	if "$LLVM_BIN/clang-cl" "${CXXFLAGS[@]}" /c "$src" /Fo"$out" > "$log" 2>&1; then
		rm -f "$log"
	else
		echo "FAILED: ${src#"$SDK"/}"
		grep -m3 'error' "$log" | sed 's/^/    /'
		return 1
	fi
}
export -f compile obj
export SDK OUT LLVM_BIN
# Arrays don't export; hand them to the workers through a file
declare -p CXXFLAGS > "$OUT/cxxflags.sh"

echo "Compiling ${#CHECK_SOURCES[@]} check sources and ${#RUN_SOURCES[@]} test programs..."
status=0
printf '%s\n' "${CHECK_SOURCES[@]}" "${RUN_SOURCES[@]}" |
	xargs -P"$(nproc)" -I{} bash -c "source '$OUT/cxxflags.sh'; compile '{}'" || status=1
[ "$status" = 0 ] || { echo "Compilation failed"; exit 1; }

link() {
	local out=$1; shift
	if ! "$LLVM_BIN/lld-link" "${LDFLAGS[@]}" "$@" /out:"$out" > "$OUT/logs/$(basename "$out").log" 2>&1; then
		echo "FAILED: link $(basename "$out")"
		grep -m10 'error' "$OUT/logs/$(basename "$out").log" | sed 's/^/    /'
		return 1
	fi
	echo "Linked $(basename "$out")"
}

check_objs=(); for src in "${CHECK_SOURCES[@]}"; do check_objs+=("$(obj "$src")"); done
link "$OUT/sdkcheck.dll" /dll "${check_objs[@]}" || status=1

# tests/run programs with the extra sources CheckScript gives them
for src in "${RUN_SOURCES[@]}"; do
	name=$(basename "$src" .cpp)
	objs=("$(obj "$src")" "$(obj "$SDK/public/tier0/memoverride.cpp")")
	case "$name" in
		keyvalues3) objs+=("$(obj "$SDK/tier0_perproject/keyvalues3.cpp")") ;;
		ccommand) objs+=("$(obj "$SDK/tier0_perproject/convar.cpp")") ;;
		cmdkeyvalues) for pb in "$OUT"/pb/*.pb.cc; do objs+=("$(obj "$pb")"); done ;;
	esac
	link "$OUT/${name}_test.exe" "${objs[@]}" || status=1
done

[ "$status" = 0 ] && echo "Windows check passed" || echo "Windows check failed"
exit "$status"
