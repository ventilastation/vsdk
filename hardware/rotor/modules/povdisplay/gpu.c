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

int get_visible_column(int sprite_x, int sprite_width, int render_column) {
    int sprite_column = sprite_width - 1 - (render_column - sprite_x + COLUMNS) % COLUMNS;
    if (0 <= sprite_column && sprite_column < sprite_width) {
        return sprite_column;
    } else {
        return -1;
    }
}


void render(int column, uint32_t* pixels) {
  uint32_t colorbuf[PIXELS];


  inline void set_pixel(uint8_t n, uint32_t color) {
    if (n < PIXELS) {
      colorbuf[n] = color;
    }
  }

  inline void finish_nogamma() {
    for (int n=0; n<PIXELS; n++) {
      uint32_t color = colorbuf[n];
      pixels[n] = 0xff |
        intensidades[n][(color & 0xff000000) >> 24] << 24 |
        intensidades[n][(color & 0x00ff0000) >> 16] << 16 |
        intensidades[n][(color & 0x0000ff00) >>  8] <<  8;
    }
  }

  inline void finish_with_gamma() {
    for (int n=0; n<PIXELS; n++) {
      uint32_t color = colorbuf[n];
      int alt_n = intensidades_por_led[n];
      pixels[n] = (brillos[n] & 0x1f) | 0xe0 |
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
    if(is < 1000) {
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

        for(int y=desde; y<hasta; y++, imagen++) {
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
