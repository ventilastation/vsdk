// Speaks the same wire protocol vsdk/apps/micropython/ventilastation/comms.py
// uses on real hardware: a line command ("frame_apa102\n") followed directly
// by the binary payload, over a plain TCP socket. See
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
// Besides pushing frame_apa102, the accepted connection also accepts simple
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
#include "esp_timer.h"
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
#include <sys/time.h>

static const char *TAG = "telemetry";

static uint8_t s_frame_buf[WB_FRAME_BYTES];
static EventGroupHandle_t s_wifi_event_group;
#define WIFI_CONNECTED_BIT BIT0

// Reads "ssid"/"password" blobs from NVS namespace WB_WIFI_NVS_NAMESPACE,
// the same namespace+keys apps/micropython/ventilastation/updater.py reads
// on the DUT (falling back to the pre-rename namespace for boards
// provisioned before it). out_ssid/out_password must be zero-initialized by
// the caller so the copied blob (which isn't necessarily NUL-terminated on
// its own) ends up as a valid C string as long as it fits in
// ssid_size-1/password_size-1.
static bool load_wifi_credentials_from(const char *ns, char *out_ssid, size_t ssid_size, char *out_password, size_t password_size) {
    nvs_handle_t handle;
    if (nvs_open(ns, NVS_READONLY, &handle) != ESP_OK) {
        return false;
    }

    size_t ssid_len = ssid_size - 1;
    size_t password_len = password_size - 1;
    bool ok = nvs_get_blob(handle, "ssid", out_ssid, &ssid_len) == ESP_OK &&
              nvs_get_blob(handle, "password", out_password, &password_len) == ESP_OK;
    nvs_close(handle);
    return ok;
}

static bool load_wifi_credentials(char *out_ssid, size_t ssid_size, char *out_password, size_t password_size) {
    if (load_wifi_credentials_from(WB_WIFI_NVS_NAMESPACE, out_ssid, ssid_size, out_password, password_size)) {
        return true;
    }
    if (load_wifi_credentials_from(WB_WIFI_NVS_NAMESPACE_LEGACY, out_ssid, ssid_size, out_password, password_size)) {
        ESP_LOGW(TAG, "using legacy \"%s\" WiFi credentials — re-run `make workbench-wifi-provision` to migrate",
                 WB_WIFI_NVS_NAMESPACE_LEGACY);
        return true;
    }
    ESP_LOGE(TAG, "no ssid/password in NVS namespace \"%s\" — run `make workbench-wifi-provision`",
             WB_WIFI_NVS_NAMESPACE);
    return false;
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

    // The default modem-sleep power save mode sleeps the radio between DTIM
    // beacons, adding tens of ms of latency/jitter to every send -- fine for
    // a phone checking mail occasionally, bad for this workbench's
    // continuous ~13 Mbps frame_apa102 stream (55KB every WB_TELEMETRY_FRAME_
    // INTERVAL_MS). The workbench runs on USB power, so there's no battery
    // budget to trade off against.
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));

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

// Sends exactly `len` bytes, resuming from wherever a partial send left off.
// This matters because client_sock has SO_SNDTIMEO set: once that timeout is
// armed, a send() that can't complete within the window returns however many
// bytes it *did* manage rather than -1 -- treating that as an error (or,
// worse, ignoring it) silently drops the tail of whatever was being sent and
// permanently desyncs the client's framing for the rest of the connection,
// since TCP has no message boundaries to resynchronize on.
//
// The deadline check must happen unconditionally at the top of every
// iteration, not just after an EAGAIN: a struggling link can make small
// nonzero progress on every single SO_SNDTIMEO-bounded send() call (n > 0
// each time, just far short of len) without ever hitting EAGAIN, and an
// earlier version of this function only checked the deadline in the EAGAIN
// branch -- that let a single frame's send retry, "successfully" a few bytes
// at a time, for many seconds before the caller ever heard about it.
static bool send_all(int sock, const uint8_t *buf, size_t len, int64_t overall_deadline_us) {
    size_t sent = 0;
    while (sent < len) {
        if (esp_timer_get_time() >= overall_deadline_us) {
            return false;
        }
        int n = send(sock, buf + sent, len - sent, 0);
        if (n > 0) {
            sent += (size_t)n;
            continue;
        }
        if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            continue;  // bounded by the deadline check at the top of the loop
        }
        return false;  // hard error or EOF (n == 0)
    }
    return true;
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

        // Nagle would otherwise hold the 13-byte "frame_apa102\n" header
        // back waiting to coalesce it with the payload send that follows a
        // few instructions later, adding avoidable latency to every frame.
        int nodelay = 1;
        setsockopt(client_sock, IPPROTO_TCP, TCP_NODELAY, &nodelay, sizeof(nodelay));
        // Bound how long a stuck/congested link can wedge this loop: without
        // this, a blocking send() on a stalled connection can hang far
        // longer than one frame interval (lwIP's own retransmit timeout),
        // during which the client sees nothing but silence instead of a
        // clean disconnect-and-retry.
        struct timeval snd_timeout = {.tv_sec = 0, .tv_usec = 200000};
        setsockopt(client_sock, SOL_SOCKET, SO_SNDTIMEO, &snd_timeout, sizeof(snd_timeout));

        char cmd_buf[CMD_BUF_SIZE];
        size_t cmd_len = 0;

        while (1) {
            poll_client_commands(client_sock, cmd_buf, &cmd_len);

            int64_t frame_start = esp_timer_get_time();

            led_capture_snapshot(s_frame_buf);
            // A generous overall budget (well beyond one frame interval) for
            // *this frame's* combined header+payload send: send_all() already
            // retries through any number of 200ms SO_SNDTIMEO expirations
            // that make progress, so this only fires for a link that's
            // genuinely wedged, not one that's merely slow.
            int64_t deadline = esp_timer_get_time() + 1000000;
            if (!send_all(client_sock, (const uint8_t *)"frame_apa102\n", sizeof("frame_apa102\n") - 1, deadline) ||
                !send_all(client_sock, s_frame_buf, sizeof(s_frame_buf), deadline)) {
                break;
            }

            // Pace off how long this frame actually took to send instead of
            // always sleeping the full interval: a slow/congested send would
            // otherwise push every subsequent frame later and later, turning
            // one hiccup into a growing backlog the client sees as a burst
            // followed by a stall rather than a single, brief slowdown.
            int64_t elapsed_ms = (esp_timer_get_time() - frame_start) / 1000;
            if (elapsed_ms < WB_TELEMETRY_FRAME_INTERVAL_MS) {
                vTaskDelay(pdMS_TO_TICKS(WB_TELEMETRY_FRAME_INTERVAL_MS - elapsed_ms));
            }
        }

        ESP_LOGI(TAG, "emulator disconnected");
        close(client_sock);
    }
}

void telemetry_begin(void) {
    // Core 1 is reserved for led_capture.c's tasks (SPI-slave capture +
    // decode); keep the WiFi/TCP telemetry link on core 0.
    xTaskCreatePinnedToCore(telemetry_task, "telemetry", 4096, NULL, 5, NULL, 0);
}
