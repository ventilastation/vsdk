#include <esp_system.h>
#include <stdint.h>
#include <stdbool.h>
#include "py/nlr.h"
#include "py/obj.h"
#include "py/runtime.h"
#include "py/binary.h"
#include "py/objtype.h"

#include "sprites.h"
#include "display_geometry.h"

#define PIXELS VS_DISPLAY_PIXELS
#define VS2_MAX_LAYERS 8
#define VS2_MAX_SPRITES 100
#define VS2_MAX_TILEMAPS 16
#define VS2_MAX_DRAWABLES (VS2_MAX_SPRITES + VS2_MAX_TILEMAPS)

#define VS2_DRAW_SPRITE 0
#define VS2_DRAW_TILEMAP 1
#define VS2_CURVE_LENGTH 256

extern uint32_t* palette_pal;
extern int gamma_mode;
extern bool starfield_enabled;
extern uint8_t deepspace[256];
extern uint8_t vs2_deepspace[256];

typedef struct {
    uint8_t id;
    uint8_t mode;
    uint8_t flags;
    /* Render-time translation, 8.8 fixed point -- the same units and
     * convention as vs2_sprite_t.x/.y and vs2_tilemap_t.x/.y (see
     * fixed_floor_to_int() in gpu.c). X is angular and folds into the
     * renderer's already-modular column arithmetic; Y shares sprite y's
     * domain (LED index on HUD, depth on a tunnel) and folds into the row
     * range a drawable occupies. Both default to 0, so a layer nobody
     * touches renders exactly as it did before cameras existed. */
    int32_t camera_x;
    int32_t camera_y;
    /* Depth (or, on FULLSCREEN, radial-extent) -> LED-row table. One curve
     * per layer, inline rather than a pointer: this struct is embedded
     * directly in vs2_layer_obj_t (see vs2_native.c), the same
     * MicroPython-heap-allocated object id/mode/flags already live in, so
     * there is no separate PSRAM-backed allocation to introduce. A layer
     * gets a real default (a copy of vs2_deepspace) the moment it is
     * constructed -- see vs2_layer_make_new() -- so vs2_slot_curve()'s
     * fallback below is only ever exercised for a drawable with no layer
     * at all (VS2_NO_LAYER), matching vs2_slot_mode()'s fallback_mode
     * pattern one field up. */
    uint8_t curve[VS2_CURVE_LENGTH];
} vs2_layer_t;

typedef struct {
    uint8_t layer;
    uint8_t image_strip;
    uint8_t frame;
    uint8_t mode;
    uint8_t flags;
    int32_t x;
    int32_t y;
} vs2_sprite_t;

typedef struct {
    uint8_t layer;
    uint8_t image_strip;
    uint8_t flags;
    uint8_t mode;
    uint16_t columns;
    uint16_t rows;
    uint16_t tile_width;
    uint16_t tile_height;
    uint16_t viewport_x;
    uint16_t viewport_y;
    uint16_t viewport_w;
    uint16_t viewport_h;
    int32_t x;
    int32_t y;
    /* borrowed pointer; the owning Python object keeps the buffer alive */
    const uint8_t* frames;
    uint32_t frames_len;
} vs2_tilemap_t;

typedef struct {
    uint8_t kind;
    uint8_t index;
} vs2_draw_ref_t;

typedef struct {
    uint8_t layer_count;
    uint8_t sprite_count;
    uint8_t tilemap_count;
    uint8_t draw_order_count;
    const vs2_layer_t* const* layers;
    const vs2_sprite_t* const* sprites;
    const vs2_tilemap_t* const* tilemaps;
    const vs2_draw_ref_t* draw_order;
} vs2_scene_t;

extern bool vs2_render_active;
extern vs2_scene_t vs2_active_scene;

typedef void (*vs2_service_fn_t)(void);

void render_vs2(int column, uint32_t* led_buffer, const vs2_scene_t* scene);
void render_vs2_cooperative(int column, uint32_t* led_buffer,
    const vs2_scene_t* scene, vs2_service_fn_t service);

const char* memoryview_data(mp_obj_t mv_obj);
