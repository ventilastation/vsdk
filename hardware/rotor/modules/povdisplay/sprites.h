#include <stdint.h>

typedef struct {
    const uint8_t frame_width;
    const uint8_t frame_height;
    const uint8_t total_frames;
    const uint8_t palette;
    const uint8_t data[];
} ImageStrip;

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
