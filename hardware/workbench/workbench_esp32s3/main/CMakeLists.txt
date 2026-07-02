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
        esp_wifi
        esp_event
        esp_netif
        nvs_flash
        esp_timer
        lwip
)
