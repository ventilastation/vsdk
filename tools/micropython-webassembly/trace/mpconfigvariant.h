#include "variants/standard/mpconfigvariant.h"

#define MICROPY_PY_SYS_SETTRACE (1)

// Asyncify adds native frames to each Python call. Mobile browsers have a
// smaller native stack; keep Python-to-Python calls on the Python stack so
// ordinary scene construction can boot there too.
#define MICROPY_STACKLESS (1)
