#include "freertos/idf_additions.h" // for xTaskCreatePinnedToCore
#include "py/nlr.h"
#include "py/obj.h"
#include "py/objstr.h"
#include "py/runtime.h"
#include "py/binary.h"
#include "mphalport.h"


#include "driver/gpio.h"
#include "esp_timer.h"

#include <stdio.h>
#include <string.h>
#include <inttypes.h>

#include "minispi.h"
#include "gpu.h"
#include "color_pipeline.h"
#include "ventilagon/ventilagon.h"

// Wiring is provided by the NVS-backed MicroPython board configuration at init.
int hall_gpio;
int irdiode_gpio;
int led_spi_host;
int led_clk;
int led_mosi;
int led_cs;
uint32_t led_freq;

#define COLUMNS 256
#define FASTEST_CREDIBLE_TURN 10000 // if the fan is going over 100 FPS, then I don't believe it, and discard the reading

#define DEBUG_ROTATION 0
#define PROFILE_GPU_STEP 0

// This profiler is deliberately opt-in. It measures the real GPU task's
// overlapped queue/render/wait/copy sequence without printf traffic on that
// task. A control command reads the accumulated snapshot from the other core.
typedef struct {
    uint32_t samples;
    uint32_t skipped_updates;
    uint32_t deadline_misses;
    uint32_t deadline_us;
    uint64_t total_us;
    uint64_t render_us;
    uint64_t spi_wait_us;
    uint64_t copy_us;
    uint32_t max_total_us;
    uint32_t max_render_us;
    uint32_t max_arm_render_us;
    uint32_t max_spi_wait_us;
    uint32_t max_copy_us;
    int32_t worst_slack_us;
    bool have_column;
    uint8_t last_column;
} pov_performance_t;

static portMUX_TYPE performance_lock = portMUX_INITIALIZER_UNLOCKED;
static volatile bool performance_enabled;
static pov_performance_t performance;

static uint32_t elapsed_us(int64_t start, int64_t end) {
    return end <= start ? 0 : (uint32_t)(end - start);
}

static bool performance_is_enabled(void) {
    return __atomic_load_n(&performance_enabled, __ATOMIC_ACQUIRE);
}

static void performance_reset(void) {
    portENTER_CRITICAL(&performance_lock);
    memset(&performance, 0, sizeof(performance));
    performance.worst_slack_us = INT32_MAX;
    portEXIT_CRITICAL(&performance_lock);
}

static void performance_record(uint8_t column, uint32_t deadline_us,
        uint32_t total_us, uint32_t render_us, uint32_t arm0_render_us,
        uint32_t arm1_render_us, uint32_t spi_wait_us, uint32_t copy_us) {
    if (!performance_is_enabled()) {
        return;
    }
    int32_t slack_us = deadline_us > (uint32_t)INT32_MAX
        ? INT32_MAX : (int32_t)deadline_us - (int32_t)total_us;
    portENTER_CRITICAL(&performance_lock);
    if (performance.have_column) {
        uint8_t delta = (column - performance.last_column) & 0xff;
        if (delta > 1) {
            performance.skipped_updates += delta - 1;
        }
    } else {
        performance.have_column = true;
    }
    performance.last_column = column;
    performance.samples++;
    performance.deadline_us = deadline_us;
    performance.total_us += total_us;
    performance.render_us += render_us;
    performance.spi_wait_us += spi_wait_us;
    performance.copy_us += copy_us;
    if (total_us > performance.max_total_us) performance.max_total_us = total_us;
    if (render_us > performance.max_render_us) performance.max_render_us = render_us;
    if (arm0_render_us > performance.max_arm_render_us) performance.max_arm_render_us = arm0_render_us;
    if (arm1_render_us > performance.max_arm_render_us) performance.max_arm_render_us = arm1_render_us;
    if (spi_wait_us > performance.max_spi_wait_us) performance.max_spi_wait_us = spi_wait_us;
    if (copy_us > performance.max_copy_us) performance.max_copy_us = copy_us;
    if (total_us > deadline_us) performance.deadline_misses++;
    if (slack_us < performance.worst_slack_us) performance.worst_slack_us = slack_us;
    portEXIT_CRITICAL(&performance_lock);
}

#if DEBUG_ROTATION
#define DEBUG_BUFFER_SIZE 32
typedef struct {
    int64_t now;
    int64_t turn_duration;
} DEBUG_rotation_log_entry;

DEBUG_rotation_log_entry DEBUG_rotlog[DEBUG_BUFFER_SIZE];
volatile int DEBUG_rot_item = 0;
#endif

uint32_t* dma_buffer;
uint32_t* dma_pixels0;
uint32_t* dma_pixels1;
// Per-arm scratch buffers, still used by the ventilagon path (display.c), which
// renders + serves directly rather than through the framebuffer.
uint32_t* draw_buffer0;
uint32_t* draw_buffer1;
extern uint8_t brillos[PIXELS];
extern uint8_t intensidades_por_led[PIXELS];

// Polar framebuffer holding the finished per-column APA102 words. The heavy
// render (render_vs2/render) runs off the per-column critical path on the
// render task (core 1, with MicroPython); the GPU serve task (core 0) only
// copies the current column's two arms out of the front buffer and clocks the
// SPI, so its per-column cost is constant regardless of scene complexity.
// Double-buffered: the render task fills fb_back, then publishes it as
// fb_front. Both live in internal SRAM, which is uncached and coherent across
// cores on the ESP32-S3.
static int num_pixels_g = 0;
static uint32_t* fb_a = NULL;
static uint32_t* fb_b = NULL;
static uint32_t* volatile fb_front = NULL;
static uint32_t* volatile fb_back = NULL;

int buf_size;
bool ventilagon_active = false;

volatile int64_t last_turn = 0;
volatile int64_t last_turn_duration = 1000000;

extern void render(int n, uint32_t* pixels);
extern void init_sprites();
extern void step();
extern void step_starfield();

inline uint32_t max(uint32_t a, uint32_t b) {
    if (b > a)
        return b;
    return a;
}

void init_buffers(int num_pixels) {
    num_pixels_g = num_pixels;
    dma_buffer = heap_caps_malloc(buf_size, MALLOC_CAP_DMA | MALLOC_CAP_32BIT);
    memset(dma_buffer, 0xff, buf_size);
    draw_buffer0 = heap_caps_malloc(buf_size, MALLOC_CAP_DEFAULT | MALLOC_CAP_32BIT);
    memset(draw_buffer0, 0x01, buf_size);
    draw_buffer1 = draw_buffer0 + num_pixels;
    dma_buffer[0]=0;
    dma_pixels0 = dma_buffer+1;
    dma_pixels1 = dma_buffer+num_pixels;
    for(int n=0; n<num_pixels; n++) {
        dma_pixels0[n] = 0x010000Ff;
        dma_pixels1[n] = 0x000100Ff;
    }

    // Two full-frame framebuffers in internal SRAM (COLUMNS * num_pixels words
    // each). Internal RAM is required: it is uncached, so the render task's
    // writes on core 1 are visible to the serve task on core 0 without any
    // cache maintenance.
    size_t fb_words = (size_t)COLUMNS * num_pixels;
    fb_a = heap_caps_malloc(fb_words * sizeof(uint32_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_32BIT);
    fb_b = heap_caps_malloc(fb_words * sizeof(uint32_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_32BIT);
    for (size_t i = 0; i < fb_words; i++) {
        fb_a[i] = 0x000000ff;
        fb_b[i] = 0x000000ff;
    }
    fb_front = fb_a;
    fb_back = fb_b;
}


void spi_init(int num_pixels) {
    buf_size = 4 + num_pixels * 4 * 2 + 8;
    init_buffers(num_pixels);
}


void spi_write_HSPI() {
    spiWriteNL(dma_buffer, buf_size);
}

void spi_shutdown() {
    free(dma_buffer);
    free(draw_buffer0);
    free(fb_a);
    free(fb_b);
}

static void IRAM_ATTR hall_neg_sensed(void* arg)
{
    int64_t this_turn = esp_timer_get_time();
    int64_t this_turn_duration = this_turn - last_turn;
    if (this_turn_duration > FASTEST_CREDIBLE_TURN) {
        last_turn_duration = this_turn_duration;
        last_turn = this_turn;
    }

#if DEBUG_ROTATION
    DEBUG_rotlog[DEBUG_rot_item].now = this_turn;
    DEBUG_rotlog[DEBUG_rot_item].turn_duration = this_turn_duration;
    DEBUG_rot_item = (DEBUG_rot_item + 1) % DEBUG_BUFFER_SIZE;
#endif
}

static void IRAM_ATTR hall_any_sensed(void* arg)
{
    int level = gpio_get_level(hall_gpio);
    if (level == false) {
        hall_neg_sensed(arg);
    }
}


void hall_init() {
    gpio_set_direction(hall_gpio, GPIO_MODE_INPUT);
#if DEBUG_ROTATION
    for (int n = 0; n<DEBUG_BUFFER_SIZE; n++) {
        DEBUG_rotlog[n].now = 0xAA55AA55;
        DEBUG_rotlog[n].turn_duration = 0xFF00FF00;
    }
    gpio_set_intr_type(hall_gpio, GPIO_INTR_ANYEDGE);
    gpio_isr_handler_add(hall_gpio, hall_any_sensed, (void*) hall_gpio);
#else
    gpio_set_intr_type(hall_gpio, GPIO_INTR_NEGEDGE);
    gpio_isr_handler_add(hall_gpio, hall_neg_sensed, (void*) hall_gpio);
#endif
}


int last_column = 0;
int column_offset = 0;
int64_t last_starfield_step = 0;

void spi_write_HSPI_blocking() {
    spiWriteBlocking(dma_buffer, buf_size);
}

// Render one whole frame (every column) into the back framebuffer, then
// publish it as the new front. Runs on the render task (core 1) so the heavy,
// scene-dependent render cost never sits on the per-column serve deadline.
static void render_frame() {
    uint32_t* back = fb_back;
    if (vs2_render_active) {
        for (int c = 0; c < COLUMNS; c++) {
            render_vs2(c, back + (size_t)c * num_pixels_g, &vs2_active_scene);
        }
    } else {
        for (int c = 0; c < COLUMNS; c++) {
            render(c, back + (size_t)c * num_pixels_g);
        }
    }
    // Publish. The store-release pairs with the serve task's load-acquire so
    // it only ever reads a fully rendered frame.
    __atomic_store_n(&fb_front, back, __ATOMIC_RELEASE);
    fb_back = (back == fb_a) ? fb_b : fb_a;

    int64_t now = esp_timer_get_time();
    if (now > last_starfield_step + 20000) {
        step_starfield();
        last_starfield_step = now;
    }
}

void renderTask( void * pvParameters ){
    printf("Render task running on core %d\n", xPortGetCoreID());
    while (true) {
        if (ventilagon_active) {
            // Ventilagon drives the strip itself from the serve loop; the
            // framebuffer path is idle.
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        render_frame();
        // Give the scheduler (MicroPython, housekeeping, idle) the core briefly
        // between frames; MicroPython at a higher priority also preempts freely.
        vTaskDelay(1);
    }
}

// Serve one column: copy its two arms out of the published framebuffer and
// clock them to the LEDs. Constant cost -- no scene rendering here -- so the
// per-column deadline is met regardless of how heavy the scene is.
void gpu_serve() {
    int64_t now = esp_timer_get_time();
    uint32_t column = (((now - last_turn) * COLUMNS / last_turn_duration) + column_offset ) % COLUMNS;
    if (column != last_column) {
        bool measuring = performance_is_enabled();
        int64_t measurement_start = measuring ? esp_timer_get_time() : 0;
        uint32_t column_deadline_us = last_turn_duration > 0
            ? (uint32_t)(last_turn_duration / COLUMNS) : 0;

        uint32_t* fb = __atomic_load_n(&fb_front, __ATOMIC_ACQUIRE);
        uint32_t* arm0 = fb + (size_t)((column + COLUMNS/2) % COLUMNS) * num_pixels_g;
        uint32_t* arm1 = fb + (size_t)column * num_pixels_g;
        for (int n = 0; n < num_pixels_g; n++) {
            dma_pixels0[n] = arm0[num_pixels_g - 1 - n];
            dma_pixels1[n] = arm1[n];
        }
        int64_t copy_end = measuring ? esp_timer_get_time() : 0;
        spi_write_HSPI_blocking();
        int64_t spi_end = measuring ? esp_timer_get_time() : 0;
        last_column = column;
        if (measuring) {
            performance_record(column, column_deadline_us,
                elapsed_us(measurement_start, spi_end),  // total
                0, 0, 0,                                 // render is off-path now
                elapsed_us(copy_end, spi_end),           // spi transfer
                elapsed_us(measurement_start, copy_end));// framebuffer copy
        }
    }
}


void coreTask( void * pvParameters ){
    printf("GPU serve task running on core %d\n", xPortGetCoreID());

    hall_init();

    spiStartBuses(led_spi_host, led_freq, led_clk, led_mosi, led_cs);
    spiAcquire();

    // The heavy render runs on core 1 alongside MicroPython (priority below it,
    // so it only uses MicroPython's idle slack); this serve task keeps core 0
    // for the constant-cost per-column output.
    xTaskCreatePinnedToCore(renderTask, "renderTask", 10000, NULL, 1, NULL, 1);

    while(true){
        if (ventilagon_active) {
            ventilagon_loop();
        } else {
            gpu_serve();
        }
    }
    vTaskDelete(NULL);
}

bool already_initialized = false;


static mp_obj_t povdisplay_init(size_t n_args, const mp_obj_t *args) {
    int num_pixels = mp_obj_get_int(args[0]);
    hall_gpio = mp_obj_get_int(args[1]);
    irdiode_gpio = mp_obj_get_int(args[2]);
    led_spi_host = mp_obj_get_int(args[3]);
    led_clk = mp_obj_get_int(args[4]);
    led_mosi = mp_obj_get_int(args[5]);
    led_cs = mp_obj_get_int(args[6]);
    led_freq = mp_obj_get_int(args[7]);

    if (already_initialized) {
        ventilagon_exit();
        return mp_const_none;
    }
    already_initialized = true;


    spi_init(num_pixels);
    printf("Micropython running on core %d\n", xPortGetCoreID());
    ventilagon_init();

    // This must complete before povdisplay.init() returns.  Recovery creates
    // its status sprite immediately afterwards; doing the reset in coreTask
    // let the newly spawned GPU task erase that sprite before its first
    // render.
    init_sprites();

    xTaskCreatePinnedToCore(
            coreTask,   /* Function to implement the task */
            "coreTask", /* Name of the task */
            10000,      /* Stack size in words */
            NULL,       /* Task input parameter */
            10,          /* Priority of the task */
            NULL,       /* Task handle. */
            GPU_TASK_CORE);  /* Core where the task should run */
    gamma_mode = 0;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(povdisplay_init_obj, 8, 8, povdisplay_init);

// ------------------------------

static mp_obj_t povdisplay_set_palettes(mp_obj_t palette) {
    palette_pal = (uint32_t *) memoryview_data(palette);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(povdisplay_set_palettes_obj, povdisplay_set_palettes);

// ------------------------------

static mp_obj_t povdisplay_set_gamma_mode(mp_obj_t mode) {
    gamma_mode = mp_obj_get_int(mode);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(povdisplay_set_gamma_mode_obj, povdisplay_set_gamma_mode);

// ------------------------------

static mp_obj_t povdisplay_set_color_profile(mp_obj_t profile) {
    mp_buffer_info_t buffer;
    mp_get_buffer_raise(profile, &buffer, MP_BUFFER_READ);
    if (!color_pipeline_apply(buffer.buf, buffer.len)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid POV colour profile"));
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(povdisplay_set_color_profile_obj, povdisplay_set_color_profile);

// ------------------------------

static mp_obj_t povdisplay_set_color_test_pattern(size_t n_args, const mp_obj_t *args) {
    int pattern = mp_obj_get_int(args[0]);
    int level = n_args > 1 ? mp_obj_get_int(args[1]) : 255;
    if (pattern < 0 || level < 0 || level > 255
        || !color_pipeline_set_test_pattern(pattern, level)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid POV colour test pattern"));
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(povdisplay_set_color_test_pattern_obj, 1, 2, povdisplay_set_color_test_pattern);

// ------------------------------

static mp_obj_t povdisplay_set_color_pipeline_enabled(mp_obj_t enabled) {
    if (!color_pipeline_set_enabled(mp_obj_is_true(enabled))) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("POV colour profile unavailable"));
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(povdisplay_set_color_pipeline_enabled_obj, povdisplay_set_color_pipeline_enabled);

// ------------------------------

static mp_obj_t povdisplay_set_performance_profiling(mp_obj_t enabled) {
    bool value = mp_obj_is_true(enabled);
    if (value) {
        performance_reset();
    }
    __atomic_store_n(&performance_enabled, value, __ATOMIC_RELEASE);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(povdisplay_set_performance_profiling_obj, povdisplay_set_performance_profiling);

static mp_obj_t povdisplay_reset_performance_stats(void) {
    performance_reset();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(povdisplay_reset_performance_stats_obj, povdisplay_reset_performance_stats);

static void performance_dict_int(mp_obj_t dict, qstr key, mp_int_t value) {
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(key), mp_obj_new_int(value));
}

static mp_obj_t povdisplay_get_performance_stats(void) {
    pov_performance_t snapshot;
    portENTER_CRITICAL(&performance_lock);
    snapshot = performance;
    portEXIT_CRITICAL(&performance_lock);

    uint32_t samples = snapshot.samples;
    mp_obj_t dict = mp_obj_new_dict(20);
    performance_dict_int(dict, MP_QSTR_enabled, performance_is_enabled());
    performance_dict_int(dict, MP_QSTR_calibrated, color_pipeline_is_active());
    performance_dict_int(dict, MP_QSTR_vs2, vs2_render_active);
    performance_dict_int(dict, MP_QSTR_sprites, vs2_render_active ? vs2_active_scene.sprite_count : 0);
    performance_dict_int(dict, MP_QSTR_tilemaps, vs2_render_active ? vs2_active_scene.tilemap_count : 0);
    performance_dict_int(dict, MP_QSTR_layers, vs2_render_active ? vs2_active_scene.layer_count : 0);
    performance_dict_int(dict, MP_QSTR_samples, samples);
    performance_dict_int(dict, MP_QSTR_skipped_updates, snapshot.skipped_updates);
    performance_dict_int(dict, MP_QSTR_deadline_misses, snapshot.deadline_misses);
    performance_dict_int(dict, MP_QSTR_deadline_us, snapshot.deadline_us);
    performance_dict_int(dict, MP_QSTR_avg_total_us, samples ? snapshot.total_us / samples : 0);
    performance_dict_int(dict, MP_QSTR_max_total_us, snapshot.max_total_us);
    performance_dict_int(dict, MP_QSTR_avg_render_us, samples ? snapshot.render_us / samples : 0);
    performance_dict_int(dict, MP_QSTR_max_render_us, snapshot.max_render_us);
    performance_dict_int(dict, MP_QSTR_max_arm_render_us, snapshot.max_arm_render_us);
    performance_dict_int(dict, MP_QSTR_avg_spi_wait_us, samples ? snapshot.spi_wait_us / samples : 0);
    performance_dict_int(dict, MP_QSTR_max_spi_wait_us, snapshot.max_spi_wait_us);
    performance_dict_int(dict, MP_QSTR_avg_copy_us, samples ? snapshot.copy_us / samples : 0);
    performance_dict_int(dict, MP_QSTR_max_copy_us, snapshot.max_copy_us);
    performance_dict_int(dict, MP_QSTR_worst_slack_us,
        samples ? snapshot.worst_slack_us : 0);
    return dict;
}
static MP_DEFINE_CONST_FUN_OBJ_0(povdisplay_get_performance_stats_obj, povdisplay_get_performance_stats);

// ------------------------------

static mp_obj_t povdisplay_set_column_offset(mp_obj_t offset) {
    column_offset = mp_obj_get_int(offset) % COLUMNS;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(povdisplay_set_column_offset_obj, povdisplay_set_column_offset);

static mp_obj_t povdisplay_get_column_offset() {
    return mp_obj_new_int(column_offset);
}
static MP_DEFINE_CONST_FUN_OBJ_0(povdisplay_get_column_offset_obj, povdisplay_get_column_offset);

// ------------------------------
static mp_obj_t povdisplay_getaddress(mp_obj_t sprite_num) {
    int num = mp_obj_get_int(sprite_num);
#if DEBUG_ROTATION
    if (num == 997) {
        return mp_obj_new_int((mp_int_t)(uintptr_t)brillos);
    }
    if (num == 998) {
        return mp_obj_new_int((mp_int_t)(uintptr_t)intensidades_por_led);
    }
    if (num == 999) {
        return mp_obj_new_int((mp_int_t)(uintptr_t)DEBUG_rotlog);
    }
#endif
    return mp_obj_new_int((mp_int_t)(uintptr_t)&sprites[num]);
}
static MP_DEFINE_CONST_FUN_OBJ_1(povdisplay_getaddress_obj, povdisplay_getaddress);
// ------------------------------
static mp_obj_t povdisplay_last_turn_duration() {
    return mp_obj_new_int(last_turn_duration);
}
static MP_DEFINE_CONST_FUN_OBJ_0(povdisplay_last_turn_duration_obj, povdisplay_last_turn_duration);
// ------------------------------

static const mp_map_elem_t povdisplay_globals_table[] = {
    { MP_OBJ_NEW_QSTR(MP_QSTR___name__), MP_OBJ_NEW_QSTR(MP_QSTR_vshw_povdisplay) },
    { MP_OBJ_NEW_QSTR(MP_QSTR_init), (mp_obj_t)&povdisplay_init_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_set_palettes), (mp_obj_t)&povdisplay_set_palettes_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_set_gamma_mode), (mp_obj_t)&povdisplay_set_gamma_mode_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_set_color_profile), (mp_obj_t)&povdisplay_set_color_profile_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_set_color_test_pattern), (mp_obj_t)&povdisplay_set_color_test_pattern_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_set_color_pipeline_enabled), (mp_obj_t)&povdisplay_set_color_pipeline_enabled_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_set_performance_profiling), (mp_obj_t)&povdisplay_set_performance_profiling_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_reset_performance_stats), (mp_obj_t)&povdisplay_reset_performance_stats_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_get_performance_stats), (mp_obj_t)&povdisplay_get_performance_stats_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_set_column_offset), (mp_obj_t)&povdisplay_set_column_offset_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_get_column_offset), (mp_obj_t)&povdisplay_get_column_offset_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_getaddress), (mp_obj_t)&povdisplay_getaddress_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_last_turn_duration), (mp_obj_t)&povdisplay_last_turn_duration_obj },
};

static MP_DEFINE_CONST_DICT (
    mp_module_povdisplay_globals,
    povdisplay_globals_table
);

const mp_obj_module_t mp_module_povdisplay = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t*)&mp_module_povdisplay_globals,
};

MP_REGISTER_MODULE(MP_QSTR_vshw_povdisplay, mp_module_povdisplay);

// ------------------------------

static mp_obj_t ventilagon_ventilagon_enter(void) {
    ventilagon_enter();
    ventilagon_active = true;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(ventilagon_ventilagon_enter_obj, ventilagon_ventilagon_enter);

static mp_obj_t ventilagon_ventilagon_exit(void) {
    ventilagon_exit();
    ventilagon_active = false;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(ventilagon_ventilagon_exit_obj, ventilagon_ventilagon_exit);

static mp_obj_t ventilagon_ventilagon_received(mp_obj_t mp_value) {
    byte value = mp_obj_get_int(mp_value);
    xQueueSend(queue_received, &value, 0);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(ventilagon_ventilagon_received_obj, ventilagon_ventilagon_received);

static mp_obj_t ventilagon_ventilagon_sending(void) {
    char* buff;
    if( xQueueReceive( queue_sending, &buff, 0 ) ) {
        return mp_obj_new_str(buff, strlen(buff));
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(ventilagon_ventilagon_sending_obj, ventilagon_ventilagon_sending);

static mp_obj_t ventilagon_ventilagon_is_idle(void) {
    if (ventilagon_is_idle()) {
        return mp_const_true;
    } else {
        return mp_const_false;
    }
}
static MP_DEFINE_CONST_FUN_OBJ_0(ventilagon_ventilagon_is_idle_obj, ventilagon_ventilagon_is_idle);


// ------------------------------

static const mp_map_elem_t ventilagon_globals_table[] = {
    { MP_OBJ_NEW_QSTR(MP_QSTR___name__), MP_OBJ_NEW_QSTR(MP_QSTR_ventilagon) },
    { MP_OBJ_NEW_QSTR(MP_QSTR_enter), (mp_obj_t)&ventilagon_ventilagon_enter_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_exit), (mp_obj_t)&ventilagon_ventilagon_exit_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_received), (mp_obj_t)&ventilagon_ventilagon_received_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_sending), (mp_obj_t)&ventilagon_ventilagon_sending_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_is_idle), (mp_obj_t)&ventilagon_ventilagon_is_idle_obj },
};

static MP_DEFINE_CONST_DICT (
    mp_module_ventilagon_globals,
    ventilagon_globals_table
);

const mp_obj_module_t mp_module_ventilagon = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t*)&mp_module_ventilagon_globals,
};

MP_REGISTER_MODULE(MP_QSTR_ventilagon, mp_module_ventilagon);
