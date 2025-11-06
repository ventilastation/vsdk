// Mini SPI driver
// based on https://github.com/espressif/arduino-esp32/blob/master/cores/esp32/esp32-hal-spi.c

#define GPU_TASK_CORE 0

void spiStartBuses(uint32_t freq);
void spiAcquire();
void spiWriteNL(const void * data_in, size_t len);
