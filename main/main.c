#include "acquisition.h"
#include "board.h"
#include "device_log.h"
#include "esp_err.h"
#include "usb_interface.h"

void app_main(void)
{
    ESP_ERROR_CHECK(device_log_init());
    ESP_ERROR_CHECK(board_init());
    ESP_ERROR_CHECK(acquisition_init());
    ESP_ERROR_CHECK(usb_interface_init());
    for (;;) {
        usb_interface_poll();
    }
}
