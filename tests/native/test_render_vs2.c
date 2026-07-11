/* Host tests for the hardware VS2 renderer in gpu.c.
 *
 * Compiled against tests/native/stubs so gpu.c builds with plain cc. With
 * gamma_mode=0 and an identity intensity table, the finished led_buffer
 * carries palette colors through unchanged, so assertions can check raw
 * palette markers. The fixtures mirror tests/test_emulator_vs2_render.py and
 * web/render-parity-test.js.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gpu.h"

/* gpu.c externs (device definitions live in intensidades.c / povdisplay.c) */
uint8_t intensidades[PIXELS][256];
uint8_t brillos[PIXELS];
uint8_t intensidades_por_led[PIXELS];

void calculate_deepspace(void);
extern uint8_t deepspace[256];

#define HUD_LED(dest_y) (PIXELS - 1 - (dest_y))

static int failures = 0;

#define CHECK_EQ(actual, expected, message) \
    do { \
        uint32_t check_actual = (actual); \
        uint32_t check_expected = (expected); \
        if (check_actual != check_expected) { \
            printf("FAIL %s: got %u, expected %u\n", message, \
                (unsigned)check_actual, (unsigned)check_expected); \
            failures++; \
        } \
    } while (0)

/* Mirrors make_tile_strip() in the emulator tests: 4x4 tiles, 3 frames,
 * stored column-mirrored like real strips. Frame 0: screen column 0 is
 * palette index 1, the rest 2. Frame 1: solid 3. Frame 2: solid 4 with the
 * tile's screen pixel (0, 0) transparent. */
static uint8_t tile_strip_bytes[4 + 3 * 16];
static uint8_t sprite_strip_bytes[4 + 4] = { 2, 2, 1, 0, 1, 2, 3, 4 };
static uint32_t palette_storage[256];

/* 2x2 map: top row = frame 0 | frame 1, bottom row = frame 2 | empty cell (255) */
static const uint8_t default_frames[4] = { 0, 1, 2, 255 };

static void build_tile_strip(void) {
    tile_strip_bytes[0] = 4;  /* frame_width */
    tile_strip_bytes[1] = 4;  /* frame_height */
    tile_strip_bytes[2] = 3;  /* total_frames */
    tile_strip_bytes[3] = 0;  /* palette */
    uint8_t* frame0 = tile_strip_bytes + 4;
    uint8_t* frame1 = frame0 + 16;
    uint8_t* frame2 = frame1 + 16;
    for (int dx = 0; dx < 4; dx++) {
        for (int dy = 0; dy < 4; dy++) {
            frame0[(3 - dx) * 4 + dy] = dx == 0 ? 1 : 2;
        }
    }
    memset(frame1, 3, 16);
    memset(frame2, 4, 16);
    frame2[3 * 4 + 0] = 255;
}

static vs2_tilemap_t default_tilemap(void) {
    vs2_tilemap_t tilemap = {
        .layer = 255,
        .image_strip = 9,
        .flags = 0x01,
        .mode = 2,
        .columns = 2,
        .rows = 2,
        .tile_width = 4,
        .tile_height = 4,
        .viewport_x = 0,
        .viewport_y = 0,
        .viewport_w = 8,
        .viewport_h = 8,
        .x = 10 * 256,
        .y = 40 * 256,
        .frames = default_frames,
        .frames_len = 4,
    };
    return tilemap;
}

/* Renders one column of `scene` and returns the marker byte for one led. */
static uint32_t render_led(const vs2_scene_t* scene, int column, int led) {
    uint32_t led_buffer[PIXELS];
    render_vs2(column, led_buffer, scene);
    return led_buffer[led] >> 24;
}

static vs2_scene_t tilemap_scene(const vs2_tilemap_t** tilemap_records, uint8_t count) {
    vs2_scene_t scene = {
        .layer_count = 0,
        .sprite_count = 0,
        .tilemap_count = count,
        .layers = NULL,
        .sprites = NULL,
        .tilemaps = tilemap_records,
    };
    return scene;
}

int main(void) {
    calculate_deepspace();
    build_tile_strip();
    for (int n = 0; n < PIXELS; n++) {
        for (int v = 0; v < 256; v++) {
            intensidades[n][v] = v;
        }
    }
    gamma_mode = 0;
    palette_pal = palette_storage;
    palette_storage[1] = 10u << 24;
    palette_storage[2] = 20u << 24;
    palette_storage[3] = 30u << 24;
    palette_storage[4] = 40u << 24;
    image_stripes[8] = (const ImageStrip*)sprite_strip_bytes;
    image_stripes[9] = (const ImageStrip*)tile_strip_bytes;

    /* HUD mode at y=40: dest rows 40..47 land on leds 13..6. */
    {
        vs2_tilemap_t tilemap = default_tilemap();
        const vs2_tilemap_t* records[] = { &tilemap };
        vs2_scene_t scene = tilemap_scene(records, 1);
        for (int n = 0; n < 4; n++) {
            CHECK_EQ(render_led(&scene, 10, 13 - n), 10, "frame 0 screen column 0");
        }
        CHECK_EQ(render_led(&scene, 10, 9), 0, "frame 2 transparent pixel");
        CHECK_EQ(render_led(&scene, 10, 8), 40, "frame 2 solid pixel");
        CHECK_EQ(render_led(&scene, 11, 13), 20, "unmirrored tile column");
        CHECK_EQ(render_led(&scene, 14, 13), 30, "second map column frame 1");
        CHECK_EQ(render_led(&scene, 14, 9), 0, "empty cell renders nothing");
        CHECK_EQ(render_led(&scene, 18, 13), 0, "beyond map width");
    }

    /* Horizontal viewport pan */
    {
        vs2_tilemap_t tilemap = default_tilemap();
        tilemap.viewport_x = 4;
        tilemap.viewport_w = 4;
        const vs2_tilemap_t* records[] = { &tilemap };
        vs2_scene_t scene = tilemap_scene(records, 1);
        CHECK_EQ(render_led(&scene, 10, 13), 30, "viewport pans horizontally");
        CHECK_EQ(render_led(&scene, 14, 13), 0, "viewport window width");
    }

    /* Vertical viewport pan */
    {
        vs2_tilemap_t tilemap = default_tilemap();
        tilemap.viewport_y = 2;
        tilemap.viewport_h = 4;
        const vs2_tilemap_t* records[] = { &tilemap };
        vs2_scene_t scene = tilemap_scene(records, 1);
        CHECK_EQ(render_led(&scene, 10, 13), 10, "viewport pans vertically");
        CHECK_EQ(render_led(&scene, 10, 11), 0, "vertical pan transparent pixel");
        CHECK_EQ(render_led(&scene, 10, 10), 40, "vertical pan frame 2");
        CHECK_EQ(render_led(&scene, 10, 9), 0, "viewport window height");
    }

    /* Viewport clamps past the map edge */
    {
        vs2_tilemap_t tilemap = default_tilemap();
        tilemap.viewport_x = 6;
        const vs2_tilemap_t* records[] = { &tilemap };
        vs2_scene_t scene = tilemap_scene(records, 1);
        CHECK_EQ(render_led(&scene, 10, 13), 30, "viewport clamps to map edge");
        CHECK_EQ(render_led(&scene, 12, 13), 0, "clamped viewport width");
    }

    /* X wrap around column zero */
    {
        vs2_tilemap_t tilemap = default_tilemap();
        tilemap.x = 254 * 256;
        const vs2_tilemap_t* records[] = { &tilemap };
        vs2_scene_t scene = tilemap_scene(records, 1);
        CHECK_EQ(render_led(&scene, 254, 13), 10, "tilemap at wrap origin");
        CHECK_EQ(render_led(&scene, 0, 13), 20, "tilemap wraps around column zero");
    }

    /* Tilemaps draw behind sprites */
    {
        vs2_tilemap_t tilemap = default_tilemap();
        const vs2_tilemap_t* tilemap_records[] = { &tilemap };
        vs2_sprite_t sprite = {
            .layer = 255, .image_strip = 8, .frame = 0, .mode = 2,
            .flags = 0x01, .x = 10 * 256, .y = 40 * 256,
        };
        const vs2_sprite_t* sprite_records[] = { &sprite };
        vs2_scene_t scene = tilemap_scene(tilemap_records, 1);
        scene.sprite_count = 1;
        scene.sprites = sprite_records;
        CHECK_EQ(render_led(&scene, 10, 13), 30, "sprite covers the tilemap");
        CHECK_EQ(render_led(&scene, 10, 11), 10, "tilemap shows below the sprite");
    }

    /* Layer visibility and mode override */
    {
        vs2_tilemap_t tilemap = default_tilemap();
        tilemap.layer = 0;
        const vs2_tilemap_t* tilemap_records[] = { &tilemap };
        vs2_layer_t hidden_layer = { .id = 0, .mode = 2, .flags = 0 };
        const vs2_layer_t* layer_records[] = { &hidden_layer };
        vs2_scene_t scene = tilemap_scene(tilemap_records, 1);
        scene.layer_count = 1;
        scene.layers = layer_records;
        CHECK_EQ(render_led(&scene, 10, 13), 0, "tilemap on hidden layer");

        vs2_layer_t tunnel_layer = { .id = 0, .mode = 1, .flags = 0x01 };
        layer_records[0] = &tunnel_layer;
        CHECK_EQ(render_led(&scene, 10, deepspace[40]), 10, "layer mode overrides tilemap mode");
    }

    /* TUNNEL projection uses deepspace */
    {
        vs2_tilemap_t tilemap = default_tilemap();
        tilemap.mode = 1;
        const vs2_tilemap_t* records[] = { &tilemap };
        vs2_scene_t scene = tilemap_scene(records, 1);
        CHECK_EQ(render_led(&scene, 10, deepspace[40]), 10, "TUNNEL projection");
    }

    /* FULLSCREEN tilemaps are skipped */
    {
        vs2_tilemap_t tilemap = default_tilemap();
        tilemap.mode = 0;
        const vs2_tilemap_t* records[] = { &tilemap };
        vs2_scene_t scene = tilemap_scene(records, 1);
        CHECK_EQ(render_led(&scene, 10, 13), 0, "FULLSCREEN tilemap skipped");
    }

    /* Mismatched tile dims are skipped */
    {
        vs2_tilemap_t tilemap = default_tilemap();
        tilemap.tile_width = 8;
        tilemap.tile_height = 8;
        tilemap.viewport_w = 16;
        tilemap.viewport_h = 16;
        const vs2_tilemap_t* records[] = { &tilemap };
        vs2_scene_t scene = tilemap_scene(records, 1);
        CHECK_EQ(render_led(&scene, 10, 13), 0, "mismatched tile dims skipped");
    }

    /* VS2 sprite regression: flips still work through the shared helpers */
    {
        vs2_sprite_t sprite = {
            .layer = 255, .image_strip = 8, .frame = 0, .mode = 2,
            .flags = 0x01 | 0x02 | 0x04, .x = 20 * 256, .y = 51 * 256,
        };
        const vs2_sprite_t* sprite_records[] = { &sprite };
        vs2_scene_t scene = {
            .layer_count = 0, .sprite_count = 1, .tilemap_count = 0,
            .layers = NULL, .sprites = sprite_records, .tilemaps = NULL,
        };
        CHECK_EQ(render_led(&scene, 20, HUD_LED(51)), 20, "sprite flip_x+flip_y");
        CHECK_EQ(render_led(&scene, 20, HUD_LED(52)), 10, "sprite flip_y row");
        CHECK_EQ(render_led(&scene, 21, HUD_LED(51)), 40, "sprite flip_x column");
    }

    if (failures) {
        printf("render_vs2 host tests: %d failure(s)\n", failures);
        return 1;
    }
    printf("render_vs2 host tests passed\n");
    return 0;
}
