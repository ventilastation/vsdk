#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// The browser platform sends all high-frequency renderer state through these
// pointer callbacks.  The iOS host copies the data before returning to the VM.
typedef struct {
    void (*command)(const uint8_t *line, size_t line_length, const uint8_t *data, size_t data_length);
    void (*present)(const uint8_t *sprites, size_t sprites_length, const uint8_t *frame_meta, size_t frame_meta_length);
} vs_ios_host_callbacks_t;

void vs_ios_host_set_callbacks(const vs_ios_host_callbacks_t *callbacks);
void vs_ios_host_set_input(uint8_t joy1, uint8_t joy2, uint8_t extra, bool exit_requested);
void vs_ios_host_request_full_frame(void);
void vs_ios_host_set_running(bool running);

uint8_t vs_ios_host_get_joy1(void);
uint8_t vs_ios_host_get_joy2(void);
uint8_t vs_ios_host_get_extra(void);
bool vs_ios_host_consume_exit(void);
bool vs_ios_host_consume_full_frame_request(void);
bool vs_ios_host_is_running(void);

void vs_ios_host_post_command(const uint8_t *line, size_t line_length, const uint8_t *data, size_t data_length);
void vs_ios_host_post_present(const uint8_t *sprites, size_t sprites_length, const uint8_t *frame_meta, size_t frame_meta_length);
