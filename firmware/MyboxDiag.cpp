// SPDX-License-Identifier: GPL-3.0-or-later
// AI-assisted bench diagnostic application. Never use for flight.
#include <AP_HAL/AP_HAL.h>
#include <AP_Filesystem/AP_Filesystem.h>
#include <AP_Math/AP_Math.h>
#include <hal.h>
#include <AP_HAL_ChibiOS/CANIface.h>
#include <atomic>
#include <stdio.h>
#include <stdarg.h>
#include <math.h>
#include "protocol.h"
#include "command.h"
#include "sensors.h"
#include "thresholds.h"
#include "inventory.h"
#include "output_guard.h"
#include "link_timeout.h"
const AP_HAL::HAL &hal=AP_HAL::get_HAL();
void setup();void loop();
static constexpr uint8_t PROFILE=MYBOX_DIAG_PROFILE;
static constexpr uint8_t IMUS=PROFILE==2?2:1,BAROS=PROFILE==2?2:1,OUTPUTS=PROFILE==0?14:13;
static const char *const PROFILES[]={"MyboxH743_mini","MyboxH743_mini_v2","MyboxH743_mini_v2_vib"};
static DiagIMU imu[2];static DiagBaro baro[2];
static AP_HAL::AnalogSource *analog[4];
static AP_HAL::UARTDriver *usb;
static uint32_t sequence=0,dropped=0,last_stream=0,last_poll=0,last_hb=0,last_status=0;
static uint16_t stream_rate=0;
static mbd::Parser parser;
static char json_buffer[4097];static uint8_t frame[4116];
static bool send(uint8_t kind,const char *format,...) {
    va_list ap;va_start(ap,format);int n=vsnprintf(json_buffer,sizeof(json_buffer),format,ap);va_end(ap);
    if(n<0||size_t(n)>=sizeof(json_buffer)){dropped++;return false;}
    size_t len=mbd::encode(frame,kind,++sequence,AP_HAL::millis(),json_buffer);
    if(usb->txspace()<len){dropped++;return false;}return usb->write(frame,len)==len;
}
static void reply(uint32_t id,bool ok,const char *code="OK") {send(2,"{\"id\":%lu,\"ok\":%s,\"code\":\"%s\"}",(unsigned long)id,ok?"true":"false",code);}
struct Test {const char *id;const char *device;const char *method;bool automatic;};
static const Test tests[]={
 {"imu0.id","imu0","identity",true},{"imu0.stream","imu0","stream",true},{"imu0.rest","imu0","rest",false},{"imu0.motion","imu0","motion",false},{"imu0.selftest","imu0","selftest",false},
 {"imu1.id","imu1","identity",true},{"imu1.stream","imu1","stream",true},{"imu1.rest","imu1","rest",false},{"imu1.motion","imu1","motion",false},{"imu1.selftest","imu1","selftest",false},{"imu.compare","imu0","compare",false},
 {"baro0.id","baro0","identity",true},{"baro0.stream","baro0","stream",true},{"baro1.id","baro1","identity",true},{"baro1.stream","baro1","stream",true},
 {"osd.register","osd","register",true},{"osd.video","osd","visual",false},
 {"sd.read","sd","filesystem",true},{"sd.write","sd","scratch_file",false},
 {"flash.read","flash","read_crc",true},{"flash.write","flash","no_reserved_region",false},
 {"adc.voltage","adc","voltage",false},{"adc.current","adc","current",false},{"adc.pressure","adc","pressure",false},{"adc.rssi","adc","rssi",false},
 {"usb.link","usb","framed_heartbeat",true},
 {"uart1.loopback","uart1","tx_rx_jumper",false},{"uart2.loopback","uart2","tx_rx_jumper",false},{"uart3.loopback","uart3","tx_rx_jumper",false},{"uart4.loopback","uart4","tx_rx_jumper",false},{"uart5.loopback","uart5","tx_rx_jumper",false},
 {"rcin.frames","rcin","receiver_frames",false},{"can1.external","can1","external_analyzer",false},{"can2.external","can2","external_analyzer",false},{"i2c.external","i2c","external_device",false},{"mag.external","mag","external_compass",false},
 {"led.visual","led","visual",false},{"safety.led","safety","visual",false},{"safety.button","safety","button",false},{"buzzer.audio","buzzer","audible",false},{"heater.external","heater","disabled",false},
 {"pwm1.scope","pwm1","50hz_1000us_scope",false},{"pwm2.scope","pwm2","50hz_1000us_scope",false},{"pwm3.scope","pwm3","50hz_1000us_scope",false},{"pwm4.scope","pwm4","50hz_1000us_scope",false},{"pwm5.scope","pwm5","50hz_1000us_scope",false},{"pwm6.scope","pwm6","50hz_1000us_scope",false},{"pwm7.scope","pwm7","50hz_1000us_scope",false},{"pwm8.scope","pwm8","50hz_1000us_scope",false},{"pwm9.scope","pwm9","50hz_1000us_scope",false},{"pwm10.scope","pwm10","50hz_1000us_scope",false},{"pwm11.scope","pwm11","50hz_1000us_scope",false},{"pwm12.scope","pwm12","50hz_1000us_scope",false},{"pwm13.scope","pwm13","50hz_1000us_scope",false},{"pwm14.scope","pwm14","50hz_1000us_scope",false}
};
static constexpr unsigned NTESTS=sizeof(tests)/sizeof(tests[0]);
struct Result {const char *state="not_tested",*code="NOT_RUN",*detail="Test has not run",*expected="",*actual="";uint32_t duration=0;};
static Result results[NTESTS];
static char actual_text[NTESTS][128];
static int active=-1,cycle_index=-1,list_index=-1,result_index=-1;
static uint32_t test_start=0,test_count=0,test_errors=0;static bool active_started=false;
static float reference_accel[3]{},max_motion=0,sum_norm=0,max_diff=0;
static uint32_t samples_window=0;
static int find_test(const char *id) {for(unsigned i=0;i<NTESTS;i++){if(!strcmp(tests[i].id,id)){return i;}}return -1;}
static bool applicable(unsigned t) {
 const char *id=tests[t].id;
 if((!strncmp(id,"imu1",4)||!strcmp(id,"imu.compare")||!strncmp(id,"baro1",5))&&PROFILE!=2){return false;}
 if(!strcmp(id,"pwm14.scope")&&PROFILE!=0){return false;}
 if((!strcmp(id,"heater.external")||!strcmp(id,"buzzer.audio"))&&PROFILE==0){return false;}
 return true;
}
static bool result_send(unsigned i) {auto &r=results[i];return send(3,"{\"event\":\"result\",\"test\":\"%s\",\"state\":\"%s\",\"code\":\"%s\",\"detail\":\"%s\",\"expected\":\"%s\",\"actual\":\"%s\",\"duration_ms\":%lu}",tests[i].id,r.state,r.code,r.detail,r.expected,r.actual,(unsigned long)r.duration);}
static void can_stop();
static void finish(const char *state,const char *code,const char *detail,const char *expected="",const char *actual="") {
 if(active<0){return;}can_stop();auto &r=results[active];r.state=state;r.code=code;r.detail=detail;r.expected=expected;snprintf(actual_text[active],sizeof(actual_text[active]),"%s",actual);r.actual=actual_text[active];r.duration=AP_HAL::millis()-test_start;result_send(active);active=-1;active_started=false;
}
struct OutputPins {
 void off(int8_t channel,uint8_t pin) {
  if(channel>=0){hal.rcout->write(channel,0);hal.rcout->disable_ch(channel);hal.rcout->force_safety_on();}
  if(pin){hal.gpio->write(pin,pin==91?1:0);}
 }
};
class Safety:public mbd::OutputGuard<OutputPins> {
public:
 Safety():mbd::OutputGuard<OutputPins>(OutputPins{}) {}
 bool toggle=false;
 void tick() {
  enforce(AP_HAL::millis());
  if(!tripped&&gpio==77){toggle=!toggle;hal.gpio->write(77,toggle);}
 }
};
static Safety safety;
static AP_HAL::SPIDevice *osd=nullptr;
static bool osd_read(uint8_t reg,uint8_t &value) {
 if(!osd){osd=hal.spi->get_device_ptr("osd");}if(!osd||!osd->get_semaphore()->take(2)){return false;}
 uint8_t tx[2]={uint8_t(reg|0x80),0},rx[2]{};bool ok=osd->transfer_fullduplex(tx,rx,2);value=rx[1];osd->get_semaphore()->give();return ok;
}
static bool osd_write(uint8_t reg,uint8_t value) {
 if(!osd||!osd->get_semaphore()->take(2)){return false;}bool ok=osd->write_register(reg,value);osd->get_semaphore()->give();return ok;
}
static bool osd_pattern() {
 if(!osd_write(0,0x08)){return false;}const char *text="MYBOX DIAGNOSTIC";
 uint32_t start=AP_HAL::millis();for(uint16_t i=0;i<480;i++){if(AP_HAL::millis()-start>500){return false;}uint8_t v=(i/30==0||i/30==15||i%30==0||i%30==29)?'+':' ';if(i>=92&&i<92+strlen(text)){v=text[i-92];}if(!osd_write(5,i>>8)||!osd_write(6,i&255)||!osd_write(7,v)){return false;}}
 return true;
}
class StorageJob {
public:
    std::atomic<uint8_t> request{0},done{0};std::atomic<bool> busy{false};bool available=false;
    int64_t total=-1,free=-1;uint32_t elapsed_ms=0;uint8_t outcome=0;
    void task() {
        while(true) {
            uint8_t op=request;
            if(!op){hal.scheduler->delay(5);continue;}
            request=0;uint32_t start=AP_HAL::millis();outcome=0;
            if(op==1) {
                AP::FS().retry_mount();total=AP::FS().disk_space("/");free=AP::FS().disk_free("/");outcome=total>0?1:2;
            } else {
                const char *path="/MYBOX-DIAG-SCRATCH.bin";int fd=AP::FS().open(path,O_CREAT|O_EXCL|O_RDWR);
                if(fd<0){outcome=2;}
                else {
                    uint8_t pattern[512],actual[512];for(unsigned i=0;i<512;i++){pattern[i]=(i*37+19)&255;}
                    bool ok=AP::FS().write(fd,pattern,sizeof(pattern))==512&&AP::FS().fsync(fd)==0&&AP::FS().lseek(fd,0,SEEK_SET)==0&&AP::FS().read(fd,actual,sizeof(actual))==512&&!memcmp(pattern,actual,sizeof(pattern));
                    AP::FS().close(fd);bool removed=AP::FS().unlink(path)==0;outcome=ok&&removed?1:3;
                }
            }
            elapsed_ms=AP_HAL::millis()-start;done=op;busy=false;
        }
    }
    bool start(uint8_t op) {if(!available||busy){return false;}done=0;busy=true;request=op;return true;}
};
static StorageJob storage_job;
static void info(uint32_t id) {
 char uid[50]{};if(!hal.util->get_system_id(uid)){strcpy(uid,"unavailable");}
 send(2,"{\"id\":%lu,\"ok\":true,\"op\":\"info\",\"profile\":\"%s\",\"revision_source\":\"build_profile\",\"hardware_revision\":null,\"mcu\":\"STM32H743xx\",\"uid\":\"%s\",\"firmware\":\"MyboxDiag 0.2.1\",\"build_id\":\"%s\",\"protocol\":1,\"uptime_ms\":%lu,\"watchdog_reset\":%s,\"imu_count\":%u,\"barometer_count\":%u,\"outputs\":%u,\"orientation_source\":\"hardware_profile\",\"demo\":false,\"test_count\":%u,\"expected_devices\":%s,\"dropped_tx\":%lu}",(unsigned long)id,PROFILES[PROFILE],uid,MYBOX_DIAG_BUILD,(unsigned long)AP_HAL::millis(),hal.util->was_watchdog_reset()?"true":"false",IMUS,BAROS,OUTPUTS,NTESTS,EXPECTED_DEVICES_JSON,(unsigned long)dropped);
}
static void start_test(int t) {active=t;active_started=false;test_start=AP_HAL::millis();results[t]=Result{};results[t].state="running";results[t].code="RUNNING";result_send(t);}
static uint32_t requested_duration=1000;
static bool explicit_action=false;
static const uint8_t uart_pattern[]={0x55,0xaa,0,0xff,0x4d,0x42,0x44,0x31,0x12,0x34,0x56,0x78,0x87,0x65,0x43,0x21};
static uint8_t uart_received=0;static bool uart_bad=false;
static ChibiOS::CANIface *can_device[2]{};static int8_t can_active=-1;static uint32_t can_sent_ms=0;
static uint8_t can_payload[8]{};
static void can_stop() {if(can_active>=0){if(PROFILE||can_active==0){hal.gpio->write(70+can_active,1);}can_active=-1;}}

static void run_test() {
 if(active<0){return;}uint32_t now=AP_HAL::millis();const Test &t=tests[active];
 if(!applicable(active)){finish("not_applicable","NOT_APPLICABLE","Not fitted on this hardware profile");return;}
 if(!active_started) {
  active_started=true;
  if(!t.automatic&&!explicit_action){finish("needs_action","EXTERNAL_REQUIRED","Select this test and read connection instructions");return;}
  if(!strncmp(t.id,"imu",3) && strcmp(t.method,"compare")) {
   unsigned i=t.id[3]-'0';auto &s=imu[i].sample;
   if(!strcmp(t.method,"identity")){bool ok=imu[i].begin(i?"imu_isolated":PROFILE==0?"icm42688_1":"imu_main",i?2:PROFILE==0?0:1);char observed[96];snprintf(observed,sizeof(observed),"WHO_AM_I 0x%02X; transfer_errors %lu; configured %u",imu[i].sample.actual_id,(unsigned long)imu[i].sample.errors,imu[i].sample.configured);finish(ok?"passed":"failed",ok?"ID_CONFIG_OK":"IMU_ID_CONFIG","WHO_AM_I and configuration readback only",PROFILE==0?"0x47":i?"0x67":"0xE9",observed);return;}
   if(!strcmp(t.method,"selftest")){finish("warning","SELFTEST_NOT_IMPLEMENTED","Factory excitation and OTP comparison are not implemented; ID and streaming are separate tests");return;}
   if(!s.configured){finish("failed","IMU_UNAVAILABLE","Run identity test; sensor configuration failed");return;}
   test_count=s.count;test_errors=s.errors;max_motion=0;sum_norm=0;samples_window=0;for(unsigned k=0;k<3;k++){reference_accel[k]=s.accel[k];}
   return;
  }
  if(!strncmp(t.id,"baro",4)) {
   unsigned i=t.id[4]-'0';auto &s=baro[i].sample;
   if(!strcmp(t.method,"identity")){bool ok=baro[i].begin(i?0x77:PROFILE==0?0x77:0x76,PROFILE==0);char observed[96];snprintf(observed,sizeof(observed),"ID_or_CRC4 0x%02X; expected 0x%02X; transfer_errors %lu",s.actual_id,s.expected_id,(unsigned long)s.errors);finish(ok?"passed":"failed",ok?"ID_CONFIG_OK":"BARO_ID_CONFIG",PROFILE==0?"PROM CRC4 checked; MS5611 has no unique WHO_AM_I":"SPA06-003 ID and coefficients ready checked",PROFILE==0?"Valid PROM CRC4":"0x11",observed);return;}
   test_count=s.count;test_errors=s.errors;return;
  }
  if(!strcmp(t.id,"osd.register")) {uint8_t value=0,verify=0;bool ok=osd_read(0,value)&&value!=255&&osd_write(0,value^0x08)&&osd_read(0,verify)&&verify==(value^0x08);if(osd){osd_write(0,value);}finish(ok?"passed":"failed",ok?"OSD_REG_OK":"OSD_REGISTER","VM0 volatile register read/write only; video needs a separate visual test","VM0 readback","See status; no video assertion");return;}
  if(!strcmp(t.id,"osd.video")){if(!osd_pattern()){finish("failed","OSD_TRANSFER","Unable to send grid and text");return;}finish("needs_action","VISUAL_CONFIRM","Confirm grid and MYBOX DIAGNOSTIC text on an external analogue monitor");return;}
  if(!strcmp(t.id,"sd.read")||!strcmp(t.id,"sd.write")) {
   if(!storage_job.start(!strcmp(t.id,"sd.read")?1:2)){finish("warning","SD_WORKER_BUSY","SD worker is unavailable or a prior operation is still finishing");}
   return;
  }
  if(!strcmp(t.id,"flash.read")){const uint8_t *p=reinterpret_cast<const uint8_t *>(0x08020000);uint32_t crc=mbd::crc32(p,4096);send(3,"{\"event\":\"flash_crc\",\"address\":134348800,\"bytes\":4096,\"crc32\":%lu}",(unsigned long)crc);finish("passed","FLASH_READ_ONLY","Read CRC32 of first 4096 application bytes; no full-flash write or retention assertion");return;}
  if(!strcmp(t.id,"flash.write")){finish("warning","NO_FLASH_SCRATCH","No electrically documented disposable flash region; parameters and calibration sectors are preserved");return;}
  if(!strcmp(t.id,"usb.link")){finish(last_hb&&now-last_hb<1000?"passed":"needs_action",last_hb?"USB_FRAMED_OK":"USB_PC_REQUIRED","A valid CRC-framed USB request confirms a round trip only; prolonged stability needs a recorded session");return;}
  if(!strncmp(t.id,"uart",4)){unsigned i=t.id[4]-'0';auto *u=hal.serial(i);if(!u){finish("not_applicable","UART_ABSENT","UART not configured");return;}u->begin(115200,256,256);u->set_flow_control(AP_HAL::UARTDriver::FLOW_CONTROL_DISABLE);u->discard_input();u->write(uart_pattern,sizeof(uart_pattern));uart_received=0;uart_bad=false;return;}
  if(!strcmp(t.id,"rcin.frames")){test_count=0;return;}
  if(!strncmp(t.id,"can",3)) {
   unsigned i=t.id[3]-'1';
   if(i>=2){finish("not_applicable","CAN_ABSENT","No such CAN interface");return;}
   if(!can_device[i]){can_device[i]=new ChibiOS::CANIface(i);}
   if(!can_device[i]||(!can_device[i]->is_initialized()&&!can_device[i]->init(500000))){finish("failed","CAN_INIT","CAN controller initialization failed");return;}
   can_device[i]->clear_rx();can_active=i;can_sent_ms=0;
   mbd::put32(can_payload,now);mbd::put32(can_payload+4,now^0xa55a5aa5U);
   if(PROFILE||i==0){hal.gpio->write(70+i,0);}return;
  }
  if(!strcmp(t.id,"led.visual")||!strcmp(t.id,"safety.led")||!strcmp(t.id,"buzzer.audio")) {uint8_t pin=!strcmp(t.id,"led.visual")?91:!strcmp(t.id,"safety.led")?93:77;hal.gpio->pinMode(pin,HAL_GPIO_OUTPUT);safety.arm_gpio(pin,AP_HAL::millis(),last_hb,requested_duration);hal.gpio->write(pin,pin==91?0:1);return;}
  if(!strncmp(t.id,"pwm",3)) {unsigned ch=atoi(t.id+3)-1;if(ch>=OUTPUTS){finish("not_applicable","NO_OUTPUT","Output not present");return;}hal.rcout->force_safety_off();hal.rcout->set_freq(1U<<ch,50);hal.rcout->write(ch,1000);safety.arm_pwm(ch,AP_HAL::millis(),last_hb,requested_duration);hal.rcout->enable_ch(ch);hal.rcout->write(ch,1000);return;}
  if(!strcmp(t.id,"safety.button")){test_count=hal.gpio->read(92);return;}
  if(!strcmp(t.id,"imu.compare")){if(!imu[0].sample.configured||!imu[1].sample.configured){finish("failed","IMU_UNAVAILABLE","Two streaming IMUs are required");return;}max_diff=0;samples_window=0;return;}
  finish("needs_action",!strncmp(t.id,"adc",3)?"ANALOG_REFERENCE_REQUIRED":"EXTERNAL_NOT_AUTOMATED","Read the connection procedure; this path is not automatically verified by this firmware");return;
 }
 if(!strcmp(t.id,"rcin.frames")) {
  if(hal.rcin->new_input()) {unsigned count=hal.rcin->num_channels();bool plausible=count>=4;for(unsigned i=0;i<count;i++){uint16_t v=hal.rcin->read(i);plausible=plausible&&v>=750&&v<=2250;}if(plausible&&++test_count>=3){finish("passed","RCIN_FRAMES_OK","At least three decoded receiver frames with plausible channels; failsafe behaviour requires separate receiver disconnection check");return;}}
  if(now-test_start>5000){finish("needs_action","RCIN_SOURCE_REQUIRED","Connect a supported 3.3V receiver/generator to dedicated RCIN; absent frames do not prove input damage");}return;
 }
 if(!strncmp(t.id,"can",3)) {
  unsigned i=t.id[3]-'1';auto *dev=can_device[i];bool rd=true,wr=true;
  AP_HAL::CANFrame tx(0x6a0+i,can_payload,8);dev->select(rd,wr,&tx,AP_HAL::micros64());
  if(now-can_sent_ms>=100){int16_t sent=dev->send(tx,AP_HAL::micros64()+80000,AP_HAL::CANIface::AbortOnError);if(sent<0){finish("failed","CAN_SEND","CAN driver rejected frame");return;}if(sent>0){can_sent_ms=now;}}
  for(unsigned budget=0;budget<16;budget++){AP_HAL::CANFrame rx;uint64_t ts=0;AP_HAL::CANIface::CanIOFlags flags=0;int16_t n=dev->receive(rx,ts,flags);if(n<=0){break;}if(rx.id==0x6b0+i&&rx.dlc==8&&!memcmp(rx.data,can_payload,8)){finish("passed","CAN_ECHO_OK","500 kbit/s classic CAN round trip with external responder; independent response ID and session challenge checked");return;}}
  if(now-test_start>2000){char actual[96];snprintf(actual,sizeof(actual),"CAN errors %lu; busoff %u",(unsigned long)dev->getErrorCount(),dev->is_busoff());finish("needs_action","CAN_NO_ECHO","External responder must echo 8 payload bytes from ID 0x6A0/0x6A1 on 0x6B0/0x6B1; check wiring and termination","500 kbit/s echo",actual);}return;
 }
 if(!strcmp(t.id,"sd.read")||!strcmp(t.id,"sd.write")) {
  if(storage_job.done) {
   bool read_only=!strcmp(t.id,"sd.read");uint8_t result=storage_job.outcome;storage_job.done=0;
   char observed[128];snprintf(observed,sizeof(observed),"capacity_bytes %lld; free_bytes %lld; elapsed_ms %lu; test_bytes %u; bytes_per_s %lu",(long long)storage_job.total,(long long)storage_job.free,(unsigned long)storage_job.elapsed_ms,read_only?0:512,(unsigned long)(read_only?0:512000U/MAX(storage_job.elapsed_ms,1U)));
   finish(result==1?"passed":result==2?"needs_action":"failed",result==1?(read_only?"SD_MOUNT_OK":"SD_RW_OK"):result==2?"SD_CREATE":"SD_RW_ERROR",read_only?"Filesystem capacity query; no full read or write assertion":"Exclusive 512-byte scratch write/sync/readback/removal; existing files preserved","Available FAT volume; scratch test must match",observed);return;
  }
  if(now-test_start>cfg::test_timeout_ms){finish("warning","SD_TIMEOUT","SD operation exceeded deadline; worker remains isolated, other devices continue; do not remove power until it settles");}return;
 }
 if(!strncmp(t.id,"uart",4)) {auto *u=hal.serial(t.id[4]-'0');for(unsigned budget=0;budget<64&&u->available();budget++){int16_t b=u->read();if(b<0){break;}if(uart_received>=sizeof(uart_pattern)||b!=uart_pattern[uart_received]){uart_bad=true;}if(uart_received<255){uart_received++;}}
  if(uart_bad||uart_received>=sizeof(uart_pattern)){finish(uart_bad?"failed":"passed",uart_bad?"UART_MISMATCH":"UART_LOOPBACK_OK","115200 8N1 TX/RX jumper, 16-byte pattern only; RTS/CTS not checked");return;}
  if(now-test_start>1000){finish("needs_action","UART_NO_LOOPBACK","Connect this port TX to RX with safe 3.3V levels; no reply is not proof of a failed UART");}return;
 }
 if(!strncmp(t.id,"pwm",3)||!strcmp(t.id,"led.visual")||!strcmp(t.id,"safety.led")||!strcmp(t.id,"buzzer.audio")) {if(safety.tripped){safety.stop();finish("needs_action","OPERATOR_CONFIRM","Active signal ended; confirm observed signal with external instrument or visual/audio observation");}return;}
 if(!strcmp(t.id,"safety.button")){if(uint32_t(hal.gpio->read(92))!=test_count){finish("passed","BUTTON_EDGE","Safety input changed after user action; switch debounce and power-up behaviour not covered");return;}if(now-test_start>5000){finish("needs_action","BUTTON_PRESS","Press and release the safety button");}return;}
 if(!strcmp(t.id,"imu.compare")){float d=0;for(unsigned k=0;k<3;k++){d+=sq(imu[0].sample.accel[k]-imu[1].sample.accel[k]);}max_diff=MAX(max_diff,sqrtf(d));samples_window++;if(now-test_start>cfg::observation_ms){finish(max_diff<cfg::imu_difference_m_s2?"passed":"warning",max_diff<cfg::imu_difference_m_s2?"IMU_COMPARE_OK":"IMU_DISAGREEMENT","Acceleration agreement in profile axes; vibration and mounting conditions affect comparison","Difference below configured 3 m/s2",max_diff<cfg::imu_difference_m_s2?"Within screening threshold":"Review motion, mounting and profile rotation");}return;}
 if(!strncmp(t.id,"imu",3)) {
  auto &s=imu[t.id[3]-'0'].sample;float norm=0;for(unsigned k=0;k<3;k++){norm+=sq(s.accel[k]);max_motion=MAX(max_motion,fabsf(s.gyro[k]));}sum_norm+=sqrtf(norm);samples_window++;
  if(now-test_start<cfg::observation_ms){return;}
  if(s.count==test_count||now-s.last_ms>cfg::imu_stale_ms||s.errors>test_errors){finish("failed","IMU_STALE_OR_IO","No fresh data, stale sample or transfer error during observation","New DRDY samples; no transfer errors","Missing data or transfer errors");return;}
  if(!strcmp(t.method,"rest")){float g=sum_norm/MAX(samples_window,1U);bool stable=max_motion<cfg::rest_gyro_deg_s&&fabsf(g-9.80665f)<cfg::rest_gravity_tolerance_m_s2;finish(stable?"passed":"warning",stable?"REST_OK":"REST_CONDITIONS","Screening without calibration; movement or bias is not a hardware failure");return;}
  if(!strcmp(t.method,"motion")){finish(max_motion>cfg::motion_gyro_deg_s?"passed":"needs_action",max_motion>cfg::motion_gyro_deg_s?"MOTION_OBSERVED":"MOVE_BOARD","Rotate the board; observed angular rate must exceed configured 30 deg/s");return;}
  finish(s.saturated?"warning":"passed",s.saturated?"IMU_SATURATION":"IMU_STREAM_OK","DRDY-gated polling; observed acquisition rate is separate from configured 200 Hz ODR");return;
 }
 if(!strncmp(t.id,"baro",4)) {auto &s=baro[t.id[4]-'0'].sample;if(now-test_start<cfg::observation_ms){return;}if(s.count==test_count||now-s.last_ms>cfg::baro_stale_ms||s.errors>test_errors){finish("failed","BARO_STALE_OR_IO","No fresh barometer data or transfer errors");return;}bool range=s.pressure>cfg::pressure_min_pa&&s.pressure<cfg::pressure_max_pa&&s.temperature>cfg::temperature_min_c&&s.temperature<cfg::temperature_max_c;finish(range?"passed":"warning",range?"BARO_STREAM_OK":"BARO_RANGE","Broad environmental screening; unusual pressure or temperature needs reference measurement");return;}
 if(now-test_start>cfg::test_timeout_ms){safety.stop();finish("failed","TEST_TIMEOUT","Test deadline exceeded");}
}
static void telemetry() {
 uint32_t now=AP_HAL::millis();
 for(unsigned i=0;i<IMUS;i++){auto &s=imu[i].sample;send(4,"{\"sensor\":\"imu%u\",\"sample_ms\":%lu,\"sample_count\":%lu,\"fresh\":%s,\"measurement_hz\":%.2f,\"configured_odr_hz\":200,\"errors\":%lu,\"saturated\":%lu,\"accel_m_s2\":[%.5f,%.5f,%.5f],\"gyro_deg_s\":[%.5f,%.5f,%.5f],\"temperature_c\":%.3f,\"raw\":[%d,%d,%d,%d,%d,%d,%d],\"rotation\":\"ROTATION_NONE\"}",i,(unsigned long)s.last_ms,(unsigned long)s.count,s.count&&now-s.last_ms<cfg::imu_stale_ms?"true":"false",(double)s.hz,(unsigned long)s.errors,(unsigned long)s.saturated,(double)s.accel[0],(double)s.accel[1],(double)s.accel[2],(double)s.gyro[0],(double)s.gyro[1],(double)s.gyro[2],(double)s.temperature,s.raw[0],s.raw[1],s.raw[2],s.raw[3],s.raw[4],s.raw[5],s.raw[6]);}
 for(unsigned i=0;i<BAROS;i++){auto &s=baro[i].sample;float altitude=s.pressure>0&&s.baseline>0?44330.0f*(1-powf(s.pressure/s.baseline,0.19029495f)):0;send(4,"{\"sensor\":\"baro%u\",\"sample_ms\":%lu,\"sample_count\":%lu,\"fresh\":%s,\"measurement_hz\":%.2f,\"errors\":%lu,\"pressure_pa\":%.2f,\"temperature_c\":%.3f,\"relative_altitude_m\":%.3f}",i,(unsigned long)s.last_ms,(unsigned long)s.count,s.count&&now-s.last_ms<cfg::baro_stale_ms?"true":"false",(double)s.hz,(unsigned long)s.errors,(double)s.pressure,(double)s.temperature,(double)altitude);}
 const char *names[]={"voltage","current","pressure","rssi"};float scale[]={PROFILE==0?20.0f:21.0f,83.333f,2,1};
 for(unsigned i=0;i<4;i++){if(!analog[i]){continue;}float raw=analog[i]->read_latest(),v=analog[i]->voltage_latest();if(i==2){v*=0.5f;} // HAL already applies HWDEF SCALE(2) on PC4; expose actual ADC volts first.
 send(4,"{\"sensor\":\"adc.%s\",\"sample_ms\":%lu,\"raw\":%.2f,\"adc_voltage_v\":%.5f,\"scale\":%.5f,\"value\":%.5f,\"fresh\":true,\"units\":\"%s\",\"measurement_hz\":null,\"timestamp_source\":\"hal_readout\"}",names[i],(unsigned long)now,(double)raw,(double)v,(double)scale[i],(double)(v*scale[i]),i==1?"A":"V");}
}
static void command(const Command &c) {
 uint32_t now=AP_HAL::millis();last_hb=now;safety.heartbeat=now;
 if(!strcmp(c.op,"info")){info(c.id);return;}
 if(!strcmp(c.op,"ping")){reply(c.id,true);return;}
 if(!strcmp(c.op,"list")){list_index=0;reply(c.id,true);return;}
 if(!strcmp(c.op,"results")){result_index=0;reply(c.id,true);return;}
 if(!strcmp(c.op,"stream")){if(c.rate>100){reply(c.id,false,"RATE_RANGE_0_100");return;}stream_rate=c.rate;reply(c.id,true);return;}
 if(!strcmp(c.op,"stop")){can_stop();safety.stop();cycle_index=-1;finish("not_tested","CANCELLED","Stopped by operator");reply(c.id,true);return;}
 if(!strcmp(c.op,"confirm")){int t=find_test(c.test);if(t<0||!applicable(t)||strcmp(results[t].state,"needs_action")){reply(c.id,false,"CONFIRM_STATE");return;}bool allowed=!strcmp(tests[t].method,"visual")||!strcmp(tests[t].method,"audible")||!strncmp(tests[t].id,"pwm",3);if(!allowed){reply(c.id,false,"AUTOMATIC_EVIDENCE_REQUIRED");return;}results[t].state=c.confirm?"passed":"failed";results[t].code=c.confirm?"OPERATOR_CONFIRMED":"OPERATOR_REJECTED";results[t].detail="Operator observation; scope is the named visual, audio or external signal test";result_send(t);reply(c.id,true);return;}
 if(!strcmp(c.op,"run")) {
  if(active>=0||cycle_index>=0){reply(c.id,false,"BUSY");return;}
  if(!strcmp(c.test,"all")){explicit_action=false;cycle_index=0;reply(c.id,true);return;}
  int t=find_test(c.test);if(t<0){reply(c.id,false,"UNKNOWN_TEST");return;}
  bool dangerous=!strncmp(c.test,"pwm",3);if(dangerous&&!c.confirm){reply(c.id,false,"REMOVE_PROPS_CONFIRM_REQUIRED");return;}
  if(c.duration_ms<100||c.duration_ms>cfg::actuator_max_ms){reply(c.id,false,"DURATION_RANGE_100_2000");return;}
  requested_duration=c.duration_ms;explicit_action=true;start_test(t);reply(c.id,true);return;
 }
 reply(c.id,false,"UNKNOWN_OPERATION");
}
static void heartbeat_led() {
 // Optical confirmation is still a separate operator test. This is a liveness indicator.
 if(safety.gpio==91){return;}
 hal.gpio->write(91,((AP_HAL::millis()/250U)&1U)?0:1);
}
void setup() {
 usb=hal.serial(0);usb->begin(115200,8192,16384);hal.util->set_soft_armed(false);
 hal.rcin->init();hal.rcout->init();hal.rcout->force_safety_on();for(unsigned i=0;i<OUTPUTS;i++){hal.rcout->write(i,0);hal.rcout->disable_ch(i);}
 for(uint8_t pin: {uint8_t(91),uint8_t(93)}){hal.gpio->pinMode(pin,HAL_GPIO_OUTPUT);hal.gpio->write(pin,pin==91?1:0);}
 if(PROFILE){hal.gpio->pinMode(80,HAL_GPIO_OUTPUT);hal.gpio->write(80,0);hal.gpio->pinMode(77,HAL_GPIO_OUTPUT);hal.gpio->write(77,0);}
 hal.gpio->pinMode(92,HAL_GPIO_INPUT);
 hal.gpio->write(91,0); // visible startup indication before the first complete cycle
 const uint8_t pins[]={10,11,4,8};for(unsigned i=0;i<4;i++){analog[i]=hal.analogin->channel(pins[i]);}
 hal.scheduler->register_timer_process(FUNCTOR_BIND(&safety,&Safety::tick,void));
 storage_job.available=hal.scheduler->thread_create(FUNCTOR_BIND(&storage_job,&StorageJob::task,void),"diag_sd",3072,AP_HAL::Scheduler::PRIORITY_IO,0);
 cycle_index=0;explicit_action=false;
}
void loop() {
 uint32_t now=AP_HAL::millis();
 for(unsigned budget=0;budget<1024&&usb->available();budget++){int16_t b=usb->read();if(b<0){break;}if(parser.feed(b,now)){if(parser.buf[5]==1){Command c;if(c.parse(parser.payload())){command(c);}else{send(3,"{\"event\":\"error\",\"code\":\"BAD_COMMAND\"}");}}parser.consume();}}
 if(now-last_poll>=2){last_poll=now;for(unsigned i=0;i<IMUS;i++){imu[i].poll();}for(unsigned i=0;i<BAROS;i++){baro[i].poll();}}
 safety.tick();heartbeat_led();
 if(active<0&&cycle_index>=0){if(unsigned(cycle_index)<NTESTS){start_test(cycle_index++);}else{cycle_index=-1;send(3,"{\"event\":\"cycle_complete\"}");}}
 run_test();
 if(list_index>=0&&usb->txspace()>4096){if(unsigned(list_index)<NTESTS){const auto &t=tests[list_index];if(send(3,"{\"event\":\"test\",\"test\":\"%s\",\"device\":\"%s\",\"method\":\"%s\",\"automatic\":%s,\"applicable\":%s}",t.id,t.device,t.method,t.automatic?"true":"false",applicable(list_index)?"true":"false")){list_index++;}}else{if(send(3,"{\"event\":\"list_complete\"}")){list_index=-1;}}}
 if(result_index>=0&&usb->txspace()>4096){if(unsigned(result_index)<NTESTS){if(result_send(result_index)){result_index++;}}else{if(send(3,"{\"event\":\"results_complete\"}")){result_index=-1;}}}
 if(stream_rate&&now-last_stream>=1000U/stream_rate){last_stream=now;telemetry();}
 // command() refreshes last_hb after the loop's initial time snapshot.
 if(last_hb&&mbd::link_expired(AP_HAL::millis(),last_hb,2000)){can_stop();safety.stop();stream_rate=0;last_hb=0;}
 if(now-last_status>1000&&stream_rate){last_status=now;send(3,"{\"event\":\"link\",\"uptime_ms\":%lu,\"parser_errors\":%lu,\"dropped_tx\":%lu,\"stream_hz\":%u,\"active_test\":%d}",(unsigned long)now,(unsigned long)parser.errors,(unsigned long)dropped,stream_rate,active);}
 hal.scheduler->delay(1);
}
AP_HAL_MAIN();
