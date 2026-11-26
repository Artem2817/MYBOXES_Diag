"""Native regression: late hardware enable after timer revocation stays tracked."""
from pathlib import Path
import subprocess

def test_output_expiry_late_enable_disconnect_and_clock_wrap(tmp_path):
    root=Path(__file__).resolve().parents[1];source=tmp_path/'guard.cpp'
    source.write_text(r'''
#include "output_guard.h"
#include <assert.h>
struct State {bool pwm_on=false,gpio_on=false;unsigned off_calls=0;};
struct Pins {State *state;void off(int8_t ch,uint8_t pin){if(ch>=0){state->pwm_on=false;}if(pin){state->gpio_on=false;}state->off_calls++;}};
int main(){
 State state;mbd::OutputGuard<Pins> g{Pins{&state}};
 g.enforce(10000);assert(state.off_calls==0); // no output enabled after boot
 g.arm_pwm(3,1000,0,1000);g.enforce(1000);assert(g.tripped&&g.pwm==3);
 state.pwm_on=true; // main thread resumes an enable interrupted by revocation
 g.enforce(1001);assert(!state.pwm_on&&g.pwm==3); // timer still owns that channel
 g.stop();assert(g.pwm==-1&&!g.tripped&&!state.pwm_on);
 g.arm_pwm(2,100,100,2000);state.pwm_on=true;g.enforce(850);assert(state.pwm_on&&!g.tripped);
 g.enforce(851);assert(!state.pwm_on&&g.tripped);g.stop();
 g.arm_gpio(91,1000,1000,500);state.gpio_on=true;g.enforce(1499);assert(state.gpio_on);
 g.enforce(1500);assert(!state.gpio_on&&g.tripped&&g.gpio==91);g.stop();
 const uint32_t begin=0xffffff00U;
 g.arm_pwm(0,begin,begin,500);state.pwm_on=true;g.enforce(begin+499);assert(state.pwm_on);
 g.enforce(begin+500);assert(!state.pwm_on&&g.tripped);g.stop();
 g.arm_pwm(1,10,10,999999);assert(g.deadline==2010); // independent hard duration cap
 g.stop();g.arm_pwm(1,100,101,500);state.pwm_on=true;
 g.enforce(100);assert(state.pwm_on&&!g.tripped); // heartbeat newer than snapshot
 assert(!mbd::link_expired(100,101,2000));
 assert(!mbd::link_expired(2100,100,2000));
 assert(mbd::link_expired(2101,100,2000));
 assert(!mbd::link_expired(begin+1999,begin,2000));
 assert(mbd::link_expired(begin+2001,begin,2000));
}
''')
    binary=tmp_path/'guard';subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(root/'firmware'),str(source),'-o',str(binary)],check=True)
    subprocess.run([binary],check=True)
