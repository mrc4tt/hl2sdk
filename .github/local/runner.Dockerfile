# Runner image for local-ci.sh (built by it on first use): act's slim Ubuntu image
# plus what local.yml's jobs need - cmake/ninja for the cmake job, clang >= 19 for the
# windows job (the MSVC STL needs it; clang-cl is in clang-tools-20). ~3 GB instead of
# catthehacker/ubuntu:full-latest's ~75 GB.
FROM catthehacker/ubuntu:act-latest
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      cmake ninja-build clang-20 clang-tools-20 lld-20 llvm-20 \
 && rm -rf /var/lib/apt/lists/*
