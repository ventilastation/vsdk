// iOS host configuration for MicroPython's Unix VFS port.
//
// iOS forbids runtime-generated executable memory, so keep the bytecode VM
// while explicitly disabling every native-code emitter that the Unix port
// would otherwise auto-enable for the simulator/device architecture.

#define MICROPY_CONFIG_ROM_LEVEL (MICROPY_CONFIG_ROM_LEVEL_EXTRA_FEATURES)

#include "mpconfigvariant_common.h"

// The Unix convenience wrapper for libc system() is unavailable in the iOS
// SDK and is not needed by Ventilastation.
#undef MICROPY_PY_OS_SYSTEM
#define MICROPY_PY_OS_SYSTEM (0)

#define MICROPY_EMIT_X64 (0)
#define MICROPY_EMIT_X86 (0)
#define MICROPY_EMIT_THUMB (0)
#define MICROPY_EMIT_ARM (0)
#define MICROPY_EMIT_XTENSA (0)
#define MICROPY_EMIT_XTENSAWIN (0)
#define MICROPY_EMIT_RV32 (0)
#define MICROPY_EMIT_NATIVE_DEBUG (0)

// The Unix x86_64 assembly NLR implementation assumes an executable-style
// process entrypoint.  The embedded iOS VM uses the portable exception path.
#define MICROPY_NLR_SETJMP (1)

// UIKit enters the VM from framework callbacks rather than a process entry
// point, so the Unix port's relative C-stack guard cannot measure a stable
// top-of-stack.  The Simulator's protected main stack is still scanned by the
// VM; disable only this relative guard to avoid false recursion failures.
#define MICROPY_STACK_CHECK (0)
