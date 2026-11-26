// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>
struct Command {
    uint32_t id=0, rate=20, duration_ms=1000, channel=0;
    char op[24]{},test[48]{};bool confirm=false;
    static void ws(const char *&p) {while(*p && isspace((unsigned char)*p)){p++;}}
    static bool str(const char *&p,char *out,size_t cap) {
        if(*p++!='"'){return false;} size_t n=0;
        while(*p && *p!='"') {if((unsigned char)*p<32 || *p=='\\' || n+1>=cap){return false;}out[n++]=*p++;}
        out[n]=0;if(*p!='"'){return false;}p++;return true;
    }
    bool parse(const char *p) {
        ws(p);if(*p++!='{'){return false;}uint32_t seen=0;
        for(unsigned k=0;k<10;k++) {
            ws(p);if(*p=='}'){p++;ws(p);return !*p && (seen&3)==3 && id>0;}
            char key[24]{},value[64]{};if(!str(p,key,sizeof(key))){return false;}ws(p);if(*p++!=':'){return false;}ws(p);
            bool string=*p=='"';
            if(string) {if(!str(p,value,sizeof(value))){return false;}}
            else {size_t n=0;while(*p && *p!=',' && *p!='}' && !isspace((unsigned char)*p)){if(n+1>=sizeof(value)){return false;}value[n++]=*p++;}value[n]=0;}
            unsigned bit=0;
            if(!strcmp(key,"id")){bit=1;}else if(!strcmp(key,"op")){bit=2;}else if(!strcmp(key,"test")){bit=4;}
            else if(!strcmp(key,"rate")){bit=8;}else if(!strcmp(key,"duration_ms")){bit=16;}else if(!strcmp(key,"channel")){bit=32;}else if(!strcmp(key,"confirm")){bit=64;}else{return false;}
            if(seen&bit){return false;}seen|=bit;
            if(bit==2 || bit==4) {if(!string){return false;}char *dest=bit==2?op:test;size_t cap=bit==2?sizeof(op):sizeof(test);if(strlen(value)>=cap){return false;}strcpy(dest,value);}
            else if(bit==64){if(string || (strcmp(value,"true") && strcmp(value,"false"))){return false;}confirm=!strcmp(value,"true");}
            else {if(string || !*value){return false;}uint64_t v=0;for(const char *q=value;*q;q++){if(!isdigit((unsigned char)*q)){return false;}v=v*10+(*q-'0');if(v>UINT32_MAX){return false;}}if(bit==1){id=v;}else if(bit==8){rate=v;}else if(bit==16){duration_ms=v;}else{channel=v;}}
            ws(p);if(*p==','){p++;ws(p);if(*p=='}'){return false;}continue;}if(*p!='}'){return false;}
        }
        return false;
    }
};
