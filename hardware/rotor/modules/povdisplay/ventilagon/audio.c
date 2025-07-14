/*
a) awesome.wav
b) begin.wav
c) die.wav
d) excellent.wav
e) gameover.wav
f) hexagon.wav
g) line.wav
h) menuchoose.wav
i) menuselect.wav
j) pentagon.wav
k) rankup.wav
l) square.wav
m) start.wav
n) superhexagon.wav
o) triangle.wav
p) wonderful.wav

buenisimo.wav
cuadrado.wav
daleeee.wav
dale.wav
empeza.wav
excelente.wav
hexagono.wav
impecable.wav
increible.wav
linea.wav
maravilloso no lo puedo creer.wav
pentagono.wav
perdiste.wav
sonaste.wav
superventilagon.wav
tas chavo.wav
triangulo.wav
vamos.wav
ventilagono.wav
*/

#include "ventilagon.h"

void serial_send(const char* text) {
  xQueueSend(queue_sending, &text, 0);
  // printf("serial sending... (%p) ", text);
  // printf("%s\n", text);
}

void audio_play(const char* command) {
  if (command != NULL) {
    serial_send(command);
  }
}

void audio_play_superventilagon() {
  audio_play("sound ventilagon/audio/es/superventilagon");
}

void audio_play_crash() {
  audio_play("sound ventilagon/audio/die");
}

void audio_play_win() {
  audio_play("sound ventilagon/audio/es/buenisimo");
}

void audio_play_game_over() {
  audio_play("sound ventilagon/audio/es/perdiste");
}

void audio_stop_song() {
  serial_send("music off");
}

void audio_begin() {
  serial_send("sound ventilagon/audio/es/empeza");
}

void audio_reset() {
  serial_send("music off");
}

void audio_stop_servo() {
  serial_send("servo stop");
}

const char* section_sounds[] = {
  NULL,
  "sound ventilagon/audio/es/linea",
  "sound ventilagon/audio/es/triangulo",
  "sound ventilagon/audio/es/cuadrado",
  "sound ventilagon/audio/es/pentagono",
  "sound ventilagon/audio/es/ventilagono",
  NULL
};

