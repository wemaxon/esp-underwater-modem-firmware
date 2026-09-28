#include "device_log.h"

#include <stdarg.h>
#include <stdio.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

#define DEVICE_LOG_QUEUE_LENGTH 16U

static QueueHandle_t entries;

static int log_write(const char *format, va_list args)
{
    device_log_entry_t entry;
    int length = vsnprintf(entry.text, sizeof(entry.text), format, args);
    if (length > 0) {
        entry.length = (uint16_t)((size_t)length < sizeof(entry.text) ? (size_t)length : sizeof(entry.text) - 1);
        if ((size_t)length >= sizeof(entry.text)) {
            entry.text[entry.length - 1] = '\n';
        }
        xQueueSend(entries, &entry, 0);
    }
    return length;
}

esp_err_t device_log_init(void)
{
    entries = xQueueCreate(DEVICE_LOG_QUEUE_LENGTH, sizeof(device_log_entry_t));
    if (!entries) {
        return ESP_ERR_NO_MEM;
    }
    esp_log_set_vprintf(log_write);
    return ESP_OK;
}

bool device_log_read(device_log_entry_t *entry)
{
    return xQueueReceive(entries, entry, 0) == pdTRUE;
}
