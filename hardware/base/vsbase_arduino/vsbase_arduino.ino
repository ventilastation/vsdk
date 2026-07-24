#include <Servo.h>
#include <Adafruit_NeoPixel.h>
#include <limits.h>
#include <string.h>

// Pin and mechanical calibration are deliberately private to this firmware.
#define NEO_PIN 7
#define LUZ_BOTON_1 2
#define LUZ_BOTON_2 3
#define SERVO_PIN 10
#define NUM_PIXELS 16
#define SERVO_SAFE_REST_DEG 106
#define SERVO_SAFE_FULL_DEG 13
#define MIN_BLINK_MS 100UL
#define MAX_BLINK_MS 10000UL
#define COMMAND_MAX 48

// No git-hash injection for this build (no existing Arduino build
// automation to hook a codegen step into, unlike the two ESP-IDF/CMake
// firmwares) -- hand-bump FIRMWARE_VERSION when this sketch changes.
#define FIRMWARE_VERSION "v1.1"
#define FIRMWARE_GIT_HASH "unknown"

Adafruit_NeoPixel pixels(NUM_PIXELS, NEO_PIN, NEO_GRB + NEO_KHZ800);
Servo servo;

uint8_t strip_red = 0, strip_green = 0, strip_blue = 0;
uint8_t servo_position = 0;
uint8_t button_mask = 0;
unsigned long button_blink_ms = 0;
char command_buffer[COMMAND_MAX + 1];
uint8_t command_length = 0;

// RESYNC / device identification (see
// docs/internals/input-protocol-v2.md#resync--device-identification).
// Mirrors input_parser.py's _RESYNC_SEQUENCE byte-for-byte.
const uint8_t RESYNC_SEQUENCE[] = { '\n', '\n', 0xD2, 'E', 'S', 'Y', 'N', 'C', '\n' };
const uint8_t RESYNC_LEN = sizeof(RESYNC_SEQUENCE);
uint8_t resync_match = 0;

// Super Ventilagon's original relay protocol: `ventilagon start`/`stop`/
// `reset`/`attract` lines (see docs/internals/host-protocol.md's
// `arduino <cmd>` entry and comms.py's _arduino_commands/arduino_send()),
// parsed by handle_command() the same way as `base ...` below. This
// self-contained light+servo show is driven straight off
// servo_position/button_mask/button_blink_ms (the same state `base servo`/
// `base buttons` use) to keep one source of truth, but paints the strip
// with its own untouched colors instead of going through apply_strip()'s
// gamma table, to reproduce the original show byte-for-byte.
#define CENTISECONDS (10UL)  // in milliseconds
unsigned long legacy_section_durations[] = {
  1325 * CENTISECONDS,
  1325 * CENTISECONDS,
  1325 * CENTISECONDS,
  1325 * CENTISECONDS,
  1325 * 2 * CENTISECONDS,
  1325 * 3 * CENTISECONDS,
  ULONG_MAX,
};
uint32_t legacy_colors[] = {
  0x0000ff,
  0x00ff00,
  0xffff00,
  0x00ffff,
  0xff00ff,
  0xff0000,
  0x000000,
};
bool legacy_timer_running = false;
uint8_t legacy_section = 0;
unsigned long legacy_section_init_time = 0;
unsigned long legacy_section_duration = legacy_section_durations[0];

// Doom palette values target a gamma-corrected monitor. WS2812 PWM is close
// to linear, so use this 2.2 transfer curve before driving the physical strip.
const uint8_t base_gamma_22[256] PROGMEM = {
  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1,
  1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2,
  3, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6,
  6, 7, 7, 7, 8, 8, 8, 9, 9, 9, 10, 10, 11, 11, 11, 12,
  12, 13, 13, 13, 14, 14, 15, 15, 16, 16, 17, 17, 18, 18, 19, 19,
  20, 20, 21, 22, 22, 23, 23, 24, 25, 25, 26, 26, 27, 28, 28, 29,
  30, 30, 31, 32, 33, 33, 34, 35, 35, 36, 37, 38, 39, 39, 40, 41,
  42, 43, 43, 44, 45, 46, 47, 48, 49, 49, 50, 51, 52, 53, 54, 55,
  56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71,
  73, 74, 75, 76, 77, 78, 79, 81, 82, 83, 84, 85, 87, 88, 89, 90,
  91, 93, 94, 95, 97, 98, 99, 100, 102, 103, 105, 106, 107, 109, 110, 111,
  113, 114, 116, 117, 119, 120, 121, 123, 124, 126, 127, 129, 130, 132, 133, 135,
  137, 138, 140, 141, 143, 145, 146, 148, 149, 151, 153, 154, 156, 158, 159, 161,
  163, 165, 166, 168, 170, 172, 173, 175, 177, 179, 181, 182, 184, 186, 188, 190,
  192, 194, 196, 197, 199, 201, 203, 205, 207, 209, 211, 213, 215, 217, 219, 221,
  223, 225, 227, 229, 231, 234, 236, 238, 240, 242, 244, 246, 248, 251, 253, 255,
};

void apply_strip() {
  uint32_t color = pixels.Color(pgm_read_byte(&base_gamma_22[strip_red]),
                                pgm_read_byte(&base_gamma_22[strip_green]),
                                pgm_read_byte(&base_gamma_22[strip_blue]));
  for (uint8_t index = 0; index < NUM_PIXELS; ++index) {
    pixels.setPixelColor(index, color);
  }
  pixels.show();
}

void apply_servo() {
  // 0 -> rest, 255 -> full. Both endpoints have been measured safe locally.
  long degrees = SERVO_SAFE_REST_DEG +
    ((long)(SERVO_SAFE_FULL_DEG - SERVO_SAFE_REST_DEG) * servo_position) / 255;
  servo.write((int)degrees);
}

void legacy_set_strip_raw(uint32_t color) {
  for (uint8_t index = 0; index < NUM_PIXELS; ++index) {
    pixels.setPixelColor(index, color);
  }
  pixels.show();
}

void legacy_buttons_on() {
  button_mask = 0x03;
  button_blink_ms = 512;  // matches the original firmware's (millis() >> 8) & 1 blink rate
}

void legacy_buttons_off() {
  button_mask = 0;
  button_blink_ms = 0;
}

void legacy_update_servo_value(unsigned long value, unsigned long max_val) {
  servo_position = (uint8_t)map(value, 0, max_val, 0, 255);
  apply_servo();
}

void legacy_start_timer() {
  legacy_timer_running = true;
  legacy_section = 0;
  legacy_section_init_time = millis();
  legacy_section_duration = legacy_section_durations[0];
  legacy_set_strip_raw(legacy_colors[0]);
  legacy_buttons_off();
}

void legacy_stop_timer() {
  legacy_timer_running = false;
  legacy_buttons_on();
}

void legacy_stop_no_leds() {
  legacy_timer_running = false;
  legacy_set_strip_raw(0);
  legacy_buttons_off();
}

void legacy_reset_all() {
  legacy_timer_running = false;
  legacy_set_strip_raw(0);
  legacy_update_servo_value(0, 255);
  legacy_section = 0;
  legacy_buttons_on();
}

void legacy_advance_section(unsigned long now) {
  legacy_section++;
  legacy_section_init_time = now;
  legacy_section_duration = legacy_section_durations[legacy_section];
  legacy_set_strip_raw(legacy_colors[legacy_section]);
}

void legacy_check_timer() {
  if (!legacy_timer_running) return;
  unsigned long now = millis();
  if (now - legacy_section_init_time > legacy_section_duration) {
    legacy_advance_section(now);
  }
  if (legacy_section_duration != ULONG_MAX) {
    legacy_update_servo_value(now - legacy_section_init_time, legacy_section_duration);
  }
}

bool parse_uint(const char *text, unsigned long *value) {
  if (!text || !*text) return false;
  unsigned long result = 0;
  for (; *text; ++text) {
    if (*text < '0' || *text > '9') return false;
    result = result * 10 + (unsigned long)(*text - '0');
    if (result > 100000UL) return false;
  }
  *value = result;
  return true;
}

void handle_command(char *line) {
  char *save = NULL;
  char *prefix = strtok_r(line, " ", &save);
  char *kind = strtok_r(NULL, " ", &save);
  if (!prefix || !kind) return;

  if (strcmp(prefix, "ventilagon") == 0) {
    if (strtok_r(NULL, " ", &save)) return;  // no arguments taken
    if (strcmp(kind, "start") == 0) legacy_start_timer();
    else if (strcmp(kind, "stop") == 0) legacy_stop_no_leds();
    else if (strcmp(kind, "reset") == 0) legacy_reset_all();
    else if (strcmp(kind, "attract") == 0) legacy_stop_timer();
    return;
  }

  if (strcmp(prefix, "base") != 0) return;

  if (strcmp(kind, "leds") == 0) {
    char *r = strtok_r(NULL, " ", &save);
    char *g = strtok_r(NULL, " ", &save);
    char *b = strtok_r(NULL, " ", &save);
    unsigned long red, green, blue;
    if (strtok_r(NULL, " ", &save) || !parse_uint(r, &red) || !parse_uint(g, &green) ||
        !parse_uint(b, &blue) || red > 255 || green > 255 || blue > 255) return;
    if (strip_red != red || strip_green != green || strip_blue != blue) {
      strip_red = (uint8_t)red; strip_green = (uint8_t)green; strip_blue = (uint8_t)blue;
      apply_strip();
    }
  } else if (strcmp(kind, "servo") == 0) {
    char *position = strtok_r(NULL, " ", &save);
    unsigned long value;
    if (strtok_r(NULL, " ", &save) || !parse_uint(position, &value) || value > 255) return;
    if (servo_position != value) {
      servo_position = (uint8_t)value;
      apply_servo();
    }
  } else if (strcmp(kind, "buttons") == 0) {
    char *mask_text = strtok_r(NULL, " ", &save);
    char *blink_text = strtok_r(NULL, " ", &save);
    unsigned long mask, blink;
    if (strtok_r(NULL, " ", &save) || !parse_uint(mask_text, &mask) || !parse_uint(blink_text, &blink) ||
        mask > 3 || blink > MAX_BLINK_MS) return;
    if (blink && blink < MIN_BLINK_MS) blink = MIN_BLINK_MS;
    button_mask = (uint8_t)mask;
    button_blink_ms = blink;
  }
}

// RESYNC has no CPU reset to fall back on for this sketch, unlike the other
// two Ventilastation devices -- and doesn't need one. Nothing here blocks or
// uses interrupts/threads (poll_serial()/update_buttons() are a plain
// non-blocking loop), so there's nothing a real reboot would recover that
// reinitializing state and re-applying the safe defaults setup() establishes
// doesn't already achieve, without the visible LED/servo glitch an actual
// reboot would cause. See
// docs/internals/base-control-api.md#device-identification-resync.
void handle_resync() {
  strip_red = 0;
  strip_green = 0;
  strip_blue = 0;
  servo_position = 0;
  button_mask = 0;
  button_blink_ms = 0;
  command_length = 0;
  legacy_timer_running = false;
  legacy_section = 0;
  apply_strip();
  apply_servo();
  update_buttons();
  Serial.println(F("VENTILASTATION BASE " FIRMWARE_VERSION " " FIRMWARE_GIT_HASH));
}

void poll_serial() {
  while (Serial.available()) {
    uint8_t input = (uint8_t)Serial.read();

    // Track a possible RESYNC match in parallel with normal parsing, not
    // instead of it -- see input_parser.py's feed() for the full rationale
    // (0x0A is both the marker's first byte and this parser's own line
    // terminator, so a partial or failed match must not swallow it).
    if (input == RESYNC_SEQUENCE[resync_match]) {
      resync_match++;
      if (resync_match == RESYNC_LEN) {
        resync_match = 0;
        handle_resync();
        continue;
      }
    } else {
      resync_match = (input == RESYNC_SEQUENCE[0]) ? 1 : 0;
    }

    if (input == '\n' || input == '\r') {
      if (command_length) {
        command_buffer[command_length] = '\0';
        handle_command(command_buffer);
        command_length = 0;
      }
    } else if (command_length < COMMAND_MAX) {
      command_buffer[command_length++] = input;
    } else {
      command_length = 0;  // overlong command: discard and resynchronize at newline
    }
  }
}

void update_buttons() {
  bool phase = button_blink_ms == 0 || (millis() % button_blink_ms) < (button_blink_ms / 2);
  digitalWrite(LUZ_BOTON_1, (button_mask & 0x01) && phase ? HIGH : LOW);
  digitalWrite(LUZ_BOTON_2, (button_mask & 0x02) && phase ? HIGH : LOW);
}

void setup() {
  Serial.begin(57600);
  servo.attach(SERVO_PIN);
  pixels.setBrightness(128);
  pixels.begin();
  pinMode(LUZ_BOTON_1, OUTPUT);
  pinMode(LUZ_BOTON_2, OUTPUT);
  apply_strip();
  apply_servo();
  update_buttons();
}

void loop() {
  poll_serial();
  legacy_check_timer();
  update_buttons();
}
