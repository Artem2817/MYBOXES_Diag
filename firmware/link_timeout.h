// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <stdint.h>
namespace mbd {
// A snapshot can precede a heartbeat updated by another thread. Treat it as
// fresh, and preserve wraparound for intervals shorter than 2^31 ms.
inline bool link_expired(uint32_t now,uint32_t heartbeat,uint32_t timeout) {
    return int32_t(now-heartbeat)>int32_t(timeout);
}
}
