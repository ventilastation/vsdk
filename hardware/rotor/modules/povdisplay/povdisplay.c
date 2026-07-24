#include "freertos/idf_additions.h" // for xTaskCreatePinnedToCore
#include "py/nlr.h"
#include "py/obj.h"
#include "py/objstr.h"
#include "py/runtime.h"
#include "py/binary.h"
#include "mphalport.h"


#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"

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

// DIAGNOSTIC: framebuffer allocation forensics, captured once at init and
// queryable later via get_performance_stats() -- early-boot printf is lost
// on this port (USB-CDC drops output before the host enumerates), so this is
// the only reliable way to see it after the fact.
uint32_t diag_fb_bytes_requested = 0;
uint32_t diag_internal_free_before = 0;
uint32_t diag_internal_largest_before = 0;
uint32_t diag_internal_free_after = 0;
uint32_t diag_fb_a_addr = 0;
uint32_t diag_fb_b_addr = 0;
uint32_t diag_fb_a_size = 0;
uint32_t diag_fb_b_size = 0;

// DIAGNOSTIC: guard-canary regions immediately before fb_a, between fb_a and
// fb_b, and after fb_b (one combined allocation instead of two separate
// mallocs, so these sit exactly where a heap-adjacent overflow into either
// framebuffer would have to land). Filled with an index-encoded sentinel and
// re-checked periodically; a mismatch means something outside this module
// wrote into or through the framebuffer's memory.
#define DIAG_GUARD_WORDS 16
static uint32_t* diag_guard_before = NULL;
static uint32_t* diag_guard_mid = NULL;
static uint32_t* diag_guard_after = NULL;
volatile uint32_t diag_canary_corrupt_words = 0;
volatile uint32_t diag_canary_first_bad_region = 0;  // 0=none, 1=before, 2=mid, 3=after
volatile uint32_t diag_canary_first_bad_offset = 0;
volatile uint32_t diag_canary_first_bad_value = 0;
volatile uint32_t diag_canary_checks = 0;

static uint32_t diag_canary_sentinel(uint32_t region, uint32_t i) {
    return 0xCA5E0000u | (region << 12) | i;
}

static void diag_canary_fill(uint32_t* region, uint32_t region_id) {
    for (uint32_t i = 0; i < DIAG_GUARD_WORDS; i++) {
        region[i] = diag_canary_sentinel(region_id, i);
    }
}

static void diag_canary_check_region(uint32_t* region, uint32_t region_id) {
    for (uint32_t i = 0; i < DIAG_GUARD_WORDS; i++) {
        uint32_t expected = diag_canary_sentinel(region_id, i);
        uint32_t actual = region[i];
        if (actual != expected) {
            diag_canary_corrupt_words++;
            if (diag_canary_first_bad_region == 0) {
                diag_canary_first_bad_region = region_id;
                diag_canary_first_bad_offset = i;
                diag_canary_first_bad_value = actual;
            }
        }
    }
}

// Called once per publish (cheap: 48 word compares). Latches the FIRST
// corruption seen; diag_canary_corrupt_words keeps counting so a persistent
// vs. one-shot clobber can be told apart.
static void diag_canary_check(void) {
    if (!diag_guard_before) {
        return;
    }
    diag_canary_check_region(diag_guard_before, 1);
    diag_canary_check_region(diag_guard_mid, 2);
    diag_canary_check_region(diag_guard_after, 3);
    diag_canary_checks++;
}

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
    // The strip is one continuous run through the hub, not two separate arms --
    // with an odd total LED count, the centre LED is physically shared by both
    // sweeps. dma_pixels0's last word and dma_pixels1's first word are meant to
    // alias that same centre LED (whichever write lands last in the copy loop is
    // what's shown there); this is intentional, not a bug.
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
    size_t fb_bytes = fb_words * sizeof(uint32_t);
    diag_fb_bytes_requested = (uint32_t)fb_bytes;
    diag_internal_free_before = (uint32_t)heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    diag_internal_largest_before = (uint32_t)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);

    // One combined allocation -- guard | fb_a | guard | fb_b | guard -- so the
    // canary regions sit exactly where a heap-adjacent overflow into either
    // framebuffer would have to pass through. See diag_canary_check().
    size_t combined_words = DIAG_GUARD_WORDS + fb_words + DIAG_GUARD_WORDS + fb_words + DIAG_GUARD_WORDS;
    uint32_t* combined = heap_caps_malloc(combined_words * sizeof(uint32_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_32BIT);
    if (combined) {
        diag_guard_before = combined;
        fb_a = combined + DIAG_GUARD_WORDS;
        diag_guard_mid = fb_a + fb_words;
        fb_b = diag_guard_mid + DIAG_GUARD_WORDS;
        diag_guard_after = fb_b + fb_words;
        diag_canary_fill(diag_guard_before, 1);
        diag_canary_fill(diag_guard_mid, 2);
        diag_canary_fill(diag_guard_after, 3);
    } else {
        printf("POV fb: combined allocation FAILED\n");
        fb_a = NULL;
        fb_b = NULL;
    }
    diag_fb_a_addr = (uint32_t)(uintptr_t)fb_a;
    diag_fb_b_addr = (uint32_t)(uintptr_t)fb_b;
    diag_fb_a_size = (uint32_t)(combined ? heap_caps_get_allocated_size(combined) : 0);
    diag_fb_b_size = diag_fb_a_size;
    if (!fb_a) {
        printf("POV fb: fb_a allocation FAILED\n");
    }
    if (!fb_b) {
        printf("POV fb: fb_b allocation FAILED, falling back to single-buffer (tear-tolerant)\n");
        fb_b = fb_a;
    }
    for (size_t i = 0; i < fb_words; i++) {
        fb_a[i] = 0x000000ff;
        fb_b[i] = 0x000000ff;
    }
    fb_front = fb_a;
    fb_back = fb_b;
    diag_internal_free_after = (uint32_t)heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
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
    // fb_a/fb_b are offsets into the single diag_guard_before..diag_guard_after
    // allocation (see init_buffers) -- free the block once, from its start.
    free(diag_guard_before);
}

// DIAGNOSTIC: counts real hall-validated revolutions and framebuffer
// publishes, so povperf can report publishes-per-revolution -- a direct,
// serial-reliable (no Wi-Fi needed) check for whether a render pass is
// completing faster than one physical revolution (see project_next_column()).
// Plain word writes/reads: 32-bit and word-aligned, atomic enough on Xtensa
// for a monotonic counter read as an instantaneous snapshot.
volatile uint32_t diag_hall_revolutions = 0;
volatile uint32_t diag_publish_count = 0;

static void IRAM_ATTR hall_neg_sensed(void* arg)
{
    int64_t this_turn = esp_timer_get_time();
    int64_t this_turn_duration = this_turn - last_turn;
    if (this_turn_duration > FASTEST_CREDIBLE_TURN) {
        last_turn_duration = this_turn_duration;
        last_turn = this_turn;
        diag_hall_revolutions++;
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

// DIAGNOSTIC: when active, project_next_column() fills the framebuffer with
// this deterministic pattern instead of calling the real renderer, and
// gpu_serve() self-checks every served pixel against it right after copying
// into the DMA staging buffer -- through the SAME project_next_column() /
// gpu_serve() code paths real gameplay uses, at full per-column granularity
// (up to 256 checks/revolution vs. the once-per-publish canary check), so a
// mismatch pinpoints exactly which (column, led, arm) diverged and what
// value appeared, with no capture needed.
volatile bool diag_test_pattern_active = false;
volatile uint32_t diag_serve_checks = 0;
volatile uint32_t diag_mismatch_count = 0;
volatile uint32_t diag_mismatch_arm0_count = 0;
volatile uint32_t diag_mismatch_arm1_count = 0;
volatile uint32_t diag_mismatch_front_a_count = 0;  // mismatches while fb_front==fb_a
volatile uint32_t diag_mismatch_front_b_count = 0;  // mismatches while fb_front==fb_b
volatile uint32_t diag_mismatch_first_column = 0xffffffffu;
volatile uint32_t diag_mismatch_first_led = 0;
volatile uint32_t diag_mismatch_first_arm = 0;  // 0 = arm1 (column), 1 = arm0 (column+128)
volatile uint32_t diag_mismatch_first_expected = 0;
volatile uint32_t diag_mismatch_first_actual = 0;
volatile uint32_t diag_mismatch_last_column = 0xffffffffu;
volatile uint32_t diag_mismatch_last_led = 0;
volatile uint32_t diag_mismatch_last_arm = 0;
volatile uint32_t diag_mismatch_last_expected = 0;
volatile uint32_t diag_mismatch_last_actual = 0;

static uint32_t diag_pattern_value(uint32_t column, uint32_t led) {
    return ((column & 0xffu) << 24) | ((led & 0xffu) << 16) | 0x000000ffu;
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

static int render_col = 0;

// Render one framebuffer column into fb_back. Called exactly once per real
// gpu_serve() tick (see below) -- never faster -- so a full 256-column pass
// can never complete in less than one physical revolution. That matters:
// project_next_column() used to be called unconditionally on every spin of
// coreTask()'s loop, including the many spins where the physical column
// hadn't advanced yet. Because rendering a column is usually faster than a
// column's dwell time, that let a render pass lap the fan -- fb_front could
// flip more than once per revolution, at a wall-clock moment with no relation
// to where the fan physically was. The columns served after such a flip
// jumped to a newer content generation than the columns served earlier in
// the same sweep: a visible seam, landing wherever that revolution's lead
// happened to cross a full lap, and only guaranteed to heal at the next
// physical wrap (column 255->0), since that's the next point the ring is
// guaranteed to be serving one single, fully-published generation throughout.
// Gating this call under the same condition as the serve (one column
// rendered per one column served) makes that impossible: render can never
// get ahead of the physical rotation.
static void project_next_column() {
    uint32_t* back = fb_back;
    if (diag_test_pattern_active) {
        uint32_t* slot = back + (size_t)render_col * num_pixels_g;
        for (int n = 0; n < num_pixels_g; n++) {
            slot[n] = diag_pattern_value(render_col, n);
        }
    } else if (vs2_render_active) {
        render_vs2(render_col, back + (size_t)render_col * num_pixels_g, &vs2_active_scene);
    } else {
        render(render_col, back + (size_t)render_col * num_pixels_g);
    }
    if (++render_col >= COLUMNS) {
        render_col = 0;
        fb_front = back;
        fb_back = (back == fb_a) ? fb_b : fb_a;
        diag_publish_count++;
        diag_canary_check();
        int64_t now = esp_timer_get_time();
        if (now > last_starfield_step + 20000) {
            step_starfield();
            last_starfield_step = now;
        }
    }
}

// Serve the column currently under the LEDs, if the fan has advanced to a new
// one: copy that column's two arms out of the published framebuffer and start
// the DMA. Cheap and constant-cost -- no scene rendering here -- so it always
// meets the per-column deadline. project_next_column() runs right after
// queuing the (async) DMA, so its render work overlaps that column's transfer
// instead of sitting in front of the next tick's deadline; the next call's
// spiWaitComplete() collects it.
static void gpu_serve() {
    int64_t now = esp_timer_get_time();
    // Floor-mod: the C % operator keeps the sign of its dividend, and the
    // dividend can go negative (a stored negative column_offset, or the hall
    // ISR updating last_turn between our two reads). A negative value cast to
    // uint32_t would index far outside fb_front below, so fold it into
    // [0, COLUMNS) first.
    int64_t raw_column = (((now - last_turn) * COLUMNS / last_turn_duration) + column_offset ) % COLUMNS;
    if (raw_column < 0) {
        raw_column += COLUMNS;
    }
    uint32_t column = (uint32_t)raw_column;
    if (column != last_column) {
        bool measuring = performance_is_enabled();
        int64_t measurement_start = measuring ? esp_timer_get_time() : 0;
        uint32_t column_deadline_us = last_turn_duration > 0
            ? (uint32_t)(last_turn_duration / COLUMNS) : 0;

        spiWaitComplete();  // wait for the previous DMA (it overlapped the projection)
        int64_t wait_end = measuring ? esp_timer_get_time() : 0;

        uint32_t* fb = fb_front;
        uint32_t arm0_column = (column + COLUMNS/2) % COLUMNS;
        uint32_t* arm0 = fb + (size_t)arm0_column * num_pixels_g;
        uint32_t* arm1 = fb + (size_t)column * num_pixels_g;
        for (int n = 0; n < num_pixels_g; n++) {
            dma_pixels0[n] = arm0[num_pixels_g - 1 - n];
            dma_pixels1[n] = arm1[n];
        }
        if (diag_test_pattern_active) {
            bool front_is_a = (fb == fb_a);
            for (int n = 0; n < num_pixels_g; n++) {
                // n==0 of dma_pixels1 aliases dma_pixels0[num_pixels_g-1] (the
                // shared centre LED, see init_buffers) -- whichever write lands
                // last there is correct by design, not a mismatch to flag.
                uint32_t expected1 = diag_pattern_value(column, n);
                if (n != 0 && dma_pixels1[n] != expected1) {
                    diag_mismatch_count++;
                    diag_mismatch_arm1_count++;
                    if (front_is_a) diag_mismatch_front_a_count++; else diag_mismatch_front_b_count++;
                    if (diag_mismatch_first_column == 0xffffffffu) {
                        diag_mismatch_first_column = column;
                        diag_mismatch_first_led = n;
                        diag_mismatch_first_arm = 0;
                        diag_mismatch_first_expected = expected1;
                        diag_mismatch_first_actual = dma_pixels1[n];
                    }
                    diag_mismatch_last_column = column;
                    diag_mismatch_last_led = n;
                    diag_mismatch_last_arm = 0;
                    diag_mismatch_last_expected = expected1;
                    diag_mismatch_last_actual = dma_pixels1[n];
                }
                uint32_t arm0_led = num_pixels_g - 1 - n;
                uint32_t expected0 = diag_pattern_value(arm0_column, arm0_led);
                if (dma_pixels0[n] != expected0) {
                    diag_mismatch_count++;
                    diag_mismatch_arm0_count++;
                    if (front_is_a) diag_mismatch_front_a_count++; else diag_mismatch_front_b_count++;
                    if (diag_mismatch_first_column == 0xffffffffu) {
                        diag_mismatch_first_column = arm0_column;
                        diag_mismatch_first_led = arm0_led;
                        diag_mismatch_first_arm = 1;
                        diag_mismatch_first_expected = expected0;
                        diag_mismatch_first_actual = dma_pixels0[n];
                    }
                    diag_mismatch_last_column = arm0_column;
                    diag_mismatch_last_led = arm0_led;
                    diag_mismatch_last_arm = 1;
                    diag_mismatch_last_expected = expected0;
                    diag_mismatch_last_actual = dma_pixels0[n];
                }
            }
            diag_serve_checks++;
        }
        spi_write_HSPI();   // queue the DMA (async); it runs during the projection below
        int64_t queue_end = measuring ? esp_timer_get_time() : 0;
        last_column = column;
        if (measuring) {
            performance_record(column, column_deadline_us,
                elapsed_us(measurement_start, queue_end),  // total
                0, 0, 0,                                    // projection off-path
                elapsed_us(measurement_start, wait_end),   // spi wait
                elapsed_us(wait_end, queue_end));           // framebuffer copy
        }
        project_next_column();  // overlaps the DMA just queued above
    }
}


void coreTask( void * pvParameters ){
    printf("GPU task running on core %d\n", xPortGetCoreID());

    hall_init();

    spiStartBuses(led_spi_host, led_freq, led_clk, led_mosi, led_cs);
    spiAcquire();

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

// DIAGNOSTIC: see diag_test_pattern_active's declaration above.
static mp_obj_t povdisplay_set_diag_test_pattern(mp_obj_t enabled) {
    bool value = mp_obj_is_true(enabled);
    if (value) {
        diag_serve_checks = 0;
        diag_mismatch_count = 0;
        diag_mismatch_arm0_count = 0;
        diag_mismatch_arm1_count = 0;
        diag_mismatch_front_a_count = 0;
        diag_mismatch_front_b_count = 0;
        diag_mismatch_first_column = 0xffffffffu;
        diag_mismatch_first_led = 0;
        diag_mismatch_first_arm = 0;
        diag_mismatch_first_expected = 0;
        diag_mismatch_first_actual = 0;
        diag_mismatch_last_column = 0xffffffffu;
        diag_mismatch_last_led = 0;
        diag_mismatch_last_arm = 0;
        diag_mismatch_last_expected = 0;
        diag_mismatch_last_actual = 0;
    }
    __atomic_store_n(&diag_test_pattern_active, value, __ATOMIC_RELEASE);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(povdisplay_set_diag_test_pattern_obj, povdisplay_set_diag_test_pattern);

static void performance_dict_int(mp_obj_t dict, qstr key, mp_int_t value) {
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(key), mp_obj_new_int(value));
}

static mp_obj_t povdisplay_get_performance_stats(void) {
    pov_performance_t snapshot;
    portENTER_CRITICAL(&performance_lock);
    snapshot = performance;
    portEXIT_CRITICAL(&performance_lock);

    uint32_t samples = snapshot.samples;
    mp_obj_t dict = mp_obj_new_dict(58);
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
    performance_dict_int(dict, MP_QSTR_diag_hall_revolutions, diag_hall_revolutions);
    performance_dict_int(dict, MP_QSTR_diag_publish_count, diag_publish_count);
    performance_dict_int(dict, MP_QSTR_diag_fb_bytes_requested, diag_fb_bytes_requested);
    performance_dict_int(dict, MP_QSTR_diag_internal_free_before, diag_internal_free_before);
    performance_dict_int(dict, MP_QSTR_diag_internal_largest_before, diag_internal_largest_before);
    performance_dict_int(dict, MP_QSTR_diag_internal_free_after, diag_internal_free_after);
    performance_dict_int(dict, MP_QSTR_diag_fb_a_addr, diag_fb_a_addr);
    performance_dict_int(dict, MP_QSTR_diag_fb_b_addr, diag_fb_b_addr);
    performance_dict_int(dict, MP_QSTR_diag_fb_a_size, diag_fb_a_size);
    performance_dict_int(dict, MP_QSTR_diag_fb_b_size, diag_fb_b_size);
    performance_dict_int(dict, MP_QSTR_diag_canary_checks, diag_canary_checks);
    performance_dict_int(dict, MP_QSTR_diag_canary_corrupt_words, diag_canary_corrupt_words);
    performance_dict_int(dict, MP_QSTR_diag_canary_first_bad_region, diag_canary_first_bad_region);
    performance_dict_int(dict, MP_QSTR_diag_canary_first_bad_offset, diag_canary_first_bad_offset);
    performance_dict_int(dict, MP_QSTR_diag_canary_first_bad_value, diag_canary_first_bad_value);
    performance_dict_int(dict, MP_QSTR_diag_serve_checks, diag_serve_checks);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_count, diag_mismatch_count);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_first_column, diag_mismatch_first_column);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_first_led, diag_mismatch_first_led);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_first_arm, diag_mismatch_first_arm);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_first_expected, diag_mismatch_first_expected);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_first_actual, diag_mismatch_first_actual);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_arm0_count, diag_mismatch_arm0_count);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_arm1_count, diag_mismatch_arm1_count);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_front_a_count, diag_mismatch_front_a_count);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_front_b_count, diag_mismatch_front_b_count);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_last_column, diag_mismatch_last_column);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_last_led, diag_mismatch_last_led);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_last_arm, diag_mismatch_last_arm);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_last_expected, diag_mismatch_last_expected);
    performance_dict_int(dict, MP_QSTR_diag_mismatch_last_actual, diag_mismatch_last_actual);
    performance_dict_int(dict, MP_QSTR_diag_num_pixels_g, num_pixels_g);
    return dict;
}
static MP_DEFINE_CONST_FUN_OBJ_0(povdisplay_get_performance_stats_obj, povdisplay_get_performance_stats);

// ------------------------------

static mp_obj_t povdisplay_set_column_offset(mp_obj_t offset) {
    // Normalize to [0, COLUMNS): the settings scene can step the offset below
    // zero and the stored NVS value may already be negative. The retro-go
    // driver normalizes the same value on its side (ventilastation_pov.c).
    column_offset = ((mp_obj_get_int(offset) % COLUMNS) + COLUMNS) % COLUMNS;
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
    { MP_OBJ_NEW_QSTR(MP_QSTR_set_diag_test_pattern), (mp_obj_t)&povdisplay_set_diag_test_pattern_obj },
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
