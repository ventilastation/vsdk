# Builds the host-side console sound-chip synthesizers used by emu_audio.py to
# regenerate audio from the register writes the spinning board streams over
# serial. Each shared library reuses the unmodified device-side core so the
# host output matches the board exactly.
#
#   make            # build every shared library
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

GEN_LIB := libgenesissynth.$(LIBEXT)
SMS_LIB := libsmssynth.$(LIBEXT)
NES_LIB := libnessynth.$(LIBEXT)
GB_LIB  := libgbsynth.$(LIBEXT)
MSX_LIB := libmsxsynth.$(LIBEXT)
LIBS    := $(GEN_LIB) $(SMS_LIB) $(NES_LIB) $(GB_LIB) $(MSX_LIB)

INC_GEN := -I. -I$(GW_SRC)/sound -I$(GW_SRC)/bus -I$(GW_SRC)/savestate -I$(RG_COMP)
SRC_GEN := host_chip.c \
           $(GW_SRC)/sound/ym2612.c \
           $(GW_SRC)/sound/gwenesis_sn76489.c

SMS_SRC_ROOT := $(RETROGO)/retro-core/components/smsplus
INC_SMS := -I. -I$(SMS_SRC_ROOT) -I$(SMS_SRC_ROOT)/cpu -I$(SMS_SRC_ROOT)/sound -I$(RG_COMP)
SRC_SMS := host_sms.c \
           $(SMS_SRC_ROOT)/sound/sn76489.c

NES_SRC_ROOT := $(RETROGO)/retro-core/components/nofrendo
INC_NES := -I. -I$(NES_SRC_ROOT) -I$(NES_SRC_ROOT)/nes -I$(RG_COMP)
SRC_NES := host_nes.c \
           $(NES_SRC_ROOT)/nes/apu.c

GB_SRC_ROOT := $(RETROGO)/retro-core/components/gnuboy
INC_GB  := -I. -I$(GB_SRC_ROOT) -I$(RG_COMP)
SRC_GB  := host_gb.c \
           $(GB_SRC_ROOT)/sound.c

MSX_SRC_ROOT := $(RETROGO)/fmsx/components/fmsx/src/EMULib
INC_MSX := -I. -I$(MSX_SRC_ROOT) -I$(RG_COMP)
SRC_MSX := host_msx.c \
           $(MSX_SRC_ROOT)/AY8910.c \
           $(MSX_SRC_ROOT)/Sound.c

# The cores assume the device build's char/pointer leniency; quiet those
# warnings rather than patch vendored code.
CFLAGS  := -O2 -fPIC -Wno-incompatible-pointer-types -Wno-implicit-function-declaration

all: $(LIBS)

$(GEN_LIB): $(SRC_GEN)
	$(CC) $(SHFLAG) $(CFLAGS) $(INC_GEN) -o $@ $(SRC_GEN)

$(SMS_LIB): $(SRC_SMS)
	$(CC) $(SHFLAG) $(CFLAGS) $(INC_SMS) -o $@ $(SRC_SMS)

$(NES_LIB): $(SRC_NES)
	$(CC) $(SHFLAG) $(CFLAGS) $(INC_NES) -o $@ $(SRC_NES)

$(GB_LIB): $(SRC_GB)
	$(CC) $(SHFLAG) $(CFLAGS) $(INC_GB) -o $@ $(SRC_GB)

$(MSX_LIB): $(SRC_MSX)
	$(CC) $(SHFLAG) $(CFLAGS) $(INC_MSX) -o $@ $(SRC_MSX)

clean:
	rm -f $(LIBS)

.PHONY: all clean
