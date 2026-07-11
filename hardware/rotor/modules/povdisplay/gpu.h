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
#define VS2_MAX_LAYERS 16
#define VS2_MAX_SPRITES 100
#define VS2_MAX_TILEMAPS 8

extern uint32_t* palette_pal;
extern int gamma_mode;

typedef struct {
    uint8_t id;
    uint8_t mode;
    uint8_t flags;
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
    uint8_t layer_count;
    uint8_t sprite_count;
    uint8_t tilemap_count;
    const vs2_layer_t* const* layers;
    const vs2_sprite_t* const* sprites;
    const vs2_tilemap_t* const* tilemaps;
} vs2_scene_t;

extern bool vs2_render_active;
extern vs2_scene_t vs2_active_scene;

void render_vs2(int column, uint32_t* led_buffer, const vs2_scene_t* scene);

const char* memoryview_data(mp_obj_t mv_obj);
