#pragma once
/* Parses the raw VS2 scene wire format (see decode_vs2_scene() in
 * emulator/povrender.py for the byte layout) directly into the
 * vs2_scene_t/vs2_sprite_t/vs2_tilemap_t structs gpu.c's render_vs2()
 * already consumes on real hardware -- no intermediate Python (or C)
 * object representation in between.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "gpu.h"

typedef struct {
    vs2_layer_t layer_storage[VS2_MAX_LAYERS];
    vs2_sprite_t sprite_storage[VS2_MAX_SPRITES];
    vs2_tilemap_t tilemap_storage[VS2_MAX_TILEMAPS];
    const vs2_layer_t* layer_ptrs[VS2_MAX_LAYERS];
    const vs2_sprite_t* sprite_ptrs[VS2_MAX_SPRITES];
    const vs2_tilemap_t* tilemap_ptrs[VS2_MAX_TILEMAPS];
    vs2_scene_t scene;
} vs2_wire_scene_t;

/* Parses `data` (length `len`) into `out`. Returns true on success, matching
 * decode_vs2_scene()'s validation (magic, version, declared record sizes all
 * fitting inside `len`). Unlike decode_vs2_scene(), this does NOT pre-filter
 * invisible sprites/tilemaps or resolve layer-mode overrides -- render_vs2()
 * already does both per column, so every parsed record is included as-is and
 * left for it to skip or apply.
 *
 * `data` must stay valid and unmodified for as long as `out` is in use:
 * tilemap frame tables are borrowed pointers into it, the same convention
 * vs2_tilemap_t.frames already uses on-device (see gpu.h).
 */
bool vs2_wire_decode_scene(const uint8_t* data, size_t len, vs2_wire_scene_t* out);
