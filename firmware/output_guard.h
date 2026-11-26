// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <stdint.h>
#include "thresholds.h"
#include "link_timeout.h"
namespace mbd {
// Keep the channel reserved after revocation. A timer must keep forcing it off
// until the main thread acknowledges, including an enable interrupted by expiry.
template<class Pins> class OutputGuard {
public:
    explicit OutputGuard(Pins backend):pins(backend) {}
    volatile int8_t pwm=-1;volatile uint8_t gpio=0;
    volatile uint32_t deadline=0,heartbeat=0;volatile bool tripped=false;
    Pins pins;
    void arm_pwm(uint8_t channel,uint32_t now,uint32_t last_command,uint32_t duration) {
        deadline=now+(duration<cfg::actuator_max_ms?duration:cfg::actuator_max_ms);
        heartbeat=last_command;tripped=false;pwm=channel;
    }
    void arm_gpio(uint8_t pin,uint32_t now,uint32_t last_command,uint32_t duration) {
        deadline=now+(duration<cfg::actuator_max_ms?duration:cfg::actuator_max_ms);
        heartbeat=last_command;tripped=false;gpio=pin;
    }
    void enforce(uint32_t now) {
        if((pwm>=0||gpio)&&(tripped||int32_t(now-deadline)>=0||link_expired(now,heartbeat,cfg::actuator_lease_ms))) {
            tripped=true;pins.off(pwm,gpio);
        }
    }
    void stop() {
        pins.off(pwm,gpio);pwm=-1;gpio=0;tripped=false;
    }
};
}
