#include "usb_transport.h"

#include "driver/usb_serial_jtag.h"

#if CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG || CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
#error "USB CDC must be reserved for the TinyFrame interface; select the UART console"
#endif

#define TX_BUFFER_SIZE   4096U
#define RX_BUFFER_SIZE   256U
#define WRITE_TIMEOUT_MS 100U

esp_err_t usb_transport_init(void)
{
    usb_serial_jtag_driver_config_t config = {.tx_buffer_size = TX_BUFFER_SIZE, .rx_buffer_size = RX_BUFFER_SIZE};
    return usb_serial_jtag_driver_install(&config);
}

bool usb_transport_connected(void)
{
    return usb_serial_jtag_is_connected();
}

int usb_transport_read(uint8_t *data, size_t capacity, TickType_t timeout)
{
    return usb_serial_jtag_read_bytes(data, capacity, timeout);
}

esp_err_t usb_transport_write(const uint8_t *data, size_t length)
{
    while (length) {
        int written = usb_serial_jtag_write_bytes(data, length, pdMS_TO_TICKS(WRITE_TIMEOUT_MS));
        if (written <= 0) {
            return ESP_ERR_TIMEOUT;
        }
        data += written;
        length -= written;
    }
    return ESP_OK;
}

bool usb_transport_try_write(const uint8_t *data, size_t length)
{
    return usb_serial_jtag_write_bytes(data, length, 0) == (int)length;
}
