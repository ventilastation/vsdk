/* Host-build stub: just enough MicroPython object model for gpu.h/sprites.h. */
#pragma once
#include <stdint.h>

typedef void* mp_obj_t;

typedef struct _mp_obj_base_t {
    const void *type;
} mp_obj_base_t;
