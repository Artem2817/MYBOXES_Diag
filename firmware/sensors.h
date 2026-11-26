// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <AP_HAL/AP_HAL.h>
#include <AP_HAL/SPIDevice.h>
#include <AP_HAL/I2CDevice.h>
struct SensorSample {
    bool present=false,configured=false;uint8_t expected_id=0,actual_id=0;
    uint32_t last_ms=0,count=0,errors=0,saturated=0,start_ms=0;
    float accel[3]{},gyro[3]{},temperature=0,pressure=0,baseline=0,hz=0;
    int16_t raw[7]{};
};
class DiagIMU {
public:
    SensorSample sample;uint8_t type=0;AP_HAL::SPIDevice *dev=nullptr;
    bool begin(const char *name,uint8_t model);void poll();bool config_ok();
private:
    uint8_t who=0,power=0,config=0,data=0,status=0,mask=0,odr=0;bool little=false;
    bool read(uint8_t r,uint8_t *b,uint8_t n);bool write(uint8_t r,uint8_t v);
    bool indirect_ready();bool indirect_read(uint16_t address,uint8_t &value);bool indirect_write(uint16_t address,uint8_t value);
};
class DiagBaro {
public:
    SensorSample sample;uint8_t type=0;AP_HAL::I2CDevice *dev=nullptr;
    bool begin(uint8_t address,bool ms5611);void poll();
private:
    uint16_t prom[8]{};int32_t c[11]{};uint8_t phase=0;uint32_t next_ms=0,raw_d1=0;
    bool transfer(uint8_t cmd,uint8_t *p,uint8_t n);bool read(uint8_t reg,uint8_t *b,uint8_t n);bool write(uint8_t r,uint8_t v);
};
