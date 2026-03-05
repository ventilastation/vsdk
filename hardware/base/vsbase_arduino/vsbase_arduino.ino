#include <Servo.h>
#include <Adafruit_NeoPixel.h>
#include <limits.h>

#define CENTISECONDS (10UL) // in milliseconds

unsigned long section_durations[] = {
  1325 * CENTISECONDS,
  1325 * CENTISECONDS,
  1325 * CENTISECONDS,
  1325 * CENTISECONDS,
  1325 * 2 * CENTISECONDS,
  1325 * 3 * CENTISECONDS,
  ULONG_MAX
};

uint32_t colors[] = {
  0x0000ff,
  0x00ff00,
  0xffff00,
  0x00ffff,
  0xff00ff,
  0xff0000,
  0x000000,
};

#define NEO_PIN 7
#define LUZ_BOTON_1 2
#define LUZ_BOTON_2 3
#define SERVO 10  
#define NUM_PIXELS 16

Adafruit_NeoPixel pixels = Adafruit_NeoPixel(NUM_PIXELS, NEO_PIN, NEO_GRB + NEO_KHZ800);
Servo myservo;
uint8_t ledPin = PINB5;
int16_t counts;
int16_t _maxCounts = 32767;
int16_t _minCounts = -32767;

uint8_t _ledMask = (1 << PINB5);

int section = 0;
bool timer_running;
bool botones_prendidos;
unsigned long section_init_time;
unsigned long section_duration = section_durations[section];

void update_servo_colors(uint32_t color) {
  for (int n = 0; n < NUM_PIXELS; n++) {
    pixels.setPixelColor(n, color);
  }
  pixels.show();
}

void update_servo_value(unsigned long value, unsigned long max_val) {
  // rango = (106,13)
  int s = map(value, 0, max_val, 106, 13);
  myservo.write(s);
}

void apagar_botones() {
  botones_prendidos = false;
}

void prender_botones() {
  botones_prendidos = true;
}

void start_timer() {
  timer_running = true;
  section = 0;
  section_init_time = millis();
  section_duration = section_durations[section];
  update_servo_colors(colors[0]);
  apagar_botones();
}

void stop_timer() {
  timer_running = false;
  prender_botones();
}

void stop_no_leds() {
  timer_running = false;
  update_servo_colors(0);
  apagar_botones();
}

void reset_it_all() {
  timer_running = false;
  update_servo_colors(0);
  update_servo_value(0, 255);
  section = 0;
  prender_botones();
}

void advance_section(unsigned long now) {
  section++;
  section_init_time = now;
  section_duration = section_durations[section];
  update_servo_colors(colors[section]);
}

void check_timer() {
  if (timer_running == false) {
    return;
  }
  unsigned long now = millis();
  if (now - section_init_time > section_duration) {
    advance_section(now);
  }
  if (section_duration != ULONG_MAX) {
    update_servo_value(now - section_init_time, section_duration);
  }
}

void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();

    switch (inChar) {
      case 's':
        stop_timer();
        break;
      case 'S':
        start_timer();
        break;
      case 'r':
        stop_no_leds();
        break;
      case 'R':
        reset_it_all();
        break;
    }
  }
}

void setup() {
  Serial.begin (57600); /* Initialize serial comm port */
  myservo.attach(SERVO);
  pixels.setBrightness(128);
  pixels.begin();
  pinMode(LUZ_BOTON_1, OUTPUT);
  pinMode(LUZ_BOTON_2, OUTPUT);
  reset_it_all();
  apagar_botones();
}

void blink_botones() {
  if (botones_prendidos) {
    bool blink = (millis() >> 8) & 1;
    digitalWrite(LUZ_BOTON_1, blink);
    digitalWrite(LUZ_BOTON_2, blink);
  } else {
    digitalWrite(LUZ_BOTON_1, LOW);
    digitalWrite(LUZ_BOTON_2, LOW);
  }
};

void loop() {
  check_timer();
  blink_botones();
}