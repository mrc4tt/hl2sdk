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
# docker. The jobs run in a slim runner image built from .github/local/runner.Dockerfile
# on first use (~3 GB; RUNNER_IMAGE=... overrides it). The windows job uses the host's xwin splat (XWIN_ROOT, default ~/.xwin) when
# there is one and splats a fresh one (~630MB) otherwise. act copies the working tree,
# so uncommitted changes are built too.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# A submodule's .git is a file pointing into the superproject (gitdir: ../.git/modules/...),
# which act's copy of the tree cannot follow, and every commit made there moves the
# superproject's gitlink. Run this from a standalone clone instead.
if [ -n "$(git rev-parse --show-superproject-working-tree 2>/dev/null)" ]; then
	echo "This checkout is a submodule of $(git rev-parse --show-superproject-working-tree)." >&2
	echo "Run local-ci.sh from a standalone clone: git clone -b cs2 https://github.com/mrc4tt/hl2sdk" >&2
	exit 1
fi

RUNNER_DOCKERFILE=.github/local/runner.Dockerfile
# Tagged with the Dockerfile's hash, so editing it builds a fresh image
RUNNER_IMAGE=${RUNNER_IMAGE:-hl2sdk-local-ci:$(sha256sum "$RUNNER_DOCKERFILE" | cut -c1-12)}
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

# act runs with --pull=false, so fetch or build the images it would otherwise not find
if ! docker image inspect "$RUNNER_IMAGE" &> /dev/null; then
	if [[ "$RUNNER_IMAGE" == hl2sdk-local-ci:* ]]; then
		echo "Building the runner image $RUNNER_IMAGE (once)..."
		docker build -t "$RUNNER_IMAGE" -f "$RUNNER_DOCKERFILE" .github/local
	else
		docker pull "$RUNNER_IMAGE"
	fi
fi
docker image inspect "$BUILD_IMAGE" &> /dev/null || docker pull "$BUILD_IMAGE"

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
