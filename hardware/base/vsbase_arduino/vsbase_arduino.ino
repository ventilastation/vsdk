#include <Servo.h>
#include <Adafruit_NeoPixel.h>
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

Adafruit_NeoPixel pixels(NUM_PIXELS, NEO_PIN, NEO_GRB + NEO_KHZ800);
Servo servo;

uint8_t strip_red = 0, strip_green = 0, strip_blue = 0;
uint8_t servo_position = 0;
uint8_t button_mask = 0;
unsigned long button_blink_ms = 0;
char command_buffer[COMMAND_MAX + 1];
uint8_t command_length = 0;

void apply_strip() {
  uint32_t color = pixels.Color(strip_red, strip_green, strip_blue);
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
  if (!prefix || !kind || strcmp(prefix, "base") != 0) return;

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

void poll_serial() {
  while (Serial.available()) {
    char input = (char)Serial.read();
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
  update_buttons();
}
