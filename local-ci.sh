#!/usr/bin/env bash
# Runs .github/workflows/local.yml -- ci.yml and cmake.yml for linux and a clang-cl
# cross-build for windows -- on this machine through act, instead of GitHub Actions.
#
#   ./local-ci.sh                 every job
#   ./local-ci.sh linux           ci.yml's AMBuild builds + tests (clang-22/gcc, release/debug)
#   ./local-ci.sh cmake           cmake.yml's linux builds (Release/Debug)
#   ./local-ci.sh windows         clang-cl cross-build of the libraries + header/source check
#   ./local-ci.sh linux -- -v     anything after -- goes to act
#
# Needs act (https://github.com/nektos/act, or 'gh extension install nektos/gh-act') and
# docker. The windows job uses the host's xwin splat (XWIN_ROOT, default ~/.xwin) when
# there is one and splats a fresh one (~630MB) otherwise. act copies the working tree,
# so uncommitted changes are built too.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

RUNNER_IMAGE=catthehacker/ubuntu:full-latest
BUILD_IMAGE=ghcr.io/alliedmodders/build-containers/debian11-clang22:latest

job_args=()
case "${1:-all}" in
	all) ;;
	linux) job_args=(-j ambuild_linux) ;;
	cmake) job_args=(-j cmake_linux) ;;
	windows) job_args=(-j windows) ;;
	-h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
	--) set -- all "$@" ;;
	*) echo "Unknown job '$1' (all, linux, cmake, windows)" >&2; exit 1 ;;
esac
shift || true
[ "${1:-}" = "--" ] && shift

if command -v act &> /dev/null; then
	act_cmd=(act)
elif command -v gh &> /dev/null && gh act --version &> /dev/null; then
	act_cmd=(gh act)
else
	echo "act is not installed: https://github.com/nektos/act or 'gh extension install nektos/gh-act'" >&2
	exit 1
fi
docker info &> /dev/null || { echo "Docker is not running" >&2; exit 1; }

# act runs with --pull=false, so fetch the images it would otherwise not find
for image in "$RUNNER_IMAGE" "$BUILD_IMAGE"; do
	docker image inspect "$image" &> /dev/null || docker pull "$image"
done

# --user root: the runner image's default user (runner, 1001) can't write to a
# workspace copied from a home directory
container_options="--user root"
xwin_root="${XWIN_ROOT:-$HOME/.xwin}"
if [ -d "$xwin_root/crt/include" ]; then
	container_options+=" -v $xwin_root:/opt/xwin:ro"
else
	echo "No xwin splat at $xwin_root - the windows job will download one (~630MB)."
fi

exec "${act_cmd[@]}" workflow_dispatch \
	-W .github/workflows/local.yml \
	"${job_args[@]}" \
	-P ubuntu-latest="$RUNNER_IMAGE" \
	--pull=false \
	--container-options "$container_options" \
	"$@"
