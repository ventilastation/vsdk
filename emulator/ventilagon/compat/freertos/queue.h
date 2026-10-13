typedef struct HostQueue *QueueHandle_t;
QueueHandle_t xQueueCreate(int count, int size);
int xQueueSend(QueueHandle_t queue, const void *value, int timeout);
int xQueueReceive(QueueHandle_t queue, void *value, int timeout);
