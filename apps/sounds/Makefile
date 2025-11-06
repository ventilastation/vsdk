SRCS := $(shell find . -name '*.mp3')

%.mp3.wav: %.mp3
	@echo Using ffmpeg to generate $@
	@ffmpeg -loglevel error -y -i "$<" "$@"

all: $(SRCS:%=%.wav)
