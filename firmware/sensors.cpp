// SPDX-License-Identifier: GPL-3.0-or-later
// Register maps and compensation: ArduPilot Invensensev3, MS5611, SPL06;
// TDK DS-000451 / DS-000577 and TDK inv_imu_driver.c (see docs/SOURCES.md).
#include "sensors.h"
#include <math.h>
extern const AP_HAL::HAL &hal;
static int16_t be16(const uint8_t *b) {return int16_t(uint16_t(b[0])<<8|b[1]);}
static int32_t signed_n(uint32_t x,uint8_t n) {return (x&(1U<<(n-1)))?int32_t(x)-int32_t(1U<<n):int32_t(x);}
bool DiagIMU::read(uint8_t r,uint8_t *b,uint8_t n) {
    if(!dev || !dev->get_semaphore()->take(2)){sample.errors++;return false;}
    bool ok=dev->read_registers(r,b,n);dev->get_semaphore()->give();if(!ok){sample.errors++;}return ok;
}
bool DiagIMU::write(uint8_t r,uint8_t v) {
    if(!dev || !dev->get_semaphore()->take(2)){sample.errors++;return false;}
    bool ok=dev->write_register(r,v);dev->get_semaphore()->give();if(!ok){sample.errors++;}return ok;
}
bool DiagIMU::indirect_ready() {
    for(unsigned i=0;i<10;i++){uint8_t ready=0;if(!read(0x7f,&ready,1)){return false;}if(ready&1){return true;}hal.scheduler->delay_microseconds(10);}
    sample.errors++;return false;
}
bool DiagIMU::indirect_read(uint16_t address,uint8_t &value) {
    if(!dev->get_semaphore()->take(2)){sample.errors++;return false;}
    const uint8_t tx[]={0x7c,uint8_t(address>>8),uint8_t(address)};
    bool ok=dev->transfer(tx,sizeof(tx),nullptr,0);dev->get_semaphore()->give();
    if(!ok){sample.errors++;return false;}return indirect_ready()&&read(0x7e,&value,1);
}
bool DiagIMU::indirect_write(uint16_t address,uint8_t value) {
    if(!dev->get_semaphore()->take(2)){sample.errors++;return false;}
    const uint8_t tx[]={0x7c,uint8_t(address>>8),uint8_t(address),value};
    bool ok=dev->transfer(tx,sizeof(tx),nullptr,0);dev->get_semaphore()->give();
    hal.scheduler->delay_microseconds(10);if(!ok){sample.errors++;return false;}return indirect_ready();
}
bool DiagIMU::begin(const char *name,uint8_t model) {
    type=model;sample=SensorSample{};sample.start_ms=AP_HAL::millis();
    if(!dev){dev=hal.spi->get_device_ptr(name);}if(!dev){return false;}dev->set_read_flag(0x80);dev->set_speed(AP_HAL::Device::SPEED_LOW);
    if(type==0){who=0x75;sample.expected_id=0x47;power=0x4e;config=0x4f;data=0x1d;status=0x2d;mask=8;odr=7;}
    else if(type==1){who=0x72;sample.expected_id=0xe9;power=0x10;config=0x1b;data=0;status=0x19;mask=4;odr=8;}
    else {who=0x75;sample.expected_id=0x67;power=0x1f;config=0x20;data=9;status=0x39;mask=1;odr=8;}
    if(!read(who,&sample.actual_id,1)||sample.actual_id!=sample.expected_id){return false;}sample.present=true;
    bool ok=write(type==0?0x11:type==1?0x7f:0x02,type==0?1:type==1?2:0x10);
    hal.scheduler->delay(2);
    if(!ok){return false;}
    if(type==0){ok=write(0x76,0)&&write(0x4c,0x30);little=false;}
    else if(type==2){ok=write(0x35,0x30);little=false;}
    else {
        // Select big-endian data explicitly via indirect SREG_CTRL 0xA267.
        uint8_t v=0;ok=indirect_read(0xa267,v)&&indirect_write(0xa267,v|0x40);
        // Pin 7 is grounded in current CAD: disable the I3C STC pull-up.
        ok=ok&&indirect_read(0xa268,v)&&indirect_write(0xa268,v&~4U);
        little=false;
        ok=ok&&write(0x54,3)&&write(0x16,4); // enable DRDY status, AUX1 off
    }
    ok=ok&&write(power,0x0f);hal.scheduler->delay_microseconds(300);
    ok=ok&&write(config,odr)&&write(config+1,odr);
    // ICM45686 config order is ACCEL/GYRO; others GYRO/ACCEL, same FS=0.
    sample.configured=ok&&config_ok();return sample.configured;
}
bool DiagIMU::config_ok() {uint8_t a=0,b=0,p=0;return read(config,&a,1)&&read(config+1,&b,1)&&read(power,&p,1)&&a==odr&&b==odr&&(p&15)==15;}
void DiagIMU::poll() {
    uint32_t now=AP_HAL::millis();if(!sample.configured||now-sample.start_ms<100){return;}
    uint8_t s=0,b[14];if(!read(status,&s,1)||!(s&mask)){return;}
    if(!read(data,b,14)){return;}
    for(uint8_t i=0;i<7;i++){sample.raw[i]=little?int16_t(uint16_t(b[2*i+1])<<8|b[2*i]):be16(b+2*i);}
    const uint8_t ai=type==1?0:1,gi=type==1?3:4,ti=type==1?6:0;
    for(uint8_t i=0;i<3;i++){if(sample.raw[ai+i]==INT16_MIN||sample.raw[gi+i]==INT16_MIN){sample.errors++;return;}}
    const float as=(type==1?32.0f:16.0f)*9.80665f/32768.0f,gs=(type==1?4000.0f:2000.0f)/32768.0f;
    for(uint8_t i=0;i<3;i++){sample.accel[i]=sample.raw[ai+i]*as;sample.gyro[i]=sample.raw[gi+i]*gs;if(abs(sample.raw[ai+i])>=32760||abs(sample.raw[gi+i])>=32760){sample.saturated++;}}
    sample.temperature=25.0f+sample.raw[ti]/(type==0?132.48f:128.0f);
    sample.last_ms=now;sample.count++;sample.hz=sample.count*1000.0f/(now-sample.start_ms);
}
bool DiagBaro::transfer(uint8_t cmd,uint8_t *p,uint8_t n) {
    if(!dev||!dev->get_semaphore()->take(2)){sample.errors++;return false;}
    bool ok=dev->transfer(&cmd,1,p,n);dev->get_semaphore()->give();if(!ok){sample.errors++;}return ok;
}
bool DiagBaro::read(uint8_t r,uint8_t *p,uint8_t n) {return transfer(r,p,n);}
bool DiagBaro::write(uint8_t r,uint8_t v) {
    if(!dev||!dev->get_semaphore()->take(2)){sample.errors++;return false;}bool ok=dev->write_register(r,v);dev->get_semaphore()->give();if(!ok){sample.errors++;}return ok;
}
bool DiagBaro::begin(uint8_t address,bool ms5611) {
    type=ms5611?0:1;sample=SensorSample{};sample.start_ms=AP_HAL::millis();phase=0;
    if(!dev){dev=hal.i2c_mgr->get_device_ptr(0,address,400000,false,4);}if(!dev){return false;}dev->set_retries(0);
    if(type==0) {
        if(!transfer(0x1e,nullptr,0)){return false;}hal.scheduler->delay(3);bool nonzero=false,not_ff=false;
        for(uint8_t i=0;i<8;i++){uint8_t b[2];if(!transfer(0xa0+2*i,b,2)){return false;}prom[i]=uint16_t(b[0])<<8|b[1];nonzero|=prom[i]!=0;not_ff|=prom[i]!=65535;}
        uint16_t saved=prom[7];prom[7]&=0xff00;uint16_t crc=0;
        for(uint8_t i=0;i<16;i++){crc^=(i&1)?prom[i>>1]&255:prom[i>>1]>>8;for(uint8_t j=0;j<8;j++){crc=(crc&0x8000)?(crc<<1)^0x3000:crc<<1;}}
        prom[7]=saved;sample.expected_id=saved&15;sample.actual_id=(crc>>12)&15;
        if(!nonzero||!not_ff||sample.expected_id!=sample.actual_id){return false;}sample.present=true;
        sample.configured=transfer(0x48,nullptr,0);next_ms=AP_HAL::millis()+10;
    } else {
        sample.expected_id=0x11;if(!read(0x0d,&sample.actual_id,1)||sample.actual_id!=0x11){return false;}sample.present=true;
        uint8_t status=0,b[21];if(!read(8,&status,1)||(status&0xc0)!=0xc0||!read(0x10,b,21)){return false;}
        c[0]=signed_n(uint32_t(b[0])<<4|b[1]>>4,12);c[1]=signed_n(uint32_t(b[1]&15)<<8|b[2],12);
        c[2]=signed_n(uint32_t(b[3])<<12|uint32_t(b[4])<<4|b[5]>>4,20);c[3]=signed_n(uint32_t(b[5]&15)<<16|uint32_t(b[6])<<8|b[7],20);
        for(uint8_t i=0;i<5;i++){c[4+i]=be16(b+8+2*i);}c[9]=signed_n(uint32_t(b[18])<<4|b[19]>>4,12);c[10]=signed_n(uint32_t(b[19]&15)<<8|b[20],12);
        sample.configured=write(6,0x53)&&write(7,0x53)&&write(9,0)&&write(8,7);next_ms=AP_HAL::millis()+50;
    }
    return sample.configured;
}
void DiagBaro::poll() {
    uint32_t now=AP_HAL::millis();if(!sample.configured||int32_t(now-next_ms)<0){return;}
    next_ms=now+10;uint8_t b[6];
    if(type==0) {
        if(!transfer(0,b,3)){return;}uint32_t raw=uint32_t(b[0])<<16|uint32_t(b[1])<<8|b[2];
        if(!phase){raw_d1=raw;phase=1;if(!transfer(0x58,nullptr,0)){sample.configured=false;}return;}
        phase=0;if(!transfer(0x48,nullptr,0)){sample.configured=false;return;}
        float dt=float(raw)-prom[5]*256.0f,t=2000+dt*prom[6]/8388608.0f;
        float off=prom[2]*65536.0f+prom[4]*dt/128.0f,sens=prom[1]*32768.0f+prom[3]*dt/256.0f;
        if(t<2000){float a=(t-2000)*(t-2000),o2=2.5f*a,s2=1.25f*a;if(t<-1500){o2+=7*(t+1500)*(t+1500);s2+=5.5f*(t+1500)*(t+1500);}t-=dt*dt/2147483648.0f;off-=o2;sens-=s2;}
        sample.temperature=t/100;sample.pressure=(raw_d1*sens/2097152.0f-off)/32768.0f;
    } else {
        uint8_t status=0;if(!read(8,&status,1)||(status&0x30)!=0x30||!read(0,b,6)){return;}
        float p=signed_n(uint32_t(b[0])<<16|uint32_t(b[1])<<8|b[2],24)/7864320.0f;
        float t=signed_n(uint32_t(b[3])<<16|uint32_t(b[4])<<8|b[5],24)/7864320.0f;
        sample.temperature=c[0]*0.5f+c[1]*t;
        sample.pressure=c[2]+p*(c[3]+p*(c[6]+p*(c[8]+p*c[10])))+t*(c[4]+p*(c[5]+p*(c[7]+p*c[9])));
    }
    if(!isfinite(sample.pressure)||!isfinite(sample.temperature)){sample.errors++;return;}
    if(sample.count==0){sample.baseline=sample.pressure;}sample.count++;sample.last_ms=now;sample.hz=sample.count*1000.0f/(now-sample.start_ms+1);
}
