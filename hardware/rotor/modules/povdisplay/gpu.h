#include <esp_system.h>
#include <stdint.h>
#include <stdbool.h>
#include "py/nlr.h"
#include "py/obj.h"
#include "py/runtime.h"
#include "py/binary.h"
#include "py/objtype.h"

#include "sprites.h"

#define PIXELS 54

extern uint32_t* palette_pal;
extern int gamma_mode;
