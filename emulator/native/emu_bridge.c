/* ctypes-facing entry points wrapping the real hardware VS2 renderer
 * (gpu.c's render_vs2(), the same code exercised by
 * tests/native/test_render_vs2.c) for the desktop emulator.
 *
 * gpu.c expects a handful of globals normally supplied by intensidades.c /
 * povdisplay.c on real firmware. We provide identity/pass-through versions
 * here so finish_colorbuf() in gpu.c leaves palette colors unchanged --
 * matching the desktop preview's existing behavior of applying no gamma
 * correction of its own.
 */
#include <stdlib.h>
#include <string.h>

#include "vs2_wire.h" /* pulls in gpu.h; gpu.h/sprites.h have no include guards */

/* Not declared in gpu.h (only render_vs2() is); all four are defined in
 * gpu.c with external linkage. render() is the pre-VS2 fixed 100-sprite-slot
 * renderer -- still what most existing games (and the menu) actually use. */
void init_sprites(void);
void step_starfield(void);
void render(int column, uint32_t* led_buffer);

uint8_t intensidades[PIXELS][256];
uint8_t brillos[PIXELS];
uint8_t intensidades_por_led[PIXELS];

static uint32_t* g_palette = NULL;
static size_t g_palette_count = 0;

static vs2_wire_scene_t g_scene;
static bool g_scene_active = false;

/* Pre-VS2 fixed sprite table: sprite_obj_t.image_strip is a resolved
 * pointer rather than an index (unlike vs2_sprite_t), so it's re-resolved
 * from image_stripes[] on every render to reflect the latest imagestrip
 * regardless of the order "sprites" and "imagestrip" wire commands arrive
 * in -- matching the Python renderer's fresh all_strips.get() lookup on
 * every call instead of caching it at sprite-set time. */
static sprite_obj_t legacy_sprites[NUM_SPRITES];
static uint8_t legacy_sprite_image_index[NUM_SPRITES];
static bool legacy_sprites_valid = false;

void emu_gpu_init(void) {
    for (int led = 0; led < PIXELS; led++) {
        for (int v = 0; v < 256; v++) {
            intensidades[led][v] = (uint8_t)v;
        }
        intensidades_por_led[led] = (uint8_t)led;
        brillos[led] = 0x1f;
    }
    gamma_mode = 0;
    memset(image_stripes, 0, sizeof(image_stripes));
    init_sprites(); /* seeds starfield + calculates deepspace[] */
}

void emu_gpu_step_starfield(void) {
    step_starfield();
}

/* `data` is the raw wire palette payload: 4 bytes per entry, [A, B, G, R]
 * (confirmed empirically: every real entry has byte 0 == 0xff, i.e. it's an
 * alpha-first preview color -- povrender.upalette[i] ends up 0xAABBGGRR
 * after change_colors()+unpack_palette()'s double byte swap). gpu.c's own
 * pipeline (finish_colorbuf(), color_pipeline_encode_rgb()) expects the
 * opposite layout -- R at bits 24-31, G at 16-23, B at 8-15, since its
 * output feeds a real APA102 SPI word ([GB, B, G, R] in memory, per
 * color_pipeline_encode_rgb's doc comment) -- so this reverses the byte
 * order on the way in; emu_gpu_render_frame()/emu_gpu_render_legacy_frame()
 * reverse it back on the way out to reproduce the desktop preview's own
 * 0xAABBGGRR convention. */
bool emu_gpu_set_palette(const uint8_t* data, int length) {
    size_t count = (size_t)length / 4;
    uint32_t* buf = (uint32_t*)malloc(count * sizeof(uint32_t));
    if (buf == NULL) {
        return false;
    }
    for (size_t i = 0; i < count; i++) {
        const uint8_t* p = data + i * 4;
        buf[i] = ((uint32_t)p[3] << 24) | ((uint32_t)p[2] << 16) | ((uint32_t)p[1] << 8) | (uint32_t)p[0];
    }
    free(g_palette);
    g_palette = buf;
    g_palette_count = count;
    palette_pal = g_palette;
    return true;
}

/* Zero-copy: ImageStrip's layout (frame_width, frame_height, total_frames,
 * palette, then raw pixel data) is byte-identical to the wire strip blob
 * already stored in povrender.all_strips, so this just casts the pointer.
 * `data` must stay alive for as long as the slot is installed -- the Python
 * side keeps the originating bytes object in all_strips permanently. */
bool emu_gpu_set_image_strip(int slot, const uint8_t* data) {
    if (slot < 0 || slot >= NUM_IMAGES) {
        return false;
    }
    image_stripes[slot] = (const ImageStrip*)data;
    return true;
}

void emu_gpu_clear_image_strip(int slot) {
    if (slot < 0 || slot >= NUM_IMAGES) {
        return;
    }
    image_stripes[slot] = NULL;
}

/* `data` must stay alive for as long as this scene is active: tilemap frame
 * tables are borrowed pointers into it (see vs2_wire.h). */
bool emu_gpu_decode_scene(const uint8_t* data, int len) {
    g_scene_active = vs2_wire_decode_scene(data, (size_t)len, &g_scene);
    return g_scene_active;
}

void emu_gpu_clear_scene(void) {
    g_scene_active = false;
}

/* Reverses emu_gpu_set_palette()'s byte order flip: gpu.c's led_buffer has R
 * at bits 24-31 (its APA102-word convention), the desktop preview wants
 * 0xAABBGGRR (alpha at 24-31, matching povrender.upalette / the apa102.py
 * decode path). The forced low byte in gamma_mode==0 (see finish_colorbuf())
 * is always 0xff, which is exactly the alpha this format needs. */
static inline uint32_t to_preview_pixel(uint32_t v) {
    uint32_t r = (v >> 24) & 0xffu;
    uint32_t g = (v >> 16) & 0xffu;
    uint32_t b = (v >> 8) & 0xffu;
    return 0xff000000u | (b << 16) | (g << 8) | r;
}

/* Renders all 256 columns of the VS2-scene path into `out_pixels`
 * (COLUMNS * PIXELS uint32_t entries). */
void emu_gpu_render_frame(uint32_t* out_pixels) {
    uint32_t column_buf[PIXELS];
    const vs2_scene_t* scene = g_scene_active ? &g_scene.scene : NULL;
    for (int column = 0; column < 256; column++) {
        render_vs2(column, column_buf, scene);
        uint32_t* dest = out_pixels + (size_t)column * PIXELS;
        for (int n = 0; n < PIXELS; n++) {
            dest[n] = to_preview_pixel(column_buf[n]);
        }
    }
}

/* `data` is 5 bytes * NUM_SPRITES: x, y, image_strip_index, frame,
 * perspective (signed) per slot -- the same layout as povrender.spritedata,
 * as sent by the "sprites" wire command. */
void emu_gpu_set_legacy_sprites(const uint8_t* data) {
    for (int i = 0; i < NUM_SPRITES; i++) {
        const uint8_t* p = data + i * 5;
        sprite_obj_t* s = &legacy_sprites[i];
        s->x = p[0];
        s->y = p[1];
        legacy_sprite_image_index[i] = p[2];
        s->frame = p[3];
        s->perspective = (int8_t)p[4];
        sprites[i] = s;
    }
    legacy_sprites_valid = true;
}

/* Renders all 256 columns of the pre-VS2 fixed 100-sprite-slot path into
 * `out_pixels` (COLUMNS * PIXELS uint32_t entries). */
void emu_gpu_render_legacy_frame(uint32_t* out_pixels) {
    if (legacy_sprites_valid) {
        for (int i = 0; i < NUM_SPRITES; i++) {
            uint8_t idx = legacy_sprite_image_index[i];
            legacy_sprites[i].image_strip = (idx < NUM_IMAGES) ? image_stripes[idx] : NULL;
        }
    }
    uint32_t column_buf[PIXELS];
    for (int column = 0; column < 256; column++) {
        render(column, column_buf);
        uint32_t* dest = out_pixels + (size_t)column * PIXELS;
        for (int n = 0; n < PIXELS; n++) {
            dest[n] = to_preview_pixel(column_buf[n]);
        }
    }
}
