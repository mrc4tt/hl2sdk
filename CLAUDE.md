@AGENTS.md

## This fork (mrc4tt/hl2sdk)

- `origin` is mrc4tt/hl2sdk branch `cs2`; `upstream` (alliedmodders/s2sdk) is fetch-only. Never open PRs upstream.
- Don't wait for upstream after a CS2 update: verify against the binaries per AGENTS.md and fix here.
- Build check before pushing: `./local-ci.sh linux` and `./local-ci.sh windows` (clang-cl cross-build).
- ABI check: `~/CS2_VibeSignatures/run_cpp_tests.py` compiles these headers (submodule `hl2sdk_cs2`) and compares vtable slots with the binary artifacts in `bin_artifacts/<gamever>/`. See `~/CS2_VibeSignatures/sdk_abi_check.sh`.
- Protobufs: `./update_protos.sh <game dir>` regenerates `common/` and `game/shared/` protos from the game's own binaries (`devtools/dump_protos.py` reads the descriptors protoc compiled into libserver/libengine2/libnetworksystem). Output is byte-identical to GameTracking-CS2's on 14196 and 14197; `--gametracking [ref]` still fetches theirs as a cross-check. `hl2sdk-lib-sync` (server-ops) runs it on every new build and opens the PR. `base_gcmessages_csgo.proto` is in no dump and stays as is.
