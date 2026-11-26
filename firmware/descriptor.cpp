// SPDX-License-Identifier: GPL-3.0-or-later
// ArduPilot unsigned app descriptor; Waf fills image CRCs, size and platform hash.
#include <AP_HAL/AP_HAL.h>
#include <stdint.h>
struct DiagAppDescriptor {
    uint8_t signature[8];
    uint32_t crc1,crc2,size,git_hash;
    uint8_t major,minor;
    uint16_t board_id;
    uint8_t reserved[8];
};
static_assert(sizeof(DiagAppDescriptor)==36,"Bootloader descriptor layout");
extern const DiagAppDescriptor app_descriptor __attribute__((section(".app_descriptor"),used)) = {
    {0x40,0xa2,0xe4,0xf1,0x64,0x68,0x91,0x06},0,0,0,0,0,1,APJ_BOARD_ID,
    {0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff}
};
