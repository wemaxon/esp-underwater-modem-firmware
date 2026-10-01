#include "acquisition.h"

#include <stdatomic.h>

#include "board.h"
#include "edge_capture.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_continuous.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "soc/soc_caps.h"

#define VOUT_ATTENUATION    ADC_ATTEN_DB_6      /* up to about 1.3 V; the pin sees at most 1.06 V */
#define VOUT_POOL_BYTES     (16U * 1024)        /* about 200 ms of samples */
#define SAMPLE_PERIOD_NS    (1000000000LL / ACQUISITION_VOUT_RATE_HZ)

#define OUT3_MIN_PULSE_NS   1000U
#define OUT3_IDLE_NS        (3U * 1000 * 1000)
#define OUT3_BUFFER_BYTES   (32U * 1024)        /* about 150 ms of a 40 kHz signal */

_Static_assert(1000000000ULL % ACQUISITION_VOUT_RATE_HZ == 0, "Sample period must be a whole number of ns");
_Static_assert((uint64_t)OUT3_IDLE_NS * ACQUISITION_EDGE_CLOCK_HZ / 1000000000U <= 32767, "Idle limit must fit an RMT duration");

static const char *TAG = "ACQUISITION";

static adc_continuous_handle_t adc;
static adc_cali_handle_t calibration;
static edge_capture_handle_t out3;
static int64_t start_us;
static uint32_t samples_read;
static bool failed;
static atomic_bool vout_overflowed;
static volatile uint32_t frames_done;
static volatile int64_t first_frame_us;
static volatile int64_t last_frame_us;

static bool on_frame_done(adc_continuous_handle_t handle, const adc_continuous_evt_data_t *event, void *context)
{
    int64_t now = esp_timer_get_time();
    if (!frames_done) {
        first_frame_us = now;
    }
    last_frame_us = now;
    frames_done = frames_done + 1;
    return false;
}

static bool on_pool_overflow(adc_continuous_handle_t handle, const adc_continuous_evt_data_t *event, void *context)
{
    atomic_store(&vout_overflowed, true);
    return false;
}

static esp_err_t init_vout(void)
{
    adc_unit_t unit;
    adc_channel_t channel;
    ESP_RETURN_ON_ERROR(adc_continuous_io_to_channel(BOARD_PIN_TUSS4470_VOUT, &unit, &channel), TAG, "VOUT pin has no ADC channel");

    adc_continuous_handle_cfg_t handle = {
        .max_store_buf_size = VOUT_POOL_BYTES,
        .conv_frame_size = ACQUISITION_VOUT_BLOCK * SOC_ADC_DIGI_RESULT_BYTES,
    };
    adc_digi_pattern_config_t pattern = {
        .atten = VOUT_ATTENUATION,
        .channel = channel,
        .unit = unit,
        .bit_width = SOC_ADC_DIGI_MAX_BITWIDTH,
    };
    adc_continuous_config_t config = {
        .pattern_num = 1,
        .adc_pattern = &pattern,
        .sample_freq_hz = ACQUISITION_VOUT_RATE_HZ,
        .conv_mode = ADC_CONV_SINGLE_UNIT_1,
    };
    adc_continuous_evt_cbs_t callbacks = {.on_conv_done = on_frame_done, .on_pool_ovf = on_pool_overflow};
    adc_cali_curve_fitting_config_t calibration_config = {
        .unit_id = unit,
        .chan = channel,
        .atten = VOUT_ATTENUATION,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    ESP_RETURN_ON_ERROR(adc_continuous_new_handle(&handle, &adc), TAG, "Failed to create ADC handle");
    ESP_RETURN_ON_ERROR(adc_continuous_config(adc, &config), TAG, "Failed to configure ADC");
    ESP_RETURN_ON_ERROR(adc_continuous_register_event_callbacks(adc, &callbacks, NULL), TAG, "Failed to register ADC callbacks");
    return adc_cali_create_scheme_curve_fitting(&calibration_config, &calibration);
}

esp_err_t acquisition_init(void)
{
    edge_capture_config_t config = {
        .gpio = BOARD_PIN_TUSS4470_OUT3,
        .resolution_hz = ACQUISITION_EDGE_CLOCK_HZ,
        .min_pulse_ns = OUT3_MIN_PULSE_NS,
        .idle_timeout_ns = OUT3_IDLE_NS,
        .buffer_bytes = OUT3_BUFFER_BYTES,
    };
    ESP_RETURN_ON_ERROR(edge_capture_new(&config, &out3), TAG, "Failed to initialize OUT3 capture");
    ESP_RETURN_ON_ERROR(init_vout(), TAG, "Failed to initialize VOUT sampling");
    return ESP_OK;
}

esp_err_t acquisition_start(void)
{
    samples_read = 0;
    failed = false;
    frames_done = 0;
    atomic_store(&vout_overflowed, false);
    start_us = esp_timer_get_time();
    ESP_RETURN_ON_ERROR(adc_continuous_flush_pool(adc), TAG, "Failed to flush ADC pool");
    ESP_RETURN_ON_ERROR(edge_capture_start(out3), TAG, "Failed to start OUT3 capture");
    ESP_RETURN_ON_ERROR(adc_continuous_start(adc), TAG, "Failed to start VOUT sampling");
    ESP_LOGI(TAG, "Started: VOUT %u samples/s, OUT3 %u Hz edge clock", ACQUISITION_VOUT_RATE_HZ, ACQUISITION_EDGE_CLOCK_HZ);
    return ESP_OK;
}

esp_err_t acquisition_stop(void)
{
    ESP_RETURN_ON_ERROR(adc_continuous_stop(adc), TAG, "Failed to stop VOUT sampling");
    ESP_RETURN_ON_ERROR(edge_capture_stop(out3), TAG, "Failed to stop OUT3 capture");
    if (frames_done > 1) {
        int64_t span_us = last_frame_us - first_frame_us;
        uint64_t rate_hz = (uint64_t)(frames_done - 1) * ACQUISITION_VOUT_BLOCK * 1000000U / (uint64_t)span_us;
        ESP_LOGI(TAG, "Stopped: VOUT measured at %llu samples/s", (unsigned long long)rate_hz);
    }
    return ESP_OK;
}

static uint16_t vout_millivolts(int pin_millivolts)
{
    const uint32_t total = BOARD_VOUT_DIVIDER_TOP_OHMS + BOARD_VOUT_DIVIDER_BOTTOM_OHMS;
    return (uint16_t)(((uint32_t)pin_millivolts * total + BOARD_VOUT_DIVIDER_BOTTOM_OHMS / 2) / BOARD_VOUT_DIVIDER_BOTTOM_OHMS);
}

size_t acquisition_read_vout(int64_t *first_sample_ns, uint16_t *millivolts)
{
    static uint8_t raw[ACQUISITION_VOUT_BLOCK * SOC_ADC_DIGI_RESULT_BYTES];
    static adc_continuous_data_t samples[ACQUISITION_VOUT_BLOCK];
    uint32_t length = 0;
    uint32_t count = 0;
    if (adc_continuous_read(adc, raw, sizeof(raw), &length, 0) != ESP_OK) {
        return 0;
    }
    if (adc_continuous_parse_data(adc, raw, length, samples, &count) != ESP_OK) {
        failed = true;
        return 0;
    }
    for (uint32_t i = 0; i < count; ++i) {
        int pin_millivolts;
        if (!samples[i].valid || adc_cali_raw_to_voltage(calibration, (int)samples[i].raw_data, &pin_millivolts) != ESP_OK) {
            failed = true;
            return 0;
        }
        millivolts[i] = vout_millivolts(pin_millivolts);
    }
    /* The first frame completed with its last sample; earlier samples follow from the sample rate. */
    int64_t first_frame_ns = (first_frame_us - start_us) * 1000 - (int64_t)(ACQUISITION_VOUT_BLOCK - 1) * SAMPLE_PERIOD_NS;
    *first_sample_ns = first_frame_ns + (int64_t)samples_read * SAMPLE_PERIOD_NS;
    samples_read += count;
    return count;
}

size_t acquisition_read_out3(edge_t *edges, size_t capacity)
{
    size_t count = edge_capture_read(out3, edges, capacity);
    for (size_t i = 0; i < count; ++i) {
        edges[i].time_ns -= start_us * 1000;
    }
    return count;
}

acquisition_status_t acquisition_status(void)
{
    if (failed) {
        return ACQUISITION_ERROR;
    }
    if (atomic_load(&vout_overflowed) || edge_capture_overflowed(out3)) {
        return ACQUISITION_OVERFLOW;
    }
    return ACQUISITION_OK;
}
