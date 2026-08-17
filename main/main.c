#include <stdio.h>

#include "esp_log.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "board.h"


static const char *TAG = "MAIN";

void app_main(void)
{
    while(1) {
        ESP_LOGI(TAG, "Hello, World!");
        vTaskDelay(pdMS_TO_TICKS(1000));
    }

}
