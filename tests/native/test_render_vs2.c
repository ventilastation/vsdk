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
void render(int column, uint32_t* led_buffer);

#define HUD_LED(dest_y) (PIXELS - 1 - (dest_y))

static int failures = 0;
static int service_calls = 0;

static void count_service(void) {
    service_calls++;
}

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
/* Headers store width and frame count minus one (sprites.h). */
static uint8_t sprite_strip_bytes[4 + 4] = { 2 - 1, 2, 1 - 1, 0, 1, 2, 3, 4 };
static uint8_t fullscreen_strip_bytes[4 + PIXELS];
static uint32_t palette_storage[256];

/* A strip whose header claims three 4x4 frames while only one is
 * registered, with canary pixels right after it in memory: what a stale
 * ROM, or a frame number past the strip's last, looks like to the renderer.
 * Every read past the registered length must come back transparent. */
static struct {
    uint8_t strip[4 + 16];
    uint8_t canary[64];
} overdeclared;
#define OVERDECLARED_SLOT 11
#define CANARY_MARKER 50

static void register_strip(int slot, const uint8_t* bytes, uint32_t total_length) {
    image_stripes[slot] = (const ImageStrip*)bytes;
    image_strip_lengths[slot] = total_length - 4;
}

/* 2x2 map: top row = frame 0 | frame 1, bottom row = frame 2 | empty cell (255) */
static const uint8_t default_frames[4] = { 0, 1, 2, 255 };

static void build_tile_strip(void) {
    tile_strip_bytes[0] = 4 - 1;  /* frame width */
    tile_strip_bytes[1] = 4;      /* frame height */
    tile_strip_bytes[2] = 3 - 1;  /* frames */
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
    register_strip(8, sprite_strip_bytes, sizeof(sprite_strip_bytes));
    register_strip(9, tile_strip_bytes, sizeof(tile_strip_bytes));
    fullscreen_strip_bytes[0] = 1 - 1;
    fullscreen_strip_bytes[1] = PIXELS;
    fullscreen_strip_bytes[2] = 1 - 1;
    fullscreen_strip_bytes[3] = 0;
    memset(fullscreen_strip_bytes + 4, 1, PIXELS);
    register_strip(10, fullscreen_strip_bytes, sizeof(fullscreen_strip_bytes));
    overdeclared.strip[0] = 4 - 1;  /* frame width */
    overdeclared.strip[1] = 4;      /* frame height */
    overdeclared.strip[2] = 3 - 1;  /* frames: two more than registered */
    overdeclared.strip[3] = 0;
    memset(overdeclared.strip + 4, 2, 16);
    memset(overdeclared.canary, 5, sizeof(overdeclared.canary));
    palette_storage[5] = (uint32_t)CANARY_MARKER << 24;
    register_strip(OVERDECLARED_SLOT, overdeclared.strip, sizeof(overdeclared.strip));

    /* VS2 projections share a rim-origin Y axis. */
    CHECK_EQ(vs2_deepspace[0], PIXELS - 1, "TUNNEL y=0 is outermost");
    CHECK_EQ(vs2_deepspace[255], 0, "TUNNEL y=255 is center");
    for (int y = 1; y < 256; y++) {
        if (vs2_deepspace[y] > vs2_deepspace[y - 1]) {
            printf("FAIL VS2 tunnel projection is not monotonic at y=%d\n", y);
            failures++;
            break;
        }
    }

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

    /* Flip flags mirror the complete tilemap viewport, including tile order
     * and the pixels inside each tile. Labels inherit this exact path. */
    {
        vs2_tilemap_t tilemap = default_tilemap();
        tilemap.flags = 0x01 | 0x02 | 0x04;
        const vs2_tilemap_t* records[] = { &tilemap };
        vs2_scene_t scene = tilemap_scene(records, 1);
        CHECK_EQ(render_led(&scene, 10, 13), 0, "flipped top-left is empty bottom-right");
        CHECK_EQ(render_led(&scene, 10, 9), 30, "flip y reverses tile rows");
        CHECK_EQ(render_led(&scene, 14, 13), 40, "flip x reverses tile columns");
        CHECK_EQ(render_led(&scene, 17, 6), 10, "flipped opposite corner");
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

    /* The sealed V2 draw table is the board path: it must honor tagged
     * sprite/tilemap order instead of falling back to the legacy two passes. */
    {
        vs2_tilemap_t tilemap = default_tilemap();
        const vs2_tilemap_t* tilemap_records[] = { &tilemap };
        vs2_sprite_t sprite = {
            .layer = 255, .image_strip = 8, .frame = 0, .mode = 2,
            .flags = 0x01, .x = 10 * 256, .y = 40 * 256,
        };
        const vs2_sprite_t* sprite_records[] = { &sprite };
        vs2_draw_ref_t order[] = {
            { .kind = VS2_DRAW_TILEMAP, .index = 0 },
            { .kind = VS2_DRAW_SPRITE, .index = 0 },
        };
        vs2_scene_t scene = tilemap_scene(tilemap_records, 1);
        scene.sprite_count = 1;
        scene.sprites = sprite_records;
        scene.draw_order = order;
        scene.draw_order_count = 2;
        CHECK_EQ(render_led(&scene, 10, 13), 30, "native draw table sprite on top");
        order[0].kind = VS2_DRAW_SPRITE;
        order[1].kind = VS2_DRAW_TILEMAP;
        CHECK_EQ(render_led(&scene, 10, 13), 10, "native draw table tilemap on top");
    }

    /* Cooperative front-buffer service does not alter the projected pixels.
     * It yields after four sprites and after every tilemap so one expensive
     * scene column cannot hide a physical angular edge. */
    {
        vs2_tilemap_t tilemap = default_tilemap();
        const vs2_tilemap_t* tilemap_records[] = { &tilemap };
        vs2_sprite_t sprite = {
            .layer = 255, .image_strip = 8, .frame = 0, .mode = 2,
            .flags = 0x01, .x = 10 * 256, .y = 40 * 256,
        };
        const vs2_sprite_t* sprite_records[] = { &sprite };
        vs2_draw_ref_t order[] = {
            { .kind = VS2_DRAW_SPRITE, .index = 0 },
            { .kind = VS2_DRAW_SPRITE, .index = 0 },
            { .kind = VS2_DRAW_SPRITE, .index = 0 },
            { .kind = VS2_DRAW_SPRITE, .index = 0 },
            { .kind = VS2_DRAW_TILEMAP, .index = 0 },
            { .kind = VS2_DRAW_SPRITE, .index = 0 },
        };
        vs2_scene_t scene = tilemap_scene(tilemap_records, 1);
        scene.sprite_count = 1;
        scene.sprites = sprite_records;
        scene.draw_order = order;
        scene.draw_order_count = 6;
        uint32_t expected[PIXELS];
        uint32_t actual[PIXELS];
        render_vs2(10, expected, &scene);
        service_calls = 0;
        render_vs2_cooperative(10, actual, &scene, count_service);
        CHECK_EQ(service_calls, 2, "cooperative renderer service cadence");
        CHECK_EQ(memcmp(expected, actual, sizeof(expected)), 0,
                 "cooperative renderer preserves pixels");
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
        CHECK_EQ(render_led(&scene, 10, vs2_deepspace[40]), 10,
                 "layer mode overrides tilemap mode");
    }

    /* TUNNEL projection uses deepspace */
    {
        vs2_tilemap_t tilemap = default_tilemap();
        tilemap.mode = 1;
        const vs2_tilemap_t* records[] = { &tilemap };
        vs2_scene_t scene = tilemap_scene(records, 1);
        CHECK_EQ(render_led(&scene, 10, vs2_deepspace[40]), 10,
                 "TUNNEL projection");
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

    /* TUNNEL and HUD agree exactly at the rim, while FULLSCREEN y=0 reaches
     * that same outer LED and increasing Y contracts toward the center. */
    {
        vs2_sprite_t sprite = {
            .layer = 255, .image_strip = 10, .frame = 0, .mode = 1,
            .flags = 0x01, .x = 20 * 256, .y = 0,
        };
        const vs2_sprite_t* records[] = { &sprite };
        vs2_scene_t scene = {
            .layer_count = 0, .sprite_count = 1, .tilemap_count = 0,
            .layers = NULL, .sprites = records, .tilemaps = NULL,
        };
        CHECK_EQ(render_led(&scene, 20, PIXELS - 1), 10,
                 "TUNNEL y=0 outermost LED");
        sprite.mode = 2;
        CHECK_EQ(render_led(&scene, 20, PIXELS - 1), 10,
                 "HUD y=0 outermost LED");

        sprite.mode = 0;
        CHECK_EQ(render_led(&scene, 20, PIXELS - 1), 10,
                 "FULLSCREEN y=0 fully expanded");
        sprite.y = 255 * 256;
        CHECK_EQ(render_led(&scene, 20, 0), 10,
                 "FULLSCREEN y=255 reaches center");
        CHECK_EQ(render_led(&scene, 20, 1), 0,
                 "FULLSCREEN y=255 is one center LED");
    }

    /* Reads past a strip's registered length are transparent in all three
     * draw loops, while its real pixels still draw. */
    {
        vs2_sprite_t sprite = {
            .layer = 255, .image_strip = OVERDECLARED_SLOT, .frame = 0, .mode = 2,
            .flags = 0x01, .x = 30 * 256, .y = 40 * 256,
        };
        const vs2_sprite_t* records[] = { &sprite };
        vs2_scene_t scene = {
            .layer_count = 0, .sprite_count = 1, .tilemap_count = 0,
            .layers = NULL, .sprites = records, .tilemaps = NULL,
        };
        CHECK_EQ(render_led(&scene, 30, HUD_LED(40)), 20, "VS2 sprite registered frame draws");
        sprite.frame = 2;
        for (int column = 30; column < 34; column++) {
            for (int row = 40; row < 44; row++) {
                CHECK_EQ(render_led(&scene, column, HUD_LED(row)), 0,
                         "VS2 sprite never draws past its strip");
            }
        }
        sprite.mode = 0;
        CHECK_EQ(render_led(&scene, 30, PIXELS - 1), 0, "FULLSCREEN sprite never draws past its strip");
    }
    {
        static const uint8_t frames[4] = { 2, 1, 0, 255 };
        vs2_tilemap_t tilemap = default_tilemap();
        tilemap.image_strip = OVERDECLARED_SLOT;
        tilemap.frames = frames;
        const vs2_tilemap_t* records[] = { &tilemap };
        vs2_scene_t scene = tilemap_scene(records, 1);
        for (int column = 10; column < 18; column++) {
            for (int row = 40; row < 44; row++) {
                CHECK_EQ(render_led(&scene, column, HUD_LED(row)), 0,
                         "tilemap never draws past its strip");
            }
        }
        CHECK_EQ(render_led(&scene, 10, HUD_LED(44)), 20, "tilemap registered frame draws");
        tilemap.flags |= 0x04;
        CHECK_EQ(render_led(&scene, 10, HUD_LED(40)), 20, "flipped tilemap registered frame draws");
        CHECK_EQ(render_led(&scene, 10, HUD_LED(44)), 0, "flipped tilemap never draws past its strip");
    }
    {
        bool saved_starfield = starfield_enabled;
        starfield_enabled = false;
        sprite_obj_t legacy = {0};
        legacy.x = 30;
        legacy.y = 40;
        legacy.frame = 0;
        legacy.perspective = 2;
        legacy.image_strip = image_stripes[OVERDECLARED_SLOT];
        legacy.image_strip_length = image_strip_lengths[OVERDECLARED_SLOT];
        sprites[1] = &legacy;
        uint32_t led_buffer[PIXELS];
        render(30, led_buffer);
        CHECK_EQ(led_buffer[HUD_LED(40)] >> 24, 20, "V1 sprite registered frame draws");
        legacy.frame = 2;
        for (int column = 30; column < 34; column++) {
            render(column, led_buffer);
            for (int n = 0; n < PIXELS; n++) {
                CHECK_EQ(led_buffer[n] >> 24, 0, "V1 sprite never draws past its strip");
            }
        }
        legacy.perspective = 0;
        render(30, led_buffer);
        for (int n = 0; n < PIXELS; n++) {
            CHECK_EQ(led_buffer[n] >> 24, 0, "V1 FULLSCREEN sprite never draws past its strip");
        }
        sprites[1] = NULL;
        starfield_enabled = saved_starfield;
    }

    /* Width and frame count decode the same way at every value, the full
     * circle and a 256-glyph font included: no special case for 255. */
    {
        static uint8_t header[4];
        const ImageStrip* strip = (const ImageStrip*)header;
        header[0] = 254;
        header[2] = 254;
        CHECK_EQ(strip_frame_width(strip), 255, "width byte 254 is 255 wide");
        CHECK_EQ(strip_total_frames(strip), 255, "frames byte 254 is 255 frames");
        header[0] = 255;
        header[2] = 255;
        CHECK_EQ(strip_frame_width(strip), 256, "width byte 255 is the full circle");
        CHECK_EQ(strip_total_frames(strip), 256, "frames byte 255 is 256 frames");
        header[0] = 0;
        header[2] = 0;
        CHECK_EQ(strip_frame_width(strip), 1, "width byte 0 is 1 wide");
        CHECK_EQ(strip_total_frames(strip), 1, "frames byte 0 is 1 frame");
    }

    /* A 255-wide strip draws 255 columns and a 256-wide one all 256; the
     * column a 255-wide strip lacks stays dark instead of reading past it. */
    {
        static uint8_t wide[2][4 + 256 * 2];
        for (int n = 0; n < 2; n++) {
            int strip_width = 255 + n;
            wide[n][0] = (uint8_t)(strip_width - 1);
            wide[n][1] = 2;
            wide[n][2] = 0;
            wide[n][3] = 0;
            memset(wide[n] + 4, 3, (size_t)strip_width * 2);
            register_strip(12 + n, wide[n], (uint32_t)(4 + strip_width * 2));
        }
        memset(wide[0] + 4 + 255 * 2, 5, 2);  /* canary where a 256th column would be */
        for (int n = 0; n < 2; n++) {
            vs2_sprite_t sprite = {
                .layer = 255, .image_strip = (uint8_t)(12 + n), .frame = 0, .mode = 2,
                .flags = 0x01, .x = 0, .y = 40 * 256,
            };
            const vs2_sprite_t* records[] = { &sprite };
            vs2_scene_t scene = {
                .layer_count = 0, .sprite_count = 1, .tilemap_count = 0,
                .layers = NULL, .sprites = records, .tilemaps = NULL,
            };
            int lit = 0;
            for (int column = 0; column < 256; column++) {
                uint32_t marker = render_led(&scene, column, HUD_LED(40));
                CHECK_EQ(marker == 0 || marker == 30, 1, "wide strip draws only its own pixels");
                lit += marker == 30;
            }
            CHECK_EQ(lit, 255 + n, "wide strip lights exactly its width");
        }
    }

    if (failures) {
        printf("render_vs2 host tests: %d failure(s)\n", failures);
        return 1;
    }
    printf("render_vs2 host tests passed\n");
    return 0;
}
