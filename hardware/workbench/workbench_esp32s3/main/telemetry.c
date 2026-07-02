// Speaks the same wire protocol vsdk/apps/micropython/ventilastation/comms.py
// uses on real hardware: a line command ("frame_rgb\n") followed directly by
// the binary payload, over a plain TCP socket. See
// vsdk/emulator/comms.py receive_loop() for the client side that consumes
// this.
//
// The workbench joins an existing Wi-Fi network (station mode) rather than
// running its own AP, so the PC running the pyglet emulator keeps normal
// internet access on the same network — matching how the DUT itself joins
// Wi-Fi in apps/micropython/ventilastation/comms.py, including reusing the
// same NVS namespace/keys for credentials. It advertises itself over mDNS
// (WB_MDNS_HOSTNAME + ".local") so the emulator doesn't need to know its
// DHCP-assigned IP.
//
// Besides pushing frame_rgb, the accepted connection also accepts simple
// line commands from the client:
//   "reset\n"    -> pulse the DUT's reset line
//   "rpm <n>\n"  -> change the simulated hall RPM

#include "telemetry.h"
#include "config.h"
#include "led_capture.h"
#include "hall_sim.h"
#include "reset_ctl.h"

#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "mdns.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"

#include "lwip/sockets.h"
#include <errno.h>
#include <string.h>
#include <stdlib.h>

static const char *TAG = "telemetry";

static uint8_t s_frame_buf[WB_FRAME_BYTES];
static EventGroupHandle_t s_wifi_event_group;
#define WIFI_CONNECTED_BIT BIT0

// Reads "ssid"/"password" blobs from NVS namespace WB_WIFI_NVS_NAMESPACE,
// the same namespace+keys apps/micropython/ventilastation/comms.py reads on
// the DUT. out_ssid/out_password must be zero-initialized by the caller so
// the copied blob (which isn't necessarily NUL-terminated on its own) ends
// up as a valid C string as long as it fits in ssid_size-1/password_size-1.
static bool load_wifi_credentials(char *out_ssid, size_t ssid_size, char *out_password, size_t password_size) {
    nvs_handle_t handle;
    if (nvs_open(WB_WIFI_NVS_NAMESPACE, NVS_READONLY, &handle) != ESP_OK) {
        ESP_LOGE(TAG, "no \"%s\" NVS namespace — run `make workbench-wifi-provision`", WB_WIFI_NVS_NAMESPACE);
        return false;
    }

    size_t ssid_len = ssid_size - 1;
    size_t password_len = password_size - 1;
    bool ok = nvs_get_blob(handle, "ssid", out_ssid, &ssid_len) == ESP_OK &&
              nvs_get_blob(handle, "password", out_password, &password_len) == ESP_OK;
    nvs_close(handle);

    if (!ok) {
        ESP_LOGE(TAG, "\"%s\" NVS namespace is missing ssid/password — run `make workbench-wifi-provision`",
                 WB_WIFI_NVS_NAMESPACE);
    }
    return ok;
}

static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "Wi-Fi disconnected, retrying in %d ms", WB_WIFI_CONNECT_RETRY_DELAY_MS);
        vTaskDelay(pdMS_TO_TICKS(WB_WIFI_CONNECT_RETRY_DELAY_MS));
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "got IP: " IPSTR, IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

static void mdns_start(void) {
    ESP_ERROR_CHECK(mdns_init());
    ESP_ERROR_CHECK(mdns_hostname_set(WB_MDNS_HOSTNAME));
    ESP_ERROR_CHECK(mdns_instance_name_set(WB_MDNS_INSTANCE_NAME));
    ESP_ERROR_CHECK(mdns_service_add(NULL, WB_MDNS_SERVICE_TYPE, WB_MDNS_SERVICE_PROTO, WB_TELEMETRY_PORT, NULL, 0));
    ESP_LOGI(TAG, "mDNS: reachable as %s.local", WB_MDNS_HOSTNAME);
}

// Returns false (and leaves Wi-Fi/mDNS down) if there are no credentials
// yet, so the rest of the firmware (reset pulse, hall sim, UART bridge)
// still comes up and is usable over the workbench's own USB port.
static bool wifi_sta_init(void) {
    char ssid[33] = {0};
    char password[65] = {0};
    if (!load_wifi_credentials(ssid, sizeof(ssid), password, sizeof(password))) {
        return false;
    }

    s_wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL));

    wifi_config_t wifi_config = {0};
    size_t ssid_n = strnlen(ssid, sizeof(wifi_config.sta.ssid));
    size_t password_n = strnlen(password, sizeof(wifi_config.sta.password));
    memcpy(wifi_config.sta.ssid, ssid, ssid_n);
    memcpy(wifi_config.sta.password, password, password_n);

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "connecting to \"%s\"...", ssid);
    xEventGroupWaitBits(s_wifi_event_group, WIFI_CONNECTED_BIT, pdFALSE, pdTRUE, portMAX_DELAY);

    mdns_start();
    return true;
}

static void handle_client_line(char *line) {
    if (strcmp(line, "reset") == 0) {
        ESP_LOGI(TAG, "client requested DUT reset");
        reset_ctl_pulse(WB_RESET_PULSE_MS);
    } else if (strncmp(line, "rpm ", 4) == 0) {
        long rpm = strtol(line + 4, NULL, 10);
        if (rpm < 0) {
            rpm = 0;
        }
        ESP_LOGI(TAG, "client set RPM to %ld", rpm);
        hall_sim_set_rpm((uint32_t)rpm);
    } else if (line[0] != '\0') {
        ESP_LOGW(TAG, "unknown command: \"%s\"", line);
    }
}

#define CMD_BUF_SIZE 64

// Drains whatever the client has sent so far (non-blocking) and dispatches
// any complete "\n"-terminated command lines found in it.
static void poll_client_commands(int client_sock, char *cmd_buf, size_t *cmd_len) {
    char chunk[64];
    int n;
    while ((n = recv(client_sock, chunk, sizeof(chunk), MSG_DONTWAIT)) > 0) {
        for (int i = 0; i < n; i++) {
            char c = chunk[i];
            if (c == '\n') {
                cmd_buf[*cmd_len] = '\0';
                handle_client_line(cmd_buf);
                *cmd_len = 0;
            } else if (c != '\r' && *cmd_len < CMD_BUF_SIZE - 1) {
                cmd_buf[(*cmd_len)++] = c;
            }
        }
    }
}

static void telemetry_task(void *arg) {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    if (!wifi_sta_init()) {
        ESP_LOGE(TAG, "no Wi-Fi credentials: telemetry link disabled (reset/hall/UART still work)");
        vTaskDelete(NULL);
        return;
    }

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
        ESP_LOGI(TAG, "waiting for emulator connection on %s.local:%d", WB_MDNS_HOSTNAME, WB_TELEMETRY_PORT);
        int client_sock = accept(listen_sock, NULL, NULL);
        if (client_sock < 0) {
            continue;
        }
        ESP_LOGI(TAG, "emulator connected");

        char cmd_buf[CMD_BUF_SIZE];
        size_t cmd_len = 0;

        while (1) {
            poll_client_commands(client_sock, cmd_buf, &cmd_len);

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
