// Speaks the same wire protocol vsdk/apps/micropython/ventilastation/comms.py
// uses on real hardware: a line command ("frame_rgb\n") followed directly by
// the binary payload, over a plain TCP socket. See
// vsdk/emulator/comms.py receive_loop() for the client side that consumes
// this.
//
// The workbench runs as its own Wi-Fi AP (rather than joining an existing
// network, like the DUT's comms.py does) so a laptop can connect directly
// with no extra infrastructure: join "WB_WIFI_AP_SSID", then run
// `python emulator/emu.py 192.168.4.1`.

#include "telemetry.h"
#include "config.h"
#include "led_capture.h"

#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "nvs_flash.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "lwip/sockets.h"
#include <string.h>

static const char *TAG = "telemetry";

static uint8_t s_frame_buf[WB_FRAME_BYTES];

static void wifi_ap_init(void) {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    wifi_config_t wifi_config = {
        .ap = {
            .ssid = WB_WIFI_AP_SSID,
            .ssid_len = strlen(WB_WIFI_AP_SSID),
            .password = WB_WIFI_AP_PASSWORD,
            .max_connection = 4,
            .authmode = WIFI_AUTH_WPA2_PSK,
        },
    };
    if (strlen(WB_WIFI_AP_PASSWORD) == 0) {
        wifi_config.ap.authmode = WIFI_AUTH_OPEN;
    }

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "AP \"%s\" up at 192.168.4.1. On a PC joined to it, run:", WB_WIFI_AP_SSID);
    ESP_LOGI(TAG, "  cd vsdk && python emulator/emu.py 192.168.4.1");
}

static void telemetry_task(void *arg) {
    wifi_ap_init();

    int listen_sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (listen_sock < 0) {
        ESP_LOGE(TAG, "unable to create socket: errno %d", errno);
        vTaskDelete(NULL);
        return;
    }

    int opt = 1;
    setsockopt(listen_sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr = {
        .sin_family = AF_INET,
        .sin_addr.s_addr = htonl(INADDR_ANY),
        .sin_port = htons(WB_TELEMETRY_PORT),
    };
    if (bind(listen_sock, (struct sockaddr *)&addr, sizeof(addr)) != 0 ||
        listen(listen_sock, 1) != 0) {
        ESP_LOGE(TAG, "unable to bind/listen on :%d: errno %d", WB_TELEMETRY_PORT, errno);
        close(listen_sock);
        vTaskDelete(NULL);
        return;
    }

    while (1) {
        ESP_LOGI(TAG, "waiting for emulator connection on :%d", WB_TELEMETRY_PORT);
        int client_sock = accept(listen_sock, NULL, NULL);
        if (client_sock < 0) {
            continue;
        }
        ESP_LOGI(TAG, "emulator connected");

        while (1) {
            led_capture_snapshot(s_frame_buf);
            if (send(client_sock, "frame_rgb\n", 10, 0) < 0 ||
                send(client_sock, s_frame_buf, sizeof(s_frame_buf), 0) < 0) {
                break;
            }
            vTaskDelay(pdMS_TO_TICKS(WB_TELEMETRY_FRAME_INTERVAL_MS));
        }

        ESP_LOGI(TAG, "emulator disconnected");
        close(client_sock);
    }
}

void telemetry_begin(void) {
    xTaskCreate(telemetry_task, "telemetry", 4096, NULL, 5, NULL);
}
