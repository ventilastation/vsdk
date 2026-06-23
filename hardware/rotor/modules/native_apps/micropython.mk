NATIVE_APPS_MOD_DIR := $(USERMOD_DIR)

# Add all C files to SRC_USERMOD.
SRC_USERMOD += $(NATIVE_APPS_MOD_DIR)/native_apps.c

# Add our module folder to include paths.
CFLAGS_USERMOD += -I$(NATIVE_APPS_MOD_DIR)
