POVDISPLAY_MOD_DIR := $(USERMOD_DIR)

# Add all C files to SRC_USERMOD.
SRC_USERMOD += $(POVDISPLAY_MOD_DIR)/povdisplay.c \
               $(POVDISPLAY_MOD_DIR)/gpu.c \
               $(POVDISPLAY_MOD_DIR)/minispi.c \
               $(POVDISPLAY_MOD_DIR)/sprites.c \
               $(POVDISPLAY_MOD_DIR)/intensidades.c

# We can add our module folder to include paths if needed
# This is not actually needed in this example.
CFLAGS_USERMOD += -I$(POVDISPLAY_MOD_DIR)

