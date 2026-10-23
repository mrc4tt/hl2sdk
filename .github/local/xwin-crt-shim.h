// Force-included by the xwin cross-builds in .github/local only. Never reaches an
// MSVC build.
//
// public/tier0/memoverride.cpp leans on CRT internals that the headers xwin splats
// leave out but a Visual Studio install declares:
// - _recalloc_base() and _heap_alloc(): memoverride.cpp calls them but leaves its
//   own definitions inside #if 0 blocks. Both are still exported by the CRT, so a
//   declaration is all that is missing -- the signatures below are the
//   _MSC_VER >= 1900 forms memoverride.cpp calls them with.
// - _CRT_NOEXCEPT, which _msize_base() is declared with.
#pragma once

#include <stddef.h>

#ifndef _CRT_NOEXCEPT
#define _CRT_NOEXCEPT noexcept
#endif

#ifdef __cplusplus
extern "C" {
#endif

void* __cdecl _recalloc_base(void* block, size_t count, size_t size);
void* __cdecl _heap_alloc(size_t size);

#ifdef __cplusplus
}
#endif
