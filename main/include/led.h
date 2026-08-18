#pragma once

#include "driver/gpio.h"

esp_err_t led_init(gpio_num_t gpio_num);
esp_err_t led_set_state(gpio_num_t gpio_num, bool state);