#include "tuss4470.h"

#include "driver/rmt_encoder.h"
#include "driver/rmt_tx.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "tuss4470_frame.h"

#define TRANSMIT_MEM_SYMBOLS        48U     /* one RMT memory block */
#define TRANSMIT_TIMEOUT_MARGIN_US  50000
#define SPI_ATTEMPTS                3       /* status bits can change while a response is shifted out */

static const char *TAG = "TUSS4470";

static struct {
    tuss4470_config_t config;
    spi_device_handle_t spi;
    rmt_channel_handle_t transmit_channel;
    rmt_encoder_handle_t transmit_encoder;
    tuss4470_waveform_t waveform;       /* read by the RMT encoder while transmitting */
    bool transmitting;
    volatile bool transmit_done;        /* set by the RMT interrupt */
    int64_t deadline_us;
} tuss;

/*
 * Sends one frame. Responses carry live status bits; one that changes while the
 * response is shifted out (VDRV_READY while VDRV is regulated) breaks its
 * parity, so the frame is repeated.
 */
static esp_err_t transfer(uint16_t frame, tuss4470_response_t *response)
{
    uint16_t raw = 0;
    for (int attempt = 0; attempt < SPI_ATTEMPTS; ++attempt) {
        spi_transaction_t transaction = {
            .flags = SPI_TRANS_USE_TXDATA | SPI_TRANS_USE_RXDATA,
            .length = 16,
            .rxlength = 16,
            .tx_data = {(uint8_t)(frame >> 8), (uint8_t)frame},
        };
        ESP_RETURN_ON_ERROR(spi_device_transmit(tuss.spi, &transaction), TAG, "SPI transfer failed");
        raw = (uint16_t)((transaction.rx_data[0] << 8) | transaction.rx_data[1]);
        if (tuss4470_frame_parse_response(raw, response)) {
            if (response->previous_frame_error) {
                ESP_LOGW(TAG, "Device reported a parity error in the previous frame");
            }
            return ESP_OK;
        }
        ESP_LOGD(TAG, "Response parity error: 0x%04X", raw);
    }
    ESP_LOGE(TAG, "Response parity error in %d attempts: 0x%04X", SPI_ATTEMPTS, raw);
    return ESP_ERR_INVALID_CRC;
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

static esp_err_t read_status(tuss4470_status_t *status)
{
    tuss4470_response_t response;
    ESP_RETURN_ON_ERROR(transfer(tuss4470_frame_read(TUSS4470_REGISTER_DEV_STAT), &response), TAG, "Failed to read status");
    *status = tuss4470_status_from_bits(response.status_bits);
    return ESP_OK;
}

/* Pulse faults describe the previous burst and are cleared by the next one, so only an EEPROM fault stops it. */
esp_err_t tuss4470_wait_vdrv_ready(uint32_t timeout_ms)
{
    const int64_t deadline_us = esp_timer_get_time() + (int64_t)timeout_ms * 1000;
    tuss4470_status_t status;
    do {
        ESP_RETURN_ON_ERROR(read_status(&status), TAG, "Failed to read status");
        if (status.eeprom_crc_fault) {
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
 * IO mode 1: pulling IO1 low enables the burst, the RMT clocks IO2 with the
 * waveform and IO1 going high ends it. BURST_PULSE stays at its reset value 0
 * (continuous), so IO2 alone sets the burst length.
 */
static size_t encode_waveform(const void *data, size_t data_size, size_t symbols_written, size_t symbols_free,
                              rmt_symbol_word_t *symbols, bool *done, void *arg)
{
    size_t count = tuss4470_waveform_fill(&tuss.waveform, (uint32_t *)symbols, symbols_free);
    *done = tuss4470_waveform_done(&tuss.waveform);
    return count;
}

/*
 * Ends the burst right after the last cycle: if IO1 stayed low while IO2 rests
 * for more than 64 us, the chip would report a driver pulse fault.
 */
static bool on_transmit_done(rmt_channel_handle_t channel, const rmt_tx_done_event_data_t *event, void *context)
{
    gpio_set_level(tuss.config.io1_gpio, 1);
    tuss.transmit_done = true;
    return false;
}

esp_err_t tuss4470_transmit_start(const tuss4470_tone_t *tones, size_t count)
{
    ESP_RETURN_ON_FALSE(tones && count, ESP_ERR_INVALID_ARG, TAG, "No tones");
    ESP_RETURN_ON_FALSE(!tuss.transmitting, ESP_ERR_INVALID_STATE, TAG, "Already transmitting");
    for (size_t i = 0; i < count; ++i) {
        ESP_RETURN_ON_FALSE(tones[i].frequency_hz >= TUSS4470_TONE_MIN_HZ && tones[i].frequency_hz <= TUSS4470_TONE_MAX_HZ && tones[i].cycles,
                            ESP_ERR_INVALID_ARG, TAG, "Invalid tone %u", (unsigned)i);
    }
    tuss4470_waveform_start(&tuss.waveform, tones, count, TUSS4470_TRANSMIT_CLOCK_HZ);
    uint64_t duration_us = tuss4470_waveform_duration_us(tones, count, TUSS4470_TRANSMIT_CLOCK_HZ);
    tuss.deadline_us = esp_timer_get_time() + (int64_t)duration_us + TRANSMIT_TIMEOUT_MARGIN_US;

    tuss.transmit_done = false;
    ESP_RETURN_ON_ERROR(gpio_set_level(tuss.config.io1_gpio, 0), TAG, "Failed to enable burst");
    rmt_transmit_config_t transfer = {.flags.eot_level = 1};
    esp_err_t error = rmt_transmit(tuss.transmit_channel, tuss.transmit_encoder, tones, count * sizeof(*tones), &transfer);
    if (error != ESP_OK) {
        gpio_set_level(tuss.config.io1_gpio, 1);
        return error;
    }
    tuss.transmitting = true;
    return ESP_OK;
}

esp_err_t tuss4470_transmit_poll(void)
{
    if (!tuss.transmitting) {
        return ESP_ERR_INVALID_STATE;
    }
    if (tuss.transmit_done) {
        tuss.transmitting = false;
        tuss4470_status_t status;
        ESP_RETURN_ON_ERROR(read_status(&status), TAG, "Failed to read status after the burst");
        if (status.driver_pulse_fault) {
            log_status(&status);
            ESP_LOGE(TAG, "The burst was ended early by a driver pulse fault");
            return ESP_FAIL;
        }
        return ESP_OK;
    }
    if (esp_timer_get_time() < tuss.deadline_us) {
        return ESP_ERR_NOT_FINISHED;
    }
    /* Abort a transfer that did not finish in time. */
    rmt_disable(tuss.transmit_channel);
    rmt_enable(tuss.transmit_channel);
    gpio_set_level(tuss.config.io1_gpio, 1);
    tuss.transmitting = false;
    return ESP_ERR_TIMEOUT;
}

static esp_err_t init_transmit(void)
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
        .resolution_hz = TUSS4470_TRANSMIT_CLOCK_HZ,
        .mem_block_symbols = TRANSMIT_MEM_SYMBOLS,
        .trans_queue_depth = 1,
        .flags.init_level = 1,      /* TI recommends IO2 high before the burst */
    };
    rmt_simple_encoder_config_t encoder = {.callback = encode_waveform, .min_chunk_size = 1};
    rmt_tx_event_callbacks_t callbacks = {.on_trans_done = on_transmit_done};
    ESP_RETURN_ON_ERROR(rmt_new_tx_channel(&channel, &tuss.transmit_channel), TAG, "Failed to create RMT TX channel");
    ESP_RETURN_ON_ERROR(rmt_new_simple_encoder(&encoder, &tuss.transmit_encoder), TAG, "Failed to create RMT encoder");
    ESP_RETURN_ON_ERROR(rmt_tx_register_event_callbacks(tuss.transmit_channel, &callbacks, NULL), TAG, "Failed to register RMT callback");
    return rmt_enable(tuss.transmit_channel);
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
    ESP_RETURN_ON_ERROR(init_transmit(), TAG, "Failed to initialize transmit output");
    ESP_LOGI(TAG, "Initialized: IO1 GPIO %d, IO2 GPIO %d", config->io1_gpio, config->io2_gpio);
    return ESP_OK;
}
