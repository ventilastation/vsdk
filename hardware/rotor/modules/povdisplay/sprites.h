#include <stdint.h>

/* A strip's header, as written by tools/generate_roms.py (see
 * docs/internals/rom-format.md). Width and frame count run 1..256 and are
 * stored minus one, so read them only through strip_frame_width() and
 * strip_total_frames(): the field names make a direct read stand out.
 * Height is stored as is. */
typedef struct {
    const uint8_t frame_width_minus_1;
    const uint8_t frame_height;
    const uint8_t total_frames_minus_1;
    const uint8_t palette;
    const uint8_t data[];
} ImageStrip;

static inline int strip_frame_width(const ImageStrip* strip) {
    return strip->frame_width_minus_1 + 1;
}

static inline int strip_total_frames(const ImageStrip* strip) {
    return strip->total_frames_minus_1 + 1;
}

typedef struct _sprite_obj_t {
    mp_obj_base_t   base;
    uint8_t x;
    uint8_t y;
    uint8_t frame;
    const ImageStrip* image_strip;
    uint32_t image_strip_length;  // pixel bytes behind image_strip, see image_strip_lengths
    int8_t perspective;
    uint8_t sprite_id;
} sprite_obj_t;

#define NUM_SPRITES 100
extern sprite_obj_t* sprites[NUM_SPRITES];

#define NUM_IMAGES 100
extern const ImageStrip* image_stripes[NUM_IMAGES];
/* Bytes of pixel data registered behind each strip: its buffer minus the
 * 4-byte header. The renderers never read past this, whatever the header
 * claims, so a stale or corrupt ROM (or a frame number beyond the strip's)
 * draws transparent pixels instead of whatever memory follows the strip. */
extern uint32_t image_strip_lengths[NUM_IMAGES];

static const uint8_t DISABLED_FRAME = 255;
