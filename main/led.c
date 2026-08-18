#include "led.h"


esp_err_t led_init(gpio_num_t gpio_num){
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << gpio_num),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    return gpio_config(&io_conf);
}

esp_err_t led_set_state(gpio_num_t gpio_num, bool state){
    return gpio_set_level(gpio_num, state ? 1 : 0);
}