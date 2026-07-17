idf_component_register(
    SRCS
        "workbench_main.c"
        "reset_ctl.c"
        "hall_sim.c"
        "led_capture.c"
        "serial_bridge.c"
        "telemetry.c"
    INCLUDE_DIRS "."
    PRIV_REQUIRES
        driver
        esp_driver_usb_serial_jtag
        esp_wifi
        esp_event
        esp_netif
        nvs_flash
        esp_timer
        lwip
        mdns
)

# PROJECT_VER is ESP-IDF's own git-describe-based project version (see
# $ENV{IDF_PATH}/tools/cmake/project.cmake) -- reuse it as serial_bridge.c's
# RESYNC identification banner git hash (see
# docs/internals/input-protocol-v2.md#resync--device-identification) rather
# than adding a second git-invoking CMake step.
target_compile_definitions(${COMPONENT_LIB} PRIVATE WB_GIT_HASH="${PROJECT_VER}")
