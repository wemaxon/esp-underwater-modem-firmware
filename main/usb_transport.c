#include "usb_transport.h"

#include "driver/usb_serial_jtag.h"
#include "freertos/FreeRTOS.h"

#if CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG || CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
#error "USB CDC must be reserved for modem data; select the UART console"
#endif

esp_err_t usb_transport_init(void)
{
    usb_serial_jtag_driver_config_t config = {.tx_buffer_size = 4096, .rx_buffer_size = 256};
    return usb_serial_jtag_driver_install(&config);
}

int usb_transport_read(uint8_t *data, size_t capacity)
{
    return usb_serial_jtag_read_bytes(data, capacity, 1);
}

esp_err_t usb_transport_write(const uint8_t *data, size_t length)
{
    while (length) {
        int written = usb_serial_jtag_write_bytes(data, length, pdMS_TO_TICKS(100));
        if (written <= 0) {
            return ESP_ERR_TIMEOUT;
        }
        data += written;
        length -= written;
    }
    return ESP_OK;
}

bool usb_transport_connected(void)
{
    return usb_serial_jtag_is_connected();
}

bool usb_transport_try_write(const uint8_t *data, size_t length)
{
    return usb_serial_jtag_write_bytes(data, length, 0) == (int)length;
}
