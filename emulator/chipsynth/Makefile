# Builds libgenesissynth, the host-side Genesis sound-chip synthesizer used by
# emu_audio.py to regenerate audio from the register writes the spinning board
# streams over serial. It reuses the unmodified gwenesis YM2612 + SN76489 cores
# from the retro-go tree so the host output matches the device exactly.
#
#   make            # build the shared library
#   make clean

# Path to the gwenesis core sources (override if your checkout differs).
RETROGO   ?= ../../apps/retro-go
GW_SRC    := $(RETROGO)/gwenesis/components/gwenesis/src
RG_COMP   := $(RETROGO)/components/retro-go

UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
LIBEXT  := dylib
SHFLAG  := -dynamiclib
else
LIBEXT  := so
SHFLAG  := -shared
endif

LIB     := libgenesissynth.$(LIBEXT)

INC     := -I$(GW_SRC)/sound -I$(GW_SRC)/bus -I$(GW_SRC)/savestate -I$(RG_COMP)
SRC     := host_chip.c \
           $(GW_SRC)/sound/ym2612.c \
           $(GW_SRC)/sound/gwenesis_sn76489.c

# The cores assume the device build's char/pointer leniency; quiet those
# warnings rather than patch vendored code.
CFLAGS  := -O2 -fPIC $(INC) -Wno-incompatible-pointer-types -Wno-implicit-function-declaration

$(LIB): $(SRC)
	$(CC) $(SHFLAG) $(CFLAGS) -o $@ $(SRC)

clean:
	rm -f $(LIB)

.PHONY: clean
