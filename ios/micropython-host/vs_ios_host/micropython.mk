# Native bridge module included when building the iOS MicroPython runtime.
#
# The module name is __vs_host, matching the browser worker host contract.
# Keeping that contract means the existing Python browser platform, launcher,
# Vyruss VS2, and Vixeous source all run unchanged on iOS.
SRC_USERMOD_C += $(USERMOD_DIR)/mod_vs_ios_host.c
SRC_USERMOD_LIB_C += $(USERMOD_DIR)/vs_ios_host.c
CFLAGS_USERMOD += -I$(USERMOD_DIR)
