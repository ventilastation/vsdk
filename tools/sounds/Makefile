# Rebuild browser-friendly wav files for all game and system audio assets.
SOUND_ROOTS := ../../games ../../system
SRCS := $(shell find $(SOUND_ROOTS) -name '*.mp3')

%.mp3.wav: %.mp3
	@echo Using ffmpeg to generate $@
	@ffmpeg -loglevel error -y -i "$<" "$@"

all: $(SRCS:%=%.wav)
