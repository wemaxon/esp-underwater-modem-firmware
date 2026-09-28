#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

void tf_messages_init(void);
void tf_messages_accept(const uint8_t *data, size_t length);
void tf_messages_tick(void);
void tf_messages_poll(void);
bool tf_messages_write_failed(void);
void tf_messages_reset(void);
