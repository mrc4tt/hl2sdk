@AGENTS.md

## This fork (mrc4tt/hl2sdk)

- `origin` is mrc4tt/hl2sdk branch `cs2`; `upstream` (alliedmodders/s2sdk) is fetch-only. Never open PRs upstream.
- Don't wait for upstream after a CS2 update: verify against the binaries per AGENTS.md and fix here.
- Build check before pushing: `./local-ci.sh linux` and `./local-ci.sh windows` (clang-cl cross-build).
- ABI check: `~/CS2_VibeSignatures/run_cpp_tests.py` compiles these headers (submodule `hl2sdk_cs2`) and compares vtable slots with the binary artifacts in `bin_artifacts/<gamever>/`. See `~/CS2_VibeSignatures/sdk_abi_check.sh`.
- Protobufs: `./update_protos.sh` regenerates `common/` and `game/shared/` protos from the GameTracking-CS2 dump.
