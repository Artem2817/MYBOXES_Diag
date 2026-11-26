// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>
namespace mbd {
constexpr uint16_t MAX_PAYLOAD = 4096;
constexpr uint8_t VERSION = 1;
constexpr size_t HEADER = 16;
inline uint32_t crc32(const uint8_t *p, size_t n) {
    uint32_t c = 0xffffffffU;
    while (n--) { c ^= *p++; for (uint8_t i=0; i<8; i++) { c = (c>>1) ^ (0xedb88320U & (0U-(c&1U))); } }
    return ~c;
}
inline uint32_t get32(const uint8_t *p) { return uint32_t(p[0]) | uint32_t(p[1])<<8 | uint32_t(p[2])<<16 | uint32_t(p[3])<<24; }
inline void put32(uint8_t *p,uint32_t v) { for (uint8_t i=0;i<4;i++) {p[i]=v>>(8*i);} }
inline size_t encode(uint8_t *out, uint8_t kind, uint32_t seq, uint32_t ms, const char *payload) {
    const size_t n=strlen(payload); if(n>MAX_PAYLOAD) {return 0;}
    memcpy(out,"MBD1",4); out[4]=VERSION;out[5]=kind;out[6]=n&255;out[7]=n>>8;
    put32(out+8,seq);put32(out+12,ms);memcpy(out+HEADER,payload,n);
    put32(out+HEADER+n,crc32(out,HEADER+n));return HEADER+n+4;
}
struct Parser {
    uint8_t buf[MAX_PAYLOAD+HEADER+5]{};size_t used=0;uint32_t last_ms=0,errors=0;
    bool feed(uint8_t c,uint32_t ms) {
        if (used && uint32_t(ms-last_ms)>250) {used=0;errors++;}
        last_ms=ms;
        if(used==sizeof(buf)) {shift();errors++;}
        buf[used++]=c;return next();
    }
    void shift() {if(used) {memmove(buf,buf+1,--used);}}
    bool next() {
        while(used>=4) {
            if(memcmp(buf,"MBD1",4)) {shift();continue;}
            if(used<HEADER) {return false;}
            size_t n=buf[6]|uint16_t(buf[7])<<8;
            if(buf[4]!=VERSION || n>MAX_PAYLOAD) {errors++;shift();continue;}
            if(used<HEADER+n+4) {return false;}
            if(crc32(buf,HEADER+n)!=get32(buf+HEADER+n)) {errors++;shift();continue;}
            // Consumer finishes before the next byte is fed. CRC is no longer needed.
            buf[HEADER+n]=0;return true;
        }
        return false;
    }
    const char *payload() const {return reinterpret_cast<const char *>(buf+HEADER);}
    void consume() {used=0;}
};
}
