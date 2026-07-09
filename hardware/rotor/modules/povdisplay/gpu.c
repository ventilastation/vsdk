#include <math.h>
#include <stdint.h>
#include <esp_system.h>
#include "gpu.h"

// static const char* TAG = "GPU";
// #define LOG_LOCAL_LEVEL ESP_LOG_VERBOSE
// #include "esp_log.h"

#define COLUMNS 256
#define PIXELS 54
#define ROWS 256
#define VS2_FLAG_VISIBLE 0x01
#define VS2_FLAG_FLIP_X 0x02
#define VS2_FLAG_FLIP_Y 0x04
#define VS2_MODE_FULLSCREEN 0
#define VS2_NO_LAYER 255

const uint8_t TRANSPARENT = 0xFF;
uint8_t deepspace[ROWS];
sprite_obj_t* sprites[NUM_SPRITES];
extern const uint8_t intensidades[PIXELS][256];
extern uint8_t brillos[PIXELS];
extern uint8_t intensidades_por_led[PIXELS];
int gamma_mode;

uint32_t* palette_pal;
const ImageStrip* image_stripes[NUM_IMAGES];

#define STARS COLUMNS/2

typedef struct {
  uint8_t x;
  uint8_t y;
} Star;
Star starfield[STARS];


// Romu Pseudorandom Number Generators
//
// Copyright 2020 Mark A. Overton
#define ROTL(d,lrot) ((d<<(lrot)) | (d>>(8*sizeof(d)-(lrot))))

//===== RomuMono32 ===============================================================================
//
// 32-bit arithmetic: Suitable only up to 2^26 output-values. Outputs 16-bit numbers.
// Fixed period of (2^32)-47. Must be seeded using the romuMono32_init function.
// Capacity = 2^27 bytes. Register pressure = 2. State size = 32 bits.

uint32_t state;

void romuMono32_init (uint32_t seed) {
   state = (seed & 0x1fffffffu) + 1156979152u;  // Accepts 29 seed-bits.
}

uint16_t romuMono32_random () {
   uint16_t result = state >> 16;
   state *= 3611795771u;  state = ROTL(state,12);
   return result;
}


int rand_int(int max) {
    return romuMono32_random() % max;
}

void calculate_deepspace() {
  const int EMPTY_PIXELS = 16;
  const int VISIBLE_ROWS = ROWS - EMPTY_PIXELS;
  const double GAMMA = 0.28;

  int n;
  for (n=0; n<EMPTY_PIXELS; n++) {
    deepspace[n] = PIXELS;
  }

  for (int j=VISIBLE_ROWS-1; j>-1; j--) { 
    deepspace[n++] = PIXELS * pow((double)j / VISIBLE_ROWS, 1/GAMMA) + 0.5;
  }
}

void init_sprites() {

  calculate_deepspace();

  romuMono32_init(esp_random());
  for (int f = 0; f<STARS; f++) {
    starfield[f].x = rand_int(COLUMNS);
    starfield[f].y = rand_int(ROWS);
  }


  for (int i = 0; i < NUM_SPRITES; i++) {
    sprites[i] = NULL;
  }

}

void step_starfield() {
  for (int f=0; f<STARS; f++) {
    if(--starfield[f].y == 0) {
      starfield[f].y = ROWS-1;
      starfield[f].x = rand_int(COLUMNS);
    }
  }
}

static int wrap_column_delta(int value) {
    int wrapped = value % COLUMNS;
    if (wrapped < 0) {
      wrapped += COLUMNS;
    }
    return wrapped;
}

int get_visible_column(int sprite_x, int sprite_width, int render_column) {
    int sprite_column = sprite_width - 1 - wrap_column_delta(render_column - sprite_x);
    if (0 <= sprite_column && sprite_column < sprite_width) {
        return sprite_column;
    } else {
        return -1;
    }
}

static int clamp_int(int value, int minimum, int maximum) {
  if (value < minimum) return minimum;
  if (value > maximum) return maximum;
  return value;
}

static int fixed_floor_to_int(int32_t value) {
  if (value >= 0) {
    return value / 256;
  }
  return -(((-value) + 255) / 256);
}

static int get_source_column(int sprite_x, int sprite_width, int render_column, bool flip_x) {
  int sprite_column = get_visible_column(sprite_x, sprite_width, render_column);
  if (sprite_column == -1) {
    return -1;
  }
  if (flip_x) {
    return sprite_width - 1 - sprite_column;
  }
  return sprite_column;
}

static void set_colorbuf_pixel(uint32_t* colorbuf, int n, uint32_t color) {
  if (0 <= n && n < PIXELS) {
    colorbuf[n] = color;
  }
}

static void finish_colorbuf(uint32_t* colorbuf, uint32_t* led_buffer) {
  if (gamma_mode == 0) {
    for (int n=0; n<PIXELS; n++) {
      uint32_t color = colorbuf[n];
      led_buffer[n] = 0xff |
        intensidades[n][(color & 0xff000000) >> 24] << 24 |
        intensidades[n][(color & 0x00ff0000) >> 16] << 16 |
        intensidades[n][(color & 0x0000ff00) >>  8] <<  8;
    }
  } else {
    for (int n=0; n<PIXELS; n++) {
      uint32_t color = colorbuf[n];
      int alt_n = intensidades_por_led[n];
      led_buffer[n] = (brillos[n] & 0x1f) | 0xe0 |
        intensidades[alt_n][(color & 0xff000000) >> 24] << 24 |
        intensidades[alt_n][(color & 0x00ff0000) >> 16] << 16 |
        intensidades[alt_n][(color & 0x0000ff00) >>  8] <<  8;
    }
  }
}

static bool vs2_layer_visible(const vs2_scene_t* scene, const vs2_sprite_t* sprite) {
  if (sprite->layer == VS2_NO_LAYER || sprite->layer >= scene->layer_count || scene->layers == NULL) {
    return true;
  }
  const vs2_layer_t* layer = scene->layers[sprite->layer];
  if (layer == NULL) {
    return true;
  }
  return (layer->flags & VS2_FLAG_VISIBLE) != 0;
}

static uint8_t vs2_sprite_mode(const vs2_scene_t* scene, const vs2_sprite_t* sprite) {
  if (sprite->layer == VS2_NO_LAYER || sprite->layer >= scene->layer_count || scene->layers == NULL) {
    return sprite->mode;
  }
  const vs2_layer_t* layer = scene->layers[sprite->layer];
  if (layer == NULL) {
    return sprite->mode;
  }
  return layer->mode;
}

void render_vs2(int column, uint32_t* led_buffer, const vs2_scene_t* scene) {
  uint32_t colorbuf[PIXELS];

  column = column % COLUMNS;
  for (int y=0; y<PIXELS; y++) {
    colorbuf[y] = 0x000000ff;
  }
  for (int f=0; f<STARS; f++) {
    if (starfield[f].x == column) {
      set_colorbuf_pixel(colorbuf, deepspace[starfield[f].y], 0x808080ff);
    }
  }

  if (scene == NULL || scene->sprites == NULL) {
    finish_colorbuf(colorbuf, led_buffer);
    return;
  }

  for (int n=scene->sprite_count - 1; n>=0; n--) {
    const vs2_sprite_t* s = scene->sprites[n];
    if (s == NULL) {
      continue;
    }
    if ((s->flags & VS2_FLAG_VISIBLE) == 0 || !vs2_layer_visible(scene, s)) {
      continue;
    }
    if (s->image_strip >= NUM_IMAGES) {
      continue;
    }
    const ImageStrip* is = image_stripes[s->image_strip];
    if ((uintptr_t)is < 1000) {
      continue;
    }

    uint32_t* current_palette = palette_pal + 256 * is->palette;
    int width = is->frame_width;
    if (width == 255) width++;
    int visible_column = get_source_column(
      fixed_floor_to_int(s->x),
      width,
      column,
      (s->flags & VS2_FLAG_FLIP_X) != 0
    );
    if (visible_column == -1) {
      continue;
    }

    uint8_t height = is->frame_height;
    uint8_t total_frames = is->total_frames ? is->total_frames : 1;
    uint8_t frame = s->frame % total_frames;
    uint8_t mode = vs2_sprite_mode(scene, s);
    int sprite_y = fixed_floor_to_int(s->y);
    int base = visible_column * height + (frame * width * height);

    if(mode != VS2_MODE_FULLSCREEN) {
      int desde = MAX(sprite_y, 0);
      int hasta = MIN(sprite_y + height, ROWS);

      for(int y = desde; y < hasta; y++) {
        int source_row = y - sprite_y;
        if ((s->flags & VS2_FLAG_FLIP_Y) != 0) {
          source_row = height - 1 - source_row;
        }
        uint8_t color = is->data[base + source_row];
        if (color != TRANSPARENT) {
          int px_y = mode == 1 ? deepspace[y] : PIXELS - 1 - y;
          set_colorbuf_pixel(colorbuf, px_y, current_palette[color]);
        }
      }
    } else {
      int zleds = deepspace[clamp_int(255 - sprite_y, 0, ROWS - 1)];
      for (int led=0; led < zleds; led++) {
        int source_row = led * PIXELS / zleds;
        if (source_row >= height) {
          break;
        }
        if ((s->flags & VS2_FLAG_FLIP_Y) == 0) {
          source_row = height - 1 - source_row;
        }
        uint8_t color = is->data[base + source_row];
        if (color != TRANSPARENT) {
          set_colorbuf_pixel(colorbuf, led, current_palette[color]);
        }
      }
    }
  }

  finish_colorbuf(colorbuf, led_buffer);
}


void render(int column, uint32_t* led_buffer) {
  uint32_t colorbuf[PIXELS];


  inline void set_pixel(uint8_t n, uint32_t color) {
    if (n < PIXELS) {
      colorbuf[n] = color;
    }
  }

  inline void finish_nogamma() {
    for (int n=0; n<PIXELS; n++) {
      uint32_t color = colorbuf[n];
      led_buffer[n] = 0xff |
        intensidades[n][(color & 0xff000000) >> 24] << 24 |
        intensidades[n][(color & 0x00ff0000) >> 16] << 16 |
        intensidades[n][(color & 0x0000ff00) >>  8] <<  8;
    }
  }

  inline void finish_with_gamma() {
    for (int n=0; n<PIXELS; n++) {
      uint32_t color = colorbuf[n];
      int alt_n = intensidades_por_led[n];
      led_buffer[n] = (brillos[n] & 0x1f) | 0xe0 |
        intensidades[alt_n][(color & 0xff000000) >> 24] << 24 |
        intensidades[alt_n][(color & 0x00ff0000) >> 16] << 16 |
        intensidades[alt_n][(color & 0x0000ff00) >>  8] <<  8;
    }
  }

  column = column % COLUMNS;
  for (int y=0; y<PIXELS; y++) {
    colorbuf[y] = 0x000000ff;
  }
  for (int f=0; f<STARS; f++) {
    if (starfield[f].x == column) {
      set_pixel(deepspace[starfield[f].y], 0x808080ff);
    }
  }

  // el sprite 0 se dibuja arriba de todos los otros
  for (int n=NUM_SPRITES-1; n>=0; n--) {
    sprite_obj_t* s = sprites[n%NUM_SPRITES];
    if (s == NULL || s->frame == DISABLED_FRAME) {
      continue;
    }
    const ImageStrip* is = s->image_strip;
    if ((uintptr_t)is < 1000) {
      // ESP_LOGD(TAG, "BUG en gpu render=%p", s);
      // ESP_LOGD(TAG, "           n=%d", n);
      // ESP_LOGD(TAG, "           imagestrip=%p", is);
      // ESP_LOGD(TAG, "           frame=%d", s->frame);
      continue;
    }
    uint32_t* current_palette = palette_pal + 256 * is->palette;
    int width = is->frame_width;
    if (width == 255) width++; // caso especial, para los planetas
    int visible_column = get_visible_column(s->x, width, column);
    if (visible_column != -1) {
      uint8_t height = is->frame_height;
      int base = visible_column * height + (s->frame * width * height);
      if(s->perspective) {
        int desde = MAX(s->y, 0);
        int hasta = MIN(s->y + height, ROWS-1);
        int comienzo = MAX(-s->y, 0);
        const uint8_t* imagen = is->data + base + comienzo;

        for(int y = desde; y < hasta; y++, imagen++) {
          uint8_t color = *imagen;
          if (color != TRANSPARENT) {
            int px_y;
            if (s->perspective == 1) {
              px_y = deepspace[y];
            } else {
              px_y = PIXELS - 1 - y;
            }
            set_pixel(px_y, current_palette[color]);
          }
        }
      } else {
        int zleds = deepspace[255 - s->y];
        for (int led=0; led < zleds; led++) {
          int src = led * PIXELS / zleds;
          if (src >= height) {
            break;
          }
          uint8_t color = is->data[base + height - 1 - src];
          if (color != TRANSPARENT) {
            set_pixel(led, current_palette[color]);
          }
        }
      }
    }
  }

  if (gamma_mode == 0) {
    finish_nogamma();
  } else {
    finish_with_gamma();
  }

}
