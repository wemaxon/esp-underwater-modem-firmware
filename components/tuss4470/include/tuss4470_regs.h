#pragma once

/* TUSS4470 register addresses and field masks (datasheet SLDS251A, section 7.6). */

#include "esp_bit_defs.h"

#define TUSS4470_REGISTER_BPF_CONFIG_1              0x10U
#define TUSS4470_REGISTER_BPF_CONFIG_2              0x11U
#define TUSS4470_REGISTER_DEV_CTRL_1                0x12U
#define TUSS4470_REGISTER_DEV_CTRL_2                0x13U
#define TUSS4470_REGISTER_DEV_CTRL_3                0x14U
#define TUSS4470_REGISTER_VDRV_CTRL                 0x16U
#define TUSS4470_REGISTER_ECHO_INT_CONFIG           0x17U
#define TUSS4470_REGISTER_ZC_CONFIG                 0x18U
#define TUSS4470_REGISTER_BURST_PULSE               0x1AU
#define TUSS4470_REGISTER_TOF_CONFIG                0x1BU
#define TUSS4470_REGISTER_DEV_STAT                  0x1CU
#define TUSS4470_REGISTER_DEVICE_ID                 0x1DU
#define TUSS4470_REGISTER_REV_ID                    0x1EU

#define TUSS4470_BPF1_TRIM_FORCE             BIT(7)
#define TUSS4470_BPF1_BYPASS                 BIT(6)
#define TUSS4470_BPF1_FREQ_MASK              0x3FU

#define TUSS4470_BPF2_Q_SHIFT                4U
#define TUSS4470_BPF2_Q_MASK                 0x30U
#define TUSS4470_BPF2_TRIM_MASK              0x0FU

#define TUSS4470_DEV1_LOGAMP_FORCE           BIT(7)
#define TUSS4470_DEV1_SLOPE_SHIFT            4U
#define TUSS4470_DEV1_SLOPE_MASK             0x70U
#define TUSS4470_DEV1_INTERCEPT_MASK         0x0FU

#define TUSS4470_DEV2_DISABLE_FIRST          BIT(7)
#define TUSS4470_DEV2_DISABLE_LAST           BIT(6)
#define TUSS4470_DEV2_VOUT_SCALE             BIT(2)
#define TUSS4470_DEV2_LNA_MASK               0x03U

#define TUSS4470_DEV3_FAULT_TIME_SHIFT       2U
#define TUSS4470_DEV3_FAULT_TIME_MASK        0x1CU
#define TUSS4470_DEV3_IO_MODE_MASK           0x03U
#define TUSS4470_DEV3_IO_MODE_2              0x02U

#define TUSS4470_VDRV_DISABLE_LISTEN         BIT(6)
#define TUSS4470_VDRV_HIGH_Z                 BIT(5)
#define TUSS4470_VDRV_CURRENT                BIT(4)
#define TUSS4470_VDRV_VOLTAGE_MASK           0x0FU

#define TUSS4470_ECHO_ENABLE                 BIT(4)
#define TUSS4470_ECHO_THRESHOLD_MASK         0x0FU

#define TUSS4470_ZC_ENABLE                   BIT(7)
#define TUSS4470_ZC_GATE_WITH_ECHO           BIT(6)
#define TUSS4470_ZC_DIFFERENTIAL             BIT(5)
#define TUSS4470_ZC_STAGE_SHIFT              3U
#define TUSS4470_ZC_STAGE_MASK               0x18U
#define TUSS4470_ZC_HYSTERESIS_MASK          0x07U

#define TUSS4470_BURST_HALF_BRIDGE           BIT(7)
#define TUSS4470_BURST_PRE_DRIVER            BIT(6)
#define TUSS4470_BURST_PULSE_MASK            0x3FU

#define TUSS4470_TOF_SLEEP                   BIT(7)
#define TUSS4470_TOF_STANDBY                 BIT(6)
#define TUSS4470_TOF_VDRV_TRIGGER            BIT(1)
#define TUSS4470_TOF_CMD_TRIGGER             BIT(0)

#define TUSS4470_DEVSTAT_VDRV_READY          BIT(3)
#define TUSS4470_DEVSTAT_PULSE_NUM_FLT       BIT(2)
#define TUSS4470_DEVSTAT_DRV_PULSE_FLT       BIT(1)
#define TUSS4470_DEVSTAT_EE_CRC_FLT          BIT(0)
