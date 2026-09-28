#include "tuss4470.h"

#include "driver/rmt_tx.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "tuss4470_frame.h"

#define BURST_CLOCK_HZ          20000000U
#define BURST_MEM_SYMBOLS       48U     /* one RMT memory block */
#define BURST_TIMEOUT_MARGIN_MS 10U

static const char *TAG = "TUSS4470";

static struct {
    tuss4470_config_t config;
    spi_device_handle_t spi;
    rmt_channel_handle_t burst_channel;
    rmt_encoder_handle_t burst_encoder;
    rmt_symbol_word_t burst_period;     /* must outlive the RMT transfer */
} tuss;

static esp_err_t transfer(uint16_t frame, tuss4470_response_t *response)
{
    spi_transaction_t transaction = {
        .flags = SPI_TRANS_USE_TXDATA | SPI_TRANS_USE_RXDATA,
        .length = 16,
        .rxlength = 16,
        .tx_data = {(uint8_t)(frame >> 8), (uint8_t)frame},
    };
    ESP_RETURN_ON_ERROR(spi_device_transmit(tuss.spi, &transaction), TAG, "SPI transfer failed");
    uint16_t raw = (uint16_t)((transaction.rx_data[0] << 8) | transaction.rx_data[1]);
    ESP_RETURN_ON_FALSE(tuss4470_frame_parse_response(raw, response), ESP_ERR_INVALID_CRC, TAG, "Response parity error: 0x%04X", raw);
    if (response->previous_frame_error) {
        ESP_LOGW(TAG, "Device reported a parity error in the previous frame");
    }
    return ESP_OK;
}

esp_err_t tuss4470_read_register(uint8_t address, uint8_t *value)
{
    tuss4470_response_t response;
    ESP_RETURN_ON_ERROR(transfer(tuss4470_frame_read(address), &response), TAG, "Failed to read register 0x%02X", address);
    *value = response.data;
    return ESP_OK;
}

esp_err_t tuss4470_write_register(uint8_t address, uint8_t value)
{
    tuss4470_response_t response;
    ESP_RETURN_ON_ERROR(transfer(tuss4470_frame_write(address, value), &response), TAG, "Failed to write register 0x%02X", address);
    if (tuss.config.verify_writes) {
        uint8_t readback;
        ESP_RETURN_ON_ERROR(tuss4470_read_register(address, &readback), TAG, "Failed to verify register 0x%02X", address);
        ESP_RETURN_ON_FALSE(readback == value, ESP_ERR_INVALID_RESPONSE, TAG, "Register 0x%02X readback 0x%02X, expected 0x%02X", address, readback, value);
    }
    ESP_LOGD(TAG, "Register 0x%02X = 0x%02X", address, value);
    return ESP_OK;
}

esp_err_t tuss4470_update_register(uint8_t address, uint8_t mask, uint8_t value)
{
    uint8_t current;
    ESP_RETURN_ON_ERROR(tuss4470_read_register(address, &current), TAG, "Failed to update register 0x%02X", address);
    return tuss4470_write_register(address, (uint8_t)((current & ~mask) | (value & mask)));
}

esp_err_t tuss4470_set_vdrv(bool enabled)
{
    return tuss4470_update_register(TUSS4470_REGISTER_VDRV_CTRL, TUSS4470_VDRV_HIGH_Z, enabled ? 0 : TUSS4470_VDRV_HIGH_Z);
}

static void log_status(const tuss4470_status_t *status)
{
    static const char *const state_names[] = {"LISTEN", "BURST", "STANDBY", "SLEEP"};
    ESP_LOGI(TAG, "Status=0x%02X state=%s VDRV_ready=%u pulse_count_fault=%u driver_pulse_fault=%u EEPROM_fault=%u",
             status->raw, state_names[status->state], status->vdrv_ready, status->pulse_count_fault,
             status->driver_pulse_fault, status->eeprom_crc_fault);
}

esp_err_t tuss4470_wait_vdrv_ready(uint32_t timeout_ms)
{
    const int64_t deadline_us = esp_timer_get_time() + (int64_t)timeout_ms * 1000;
    tuss4470_status_t status;
    do {
        tuss4470_response_t response;
        ESP_RETURN_ON_ERROR(transfer(tuss4470_frame_read(TUSS4470_REGISTER_DEV_STAT), &response), TAG, "Failed to read status");
        status = tuss4470_status_from_bits(response.status_bits);
        if (tuss4470_status_has_fault(&status)) {
            log_status(&status);
            return ESP_FAIL;
        }
        if (status.vdrv_ready) {
            return ESP_OK;
        }
        vTaskDelay(1);
    } while (esp_timer_get_time() < deadline_us);

    ESP_LOGW(TAG, "VDRV not ready after %lu ms", (unsigned long)timeout_ms);
    log_status(&status);
    return ESP_ERR_TIMEOUT;
}

/*
 * IO mode 1: pulling IO1 low enables the burst, the RMT clocks IO2 for the
 * requested number of cycles and IO1 going high ends it. BURST_PULSE stays at
 * its reset value 0 (continuous), so IO2 alone sets the burst length.
 */
static esp_err_t send_cycles(uint32_t frequency_hz, uint16_t cycles)
{
    uint32_t half_period = (BURST_CLOCK_HZ + frequency_hz) / (2U * frequency_hz);
    tuss.burst_period = (rmt_symbol_word_t){
        .level0 = 0, .duration0 = half_period,
        .level1 = 1, .duration1 = half_period,
    };
    rmt_transmit_config_t transfer = {.loop_count = cycles, .flags.eot_level = 1};
    uint32_t duration_ms = ((uint32_t)cycles * 1000U + frequency_hz - 1U) / frequency_hz;

    esp_err_t error = rmt_transmit(tuss.burst_channel, tuss.burst_encoder, &tuss.burst_period, sizeof(tuss.burst_period), &transfer);
    if (error == ESP_OK) {
        error = rmt_tx_wait_all_done(tuss.burst_channel, (int)(duration_ms + BURST_TIMEOUT_MARGIN_MS));
    }
    if (error != ESP_OK) {
        /* Abort a transfer that may still be running. */
        ESP_RETURN_ON_ERROR(rmt_disable(tuss.burst_channel), TAG, "Failed to stop burst");
        ESP_RETURN_ON_ERROR(rmt_enable(tuss.burst_channel), TAG, "Failed to reset burst channel");
    }
    return error;
}

esp_err_t tuss4470_burst(uint32_t frequency_hz, uint16_t cycles)
{
    ESP_RETURN_ON_FALSE(frequency_hz >= TUSS4470_BURST_MIN_HZ && frequency_hz <= TUSS4470_BURST_MAX_HZ, ESP_ERR_INVALID_ARG, TAG, "Frequency out of range");
    ESP_RETURN_ON_FALSE(cycles && cycles <= TUSS4470_BURST_MAX_CYCLES, ESP_ERR_INVALID_ARG, TAG, "Cycle count out of range");
    ESP_RETURN_ON_ERROR(gpio_set_level(tuss.config.io1_gpio, 0), TAG, "Failed to enable burst");
    esp_err_t error = send_cycles(frequency_hz, cycles);
    esp_err_t released = gpio_set_level(tuss.config.io1_gpio, 1);
    return error != ESP_OK ? error : released;
}

static esp_err_t init_burst(void)
{
    gpio_config_t io1 = {
        .pin_bit_mask = 1ULL << tuss.config.io1_gpio,
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_RETURN_ON_ERROR(gpio_set_level(tuss.config.io1_gpio, 1), TAG, "Failed to idle IO1");
    ESP_RETURN_ON_ERROR(gpio_config(&io1), TAG, "Failed to configure IO1");

    rmt_tx_channel_config_t channel = {
        .gpio_num = tuss.config.io2_gpio,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = BURST_CLOCK_HZ,
        .mem_block_symbols = BURST_MEM_SYMBOLS,
        .trans_queue_depth = 1,
        .flags.init_level = 1,      /* TI recommends IO2 high before the burst */
    };
    rmt_copy_encoder_config_t encoder = {};
    ESP_RETURN_ON_ERROR(rmt_new_tx_channel(&channel, &tuss.burst_channel), TAG, "Failed to create RMT TX channel");
    ESP_RETURN_ON_ERROR(rmt_new_copy_encoder(&encoder, &tuss.burst_encoder), TAG, "Failed to create RMT encoder");
    return rmt_enable(tuss.burst_channel);
}

esp_err_t tuss4470_init(const tuss4470_config_t *config)
{
    tuss.config = *config;
    spi_device_interface_config_t spi = {
        .clock_speed_hz = config->spi_clock_hz,
        .mode = 1,
        .spics_io_num = config->spi_cs_gpio,
        .cs_ena_pretrans = 2,
        .cs_ena_posttrans = 2,
        .queue_size = 1,
    };
    ESP_RETURN_ON_ERROR(spi_bus_add_device(config->spi_host, &spi, &tuss.spi), TAG, "Failed to add SPI device");

    uint8_t device_id;
    uint8_t revision;
    ESP_RETURN_ON_ERROR(tuss4470_read_register(TUSS4470_REGISTER_DEVICE_ID, &device_id), TAG, "Failed to read DEVICE_ID");
    ESP_RETURN_ON_ERROR(tuss4470_read_register(TUSS4470_REGISTER_REV_ID, &revision), TAG, "Failed to read REV_ID");
    ESP_LOGI(TAG, "DEVICE_ID=0x%02X REV_ID=0x%02X", device_id, revision);

    ESP_RETURN_ON_ERROR(tuss4470_update_register(TUSS4470_REGISTER_DEV_CTRL_3, TUSS4470_DEV3_IO_MODE_MASK, 1), TAG, "Failed to select IO mode 1");
    ESP_RETURN_ON_ERROR(init_burst(), TAG, "Failed to initialize burst output");
    ESP_LOGI(TAG, "Initialized: IO1 GPIO %d, IO2 GPIO %d", config->io1_gpio, config->io2_gpio);
    return ESP_OK;
}
