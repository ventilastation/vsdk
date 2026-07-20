// UDP telemetry link to vsdk/emulator/comms.py's workbench receiver (see
// WorkbenchTelemetryConn there for the client side). Deliberately NOT the
// TCP-framed wire protocol the rest of the codebase speaks
// (vsdk/apps/micropython/ventilastation/comms.py, host-protocol.md): TCP's
// in-order/retransmit guarantee is the wrong fit for a live "latest frame
// wins" preview -- one lost segment head-of-line-blocks everything queued
// behind it until retransmitted, turning a single dropped packet into a
// visible stall instead of a few stale columns. UDP has no such queue: a
// lost datagram just leaves those columns showing last frame's data.
//
// Wire format, workbench -> client, one UDP datagram per column-chunk:
//   byte 0:     WB_CHUNK_MAGIC
//   bytes 1-4:  frame_seq, uint32 little-endian. Increments once per
//               led_capture_snapshot() call, not once per revolution --
//               decoupled from led_capture.c's own half-turn buffer flips.
//   byte 5:     chunk_index, 0..WB_NUM_CHUNKS-1
//   bytes 6..:  WB_CHUNK_PAYLOAD_BYTES of raw APA102 data for columns
//               [chunk_index*WB_COLUMNS_PER_CHUNK, +WB_COLUMNS_PER_CHUNK)
// No chunk_count field: both ends know WB_NUM_CHUNKS at compile time.
//
// Client -> workbench, plain text lines (same as before), used both for
// their own effect and as the only signal the workbench has of who to
// stream to -- UDP has no accept(), so "the current client" is just
// whoever's datagram arrived most recently, aged out after
// WB_TELEMETRY_CLIENT_TIMEOUT_MS of silence:
//   "reset\n"    -> pulse the DUT's reset line
//   "rpm <n>\n"  -> change the simulated hall RPM
//   "hello\n"    -> no-op, sent periodically by the client purely to keep
//                   its subscription (and NAT/firewall mapping) alive
//
// The workbench joins an existing Wi-Fi network (station mode) rather than
// running its own AP, so the PC running the pyglet emulator keeps normal
// internet access on the same network — matching how the DUT itself joins
// Wi-Fi in apps/micropython/ventilastation/comms.py, including reusing the
// same NVS namespace/keys for credentials. It advertises itself over mDNS
// (WB_MDNS_HOSTNAME + ".local") so the emulator doesn't need to know its
// DHCP-assigned IP.

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
    } else if (strcmp(line, "hello") == 0) {
        // No-op: receiving *any* datagram is what actually matters (see
        // telemetry_task's client_addr tracking below) -- "hello" exists
        // purely so the client has something to send to keep its
        // subscription alive when the user isn't touching the RPM slider
        // or reset button.
    } else if (line[0] != '\0') {
        ESP_LOGW(TAG, "unknown command: \"%s\"", line);
    }
}

#define WB_CHUNK_MAGIC          0xA1
#define WB_CHUNK_HEADER_BYTES   6  // magic(1) + frame_seq(4) + chunk_index(1)
#define WB_CHUNK_PACKET_BYTES   (WB_CHUNK_HEADER_BYTES + WB_CHUNK_PAYLOAD_BYTES)

#define CMD_BUF_SIZE 64

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

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock < 0) {
        ESP_LOGE(TAG, "unable to create socket: errno %d", errno);
        vTaskDelete(NULL);
        return;
    }

    int opt = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr = {
        .sin_family = AF_INET,
        .sin_addr.s_addr = htonl(INADDR_ANY),
        .sin_port = htons(WB_TELEMETRY_PORT),
    };
    if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) != 0) {
        ESP_LOGE(TAG, "unable to bind :%d: errno %d", WB_TELEMETRY_PORT, errno);
        close(sock);
        vTaskDelete(NULL);
        return;
    }

    // This is the loop's tick rate: how promptly it notices "it's time to
    // send the next frame" even when no client datagram arrives to wake it.
    // Far below WB_TELEMETRY_FRAME_INTERVAL_MS so frame pacing stays
    // accurate.
    struct timeval rcv_timeout = {.tv_sec = 0, .tv_usec = 5000};
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &rcv_timeout, sizeof(rcv_timeout));

    // Unlike the old TCP socket's SO_SNDTIMEO, this isn't guarding against a
    // partial send (sendto() is atomic for UDP -- one call, one whole
    // datagram, no partial-write concept) -- it bounds how long a single
    // congested sendto() can block. Without it, a burst of WB_NUM_CHUNKS
    // blocking sends under a bad enough link stacked up into multiple
    // seconds inside one loop iteration on real hardware, long enough to
    // starve the core 0 idle task and trip the watchdog. 20ms per chunk
    // caps one full frame's worth of sends at ~1.3s worst case, well under
    // that, while still being generous for a call that normally returns
    // near-instantly.
    struct timeval snd_timeout = {.tv_sec = 0, .tv_usec = 20000};
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &snd_timeout, sizeof(snd_timeout));

    ESP_LOGI(TAG, "listening for emulator telemetry on %s.local:%d (UDP)", WB_MDNS_HOSTNAME, WB_TELEMETRY_PORT);

    struct sockaddr_in client_addr = {0};
    bool have_client = false;
    int64_t client_last_seen_us = 0;
    uint32_t frame_seq = 0;
    int64_t last_frame_us = 0;

    char cmd_buf[CMD_BUF_SIZE];
    uint8_t packet[WB_CHUNK_PACKET_BYTES];

    while (1) {
        struct sockaddr_in from_addr;
        socklen_t from_len = sizeof(from_addr);
        int n = recvfrom(sock, cmd_buf, sizeof(cmd_buf) - 1, 0, (struct sockaddr *)&from_addr, &from_len);
        if (n > 0) {
            // One datagram is one line -- no partial-line buffering needed
            // here, unlike the old TCP stream parser: recvfrom() already
            // hands us a complete message. Just trim a trailing \n/\r\n.
            while (n > 0 && (cmd_buf[n - 1] == '\n' || cmd_buf[n - 1] == '\r')) {
                n--;
            }
            cmd_buf[n] = '\0';
            handle_client_line(cmd_buf);

            bool same_client = have_client &&
                                client_addr.sin_addr.s_addr == from_addr.sin_addr.s_addr &&
                                client_addr.sin_port == from_addr.sin_port;
            if (!same_client) {
                ESP_LOGI(TAG, "streaming to new emulator client");
            }
            client_addr = from_addr;
            have_client = true;
            client_last_seen_us = esp_timer_get_time();
        }

        int64_t now = esp_timer_get_time();

        if (have_client && now - client_last_seen_us > (int64_t)WB_TELEMETRY_CLIENT_TIMEOUT_MS * 1000) {
            ESP_LOGI(TAG, "client timed out (no datagram in %d ms), no longer streaming",
                     WB_TELEMETRY_CLIENT_TIMEOUT_MS);
            have_client = false;
        }

        if (have_client && now - last_frame_us >= (int64_t)WB_TELEMETRY_FRAME_INTERVAL_MS * 1000) {
            last_frame_us = now;
            led_capture_snapshot(s_frame_buf);
            frame_seq++;

            for (int chunk = 0; chunk < WB_NUM_CHUNKS; chunk++) {
                packet[0] = WB_CHUNK_MAGIC;
                memcpy(packet + 1, &frame_seq, sizeof(frame_seq));
                packet[5] = (uint8_t)chunk;
                memcpy(packet + WB_CHUNK_HEADER_BYTES,
                       s_frame_buf + chunk * WB_CHUNK_PAYLOAD_BYTES,
                       WB_CHUNK_PAYLOAD_BYTES);
                // Fire-and-forget by design: a failed/lost send just leaves
                // this chunk's columns showing stale data until the next
                // frame, not a stalled stream (see the file header comment).
                sendto(sock, packet, sizeof(packet), 0,
                       (struct sockaddr *)&client_addr, sizeof(client_addr));
            }
        }

        // Explicit yield once per loop iteration: recvfrom()'s SO_RCVTIMEO
        // was not, in practice, a reliable enough yield point on its own --
        // on real hardware this task starved the core 0 idle task badly
        // enough to trip its watchdog. A single WB_NUM_CHUNKS burst (worst
        // case ~WB_NUM_CHUNKS * 20ms if every send hit its SO_SNDTIMEO) is
        // still comfortably under the watchdog's window, so one guaranteed
        // yield per outer-loop pass -- not one per chunk, which would cap
        // throughput at a small fraction of one frame per second -- is
        // enough.
        vTaskDelay(1);
    }
}

void telemetry_begin(void) {
    // Core 1 is reserved for led_capture.c's tasks (SPI-slave capture +
    // decode); keep the WiFi/UDP telemetry link on core 0.
    xTaskCreatePinnedToCore(telemetry_task, "telemetry", 4096, NULL, 5, NULL, 0);
}
