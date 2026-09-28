#pragma once

#include <stdint.h>

#define TF_ID_BYTES 2
#define TF_LEN_BYTES 2
#define TF_TYPE_BYTES 1
#define TF_CKSUM_TYPE TF_CKSUM_CRC32
#define TF_USE_SOF_BYTE 1
#define TF_SOF_BYTE 0x01

typedef uint16_t TF_TICKS;
typedef uint8_t TF_COUNT;

#define TF_MAX_PAYLOAD_RX 64
#define TF_SENDBUF_LEN 512
#define TF_MAX_ID_LST 2
#define TF_MAX_TYPE_LST 3
#define TF_MAX_GEN_LST 1
#define TF_PARSER_TIMEOUT_TICKS 50
#define TF_USE_MUTEX 0
#define TF_Error(...) ((void)0)
