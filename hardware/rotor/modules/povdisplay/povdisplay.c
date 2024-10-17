#include "freertos/idf_additions.h" // for xTaskCreatePinnedToCore
#include "py/nlr.h"
#include "py/obj.h"
#include "py/objstr.h"
#include "py/runtime.h"
#include "py/binary.h"
#include "mphalport.h"


#include "driver/gpio.h"

#include <stdio.h>
#include <string.h>
#include <inttypes.h>

#include "minispi.h"
#include "gpu.h"
#include "ventilagon/ventilagon.h"

#define GPIO_HALL     GPIO_NUM_26
#define GPIO_HALL_B     GPIO_NUM_4
#define GPIO_DEBUG     GPIO_NUM_18

//#define printf(...) mp_printf(MP_PYTHON_PRINTER, __VA_ARGS__)

#define ESP_INTR_FLAG_DEFAULT 0
#define COLUMNS 256
#define FASTEST_CREDIBLE_TURN 10000 // if the fan is going over 100 FPS, then I don't believe it, and discard the reading

#define DEBUG_ROTATION 0

#ifdef DEBUG_ROTATION
#define DEBUG_BUFFER_SIZE 32
typedef struct {
    int64_t now;
    int64_t turn_duration;
} DEBUG_rotation_log_entry;

DEBUG_rotation_log_entry DEBUG_rotlog[DEBUG_BUFFER_SIZE];
volatile int DEBUG_rot_item = 0;
#endif

char* spi_buf;
uint32_t* extra_buf;
uint32_t* pixels0;
uint32_t* pixels1;

int buf_size;
bool ventilagon_active = false;

volatile int64_t last_turn = 0;
volatile int64_t last_turn_duration = 102400;

extern void render(int n, uint32_t* pixels);
extern void init_sprites();
extern void step();
extern void step_starfield();

inline uint32_t max(uint32_t a, uint32_t b) {
    if (b > a)
        return b;
    return a;
}

char* init_buffers(int num_pixels) {
    spi_buf=heap_caps_malloc(buf_size, MALLOC_CAP_DMA | MALLOC_CAP_32BIT);
    memset(spi_buf, 0xff, buf_size);
    extra_buf=heap_caps_malloc(buf_size/2, MALLOC_CAP_DEFAULT);
    memset(extra_buf, 0x01, buf_size/2);
    ((uint32_t*)spi_buf)[0]=0;
    pixels0 = (uint32_t*)(spi_buf+4);
    pixels1 = (uint32_t*)(spi_buf+num_pixels*4);
    for(int n=0; n<num_pixels; n++) {
        pixels0[n] = 0x010000Ff;
        pixels1[n] = 0x000100Ff;
    }
    return spi_buf;
}


void spi_init(int num_pixels) {
    buf_size = 4 + num_pixels * 4 * 2 + 8;
    const long freq = 20000000;
    spiStartBuses(freq);
    init_buffers(num_pixels);
}


void spi_write_HSPI() {
    spiWriteNL(2, spi_buf, buf_size);
}

void spi_shutdown() {
    free(spi_buf);
}


static int taskCore = 0;

void delay(int ms) {
    uint32_t end = esp_timer_get_time() + ms * 1000;
    while (esp_timer_get_time() < end) {
    }
}

int color = 0;
uint32_t count = 0;

 
static void IRAM_ATTR hall_neg_sensed(void* arg)
{
    int64_t this_turn = esp_timer_get_time();
    int64_t this_turn_duration = this_turn - last_turn;
    if (this_turn_duration > FASTEST_CREDIBLE_TURN) {
        last_turn_duration = this_turn_duration;
        last_turn = this_turn;
    }

#ifdef DEBUG_ROTATION
    DEBUG_rotlog[DEBUG_rot_item].now = this_turn;
    DEBUG_rotlog[DEBUG_rot_item].turn_duration = this_turn_duration;
    DEBUG_rot_item = (DEBUG_rot_item + 1) % DEBUG_BUFFER_SIZE;
#endif
}

static void IRAM_ATTR hall_any_sensed(void* arg)
{
    int level = gpio_get_level(GPIO_HALL_B);
    if (level == false) {
        hall_neg_sensed(arg);
    }
    gpio_set_level(GPIO_NUM_38, level);
}


void hall_init(int gpio_hall) {
    gpio_set_direction(gpio_hall, GPIO_MODE_INPUT);
#ifdef DEBUG_ROTATION
    for (int n = 0; n<DEBUG_BUFFER_SIZE; n++) {
        DEBUG_rotlog[n].now = 0xAA55AA55;
        DEBUG_rotlog[n].turn_duration = 0xFF00FF00;
    }
    gpio_set_intr_type(gpio_hall, GPIO_INTR_ANYEDGE);
    gpio_isr_handler_add(gpio_hall, hall_any_sensed, (void*) gpio_hall);
#else
    gpio_set_intr_type(gpio_hall, GPIO_INTR_NEGEDGE);
    gpio_isr_handler_add(gpio_hall, hall_neg_sensed, (void*) gpio_hall);
#endif
}


int last_column = 0;
int64_t last_starfield_step = 0;
void gpu_step() {
    int64_t now = esp_timer_get_time();
    uint32_t column = ((now - last_turn) * COLUMNS / last_turn_duration) % COLUMNS;
    if (column != last_column) {
	gpio_set_level(GPIO_DEBUG, true);
	render((column + COLUMNS/2) % COLUMNS, extra_buf);
	for(int n=0; n<54; n++) {
	    pixels0[n] = extra_buf[53-n];
	}
	render(column, pixels1);
	gpio_set_level(GPIO_DEBUG, false);
	spi_write_HSPI();
	last_column = column;
    }

    if (now > last_starfield_step + 20000) {
	step_starfield();
	last_starfield_step = now;
    }
}
 

void coreTask( void * pvParameters ){
// I suspect we can't print from this thread, perhaps printf is not reentrant?
    //printf("GPU task running on core %d\n", xPortGetCoreID());

    // //gpio_install_isr_service(ESP_INTR_FLAG_DEFAULT);
    // //hall_init(GPIO_HALL);
    hall_init(GPIO_HALL_B);
    gpio_set_direction(GPIO_DEBUG, GPIO_MODE_OUTPUT);
    gpio_set_direction(GPIO_NUM_38, GPIO_MODE_OUTPUT);

    init_sprites();
    spiAcquire();

    while(true){
        if (ventilagon_active) {
            ventilagon_loop();
        } else {
            gpu_step();
        }
    }
    vTaskDelete(NULL);
}


static mp_obj_t povdisplay_init(mp_obj_t num_pixels, mp_obj_t palette) {
    spi_init(mp_obj_get_int(num_pixels));
    palette_pal = (uint32_t *) mp_obj_str_get_str(palette);
    //printf("Micropython running on core %d\n", xPortGetCoreID());
    ventilagon_init();
    //printf("pixels0: %p\n", pixels0);
    //printf("pixels1: %p\n", pixels1);
    //printf("extra_buf: %p\n", extra_buf);

    xTaskCreatePinnedToCore(
            coreTask,   /* Function to implement the task */
            "coreTask", /* Name of the task */
            10000,      /* Stack size in words */
            NULL,       /* Task input parameter */
            10,          /* Priority of the task */
            NULL,       /* Task handle. */
            taskCore);  /* Core where the task should run */
    // printf("task created...\n");
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(povdisplay_init_obj, povdisplay_init);

static mp_obj_t povdisplay_getaddress(mp_obj_t sprite_num) {
    int num = mp_obj_get_int(sprite_num);
#ifdef DEBUG_ROTATION
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
// ------------------------------

static const mp_map_elem_t ventilagon_globals_table[] = {
    { MP_OBJ_NEW_QSTR(MP_QSTR___name__), MP_OBJ_NEW_QSTR(MP_QSTR_ventilagon) },
    { MP_OBJ_NEW_QSTR(MP_QSTR_enter), (mp_obj_t)&ventilagon_ventilagon_enter_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_exit), (mp_obj_t)&ventilagon_ventilagon_exit_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_received), (mp_obj_t)&ventilagon_ventilagon_received_obj },
    { MP_OBJ_NEW_QSTR(MP_QSTR_sending), (mp_obj_t)&ventilagon_ventilagon_sending_obj },
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
