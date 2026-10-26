#define TERMINAL_TEST
static void trace_pixel(unsigned x,unsigned y);
#define FB_PIXEL_TRACE trace_pixel
#include "../tools/ondevice-terminal.c"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned writes,outside_cursor_writes,keyboard_writes;
static int trace_blink,trace_keyboard;
static void trace_pixel(unsigned x,unsigned y)
{
    writes++;
    if(trace_blink && (y<header_h+cy*cell_h || y>=header_h+(cy+1)*cell_h || x<cx*cell_w || x>=(cx+1)*cell_w))outside_cursor_writes++;
    if(trace_keyboard && y>=keyboard_y)keyboard_writes++;
}
static void feed(const char *s){for(;*s;s++)terminal_byte(*s);}
static unsigned event(unsigned type,unsigned code,int value,char bytes[4])
{
    struct input_event e={0};e.type=type;e.code=code;e.value=value;return input_event_bytes(&e,bytes);
}
static void begin(unsigned x,unsigned y,char bytes[4])
{
    event(EV_ABS,ABS_MT_SLOT,0,bytes);event(EV_ABS,ABS_MT_TRACKING_ID,10,bytes);
    event(EV_ABS,ABS_MT_POSITION_X,x,bytes);event(EV_ABS,ABS_MT_POSITION_Y,y,bytes);
    assert(!event(EV_SYN,SYN_REPORT,0,bytes));
}
static void move(unsigned x,unsigned y,char bytes[4])
{
    event(EV_ABS,ABS_MT_POSITION_X,x,bytes);event(EV_ABS,ABS_MT_POSITION_Y,y,bytes);
    assert(!event(EV_SYN,SYN_REPORT,0,bytes));
}
static unsigned release(char bytes[4])
{
    event(EV_ABS,ABS_MT_TRACKING_ID,-1,bytes);return event(EV_SYN,SYN_REPORT,0,bytes);
}
static void reset_touch(void)
{
    memset(contacts,0,sizeof(contacts));selected_slot=touch_pressed=dropped=0;
    gesture=GESTURE_NONE;gesture_slot=-1;gesture_cancelled=gesture_sent=0;
    highlighted_row=highlighted_col=-1;input_now=0;
    touch_x.minimum=touch_y.minimum=0;touch_x.maximum=screen_w-1;touch_y.maximum=screen_h-1;
}
static void geometry_and_keys(void)
{
    for(unsigned row=0;row<5;row++)for(unsigned col=0;col<key_count(row);col++){
        struct key_rect k=key_geometry(row,col);unsigned r,c;
        assert(k.w>0 && k.h>0 && k.x+k.w<=screen_w && k.y+k.h<=screen_h);
        assert(key_hit(k.x+k.w/2,k.y+k.h/2,&r,&c) && r==row && c==col);
        assert(!key_hit(k.x-1,k.y-1,&r,&c));
    }
    assert(key_geometry(2,0).x>key_geometry(1,0).x);
    assert(key_geometry(4,2).w>4*key_geometry(4,1).w);
    char bytes[4];shifted=symbols=control_key=alt_key=0;
    assert(key_bytes(0,1,bytes)==0 && control_key);
    assert(key_bytes(3,3,bytes)==1 && bytes[0]==3 && !control_key); /* Ctrl+C */
    key_bytes(3,0,bytes);assert(shifted);
    assert(key_bytes(1,0,bytes)==1 && bytes[0]=='Q' && !shifted); /* one shot */
    assert(key_bytes(1,0,bytes)==1 && bytes[0]=='q');
    for(unsigned i=0;i<4;i++){assert(key_bytes(0,4+i,bytes)==3 && bytes[0]==27 && bytes[1]=='[' && bytes[2]=="DBAC"[i]);}
    assert(key_bytes(0,3,bytes)==1 && bytes[0]=='\t');
    key_bytes(0,2,bytes);assert(key_bytes(1,0,bytes)==2 && bytes[0]==27 && bytes[1]=='q' && !alt_key);
    key_bytes(0,1,bytes);key_bytes(0,2,bytes);assert(key_bytes(3,3,bytes)==2 && bytes[0]==27 && bytes[1]==3);
    assert(key_bytes(3,8,bytes)==1 && bytes[0]==127);
    assert(key_bytes(4,2,bytes)==1 && bytes[0]==' ');
    assert(key_bytes(4,4,bytes)==1 && bytes[0]=='\r');
    unsigned char available[128]={0};
    for(unsigned mode=0;mode<2;mode++)for(unsigned upper=0;upper<2;upper++)
        for(unsigned row=1;row<5;row++)for(unsigned col=0;col<key_count(row);col++){
            symbols=mode;shifted=upper;control_key=alt_key=0;
            unsigned n=key_bytes(row,col,bytes);if(n==1 && (unsigned char)bytes[0]<128)available[(unsigned char)bytes[0]]=1;
        }
    for(unsigned c=32;c<127;c++)assert(available[c]); /* all shell punctuation */
    shifted=symbols=control_key=alt_key=0;
}
static void parser_history_sessions(void)
{
    dimensions(720,1280);sessions_init();assert(cols==40 && rows>20);
    feed("abc\r\nhello\033[2D\033[K");assert(cells[0][0]=='a' && cells[1][2]=='l' && cells[1][3]==' ');
    feed("\033[999999;999999H");assert(cx<cols && cy<rows);
    feed("\033[2J\033[H");assert(cx==0 && cy==0 && cells[0][0]==' ');
    feed("\033]0;hidden title\007test");assert(cells[0][0]=='t');
    sessions_init();
    for(unsigned i=0;i<rows+10;i++){char b[32];snprintf(b,sizeof(b),"line %03u\r\n",i);feed(b);}
    assert(cy==rows-1 && sessions[0].history_count==11);
    scroll_lines(5);assert(sessions[0].scroll==5);unsigned char anchor[40];for(unsigned x=0;x<cols;x++)anchor[x]=visible_cell(0,x);
    feed("new output\r\n");assert(sessions[0].scroll==6);
    for(unsigned x=0;x<cols;x++)assert(visible_cell(0,x)==anchor[x]);
    scroll_lines(100000);assert(sessions[0].scroll==sessions[0].history_count);assert(visible_cell(0,5)=='0');
    scroll_lines(-100000);assert(!sessions[0].scroll);
    activate_session(1);assert(cx==0 && cy==0 && cells[0][0]==' ' && !sessions[1].history_count);
    feed("session two\033[2;");activate_session(0);feed("one");assert(escape_state==0);
    activate_session(1);assert(escape_state==2);feed("4H!");assert(cy==1 && cells[1][3]=='!');
    activate_session(0);assert(sessions[0].history_count==12 && cells[cy][0]=='o');
    for(unsigned i=0;i<HISTORY_LINES+20;i++)feed("bounded\r\n");
    assert(sessions[0].history_count==HISTORY_LINES);scroll_lines(9999);assert(sessions[0].scroll==HISTORY_LINES);
    feed("\033[3J");assert(!sessions[0].history_count && !sessions[0].scroll);
}
static void touch_and_gestures(void)
{
    sessions_init();reset_touch();geometry_and_keys();char bytes[4];
    struct key_rect q=key_geometry(1,0);unsigned x=q.x+q.w/2,y=q.y+q.h/2;
    begin(x,y,bytes);assert(!event(EV_SYN,SYN_REPORT,0,bytes));assert(release(bytes)==1 && bytes[0]=='q');
    /* The driver may reuse unchanged coordinates for a new tracking ID. */
    event(EV_ABS,ABS_MT_TRACKING_ID,11,bytes);assert(!event(EV_SYN,SYN_REPORT,0,bytes));assert(release(bytes)==1 && bytes[0]=='q');
    input_now=1000;begin(x,y,bytes);assert(!input_tick(1449,bytes));assert(input_tick(1450,bytes)==1 && bytes[0]=='1');assert(!input_tick(1600,bytes));assert(!release(bytes));
    input_now=2000;begin(x,y,bytes);input_now=2500;assert(release(bytes)==1 && bytes[0]=='1');
    begin(x,y,bytes);move(x+100,y,bytes);assert(!release(bytes)); /* drag cancels key */
    begin(x,y,bytes);event(EV_SYN,SYN_DROPPED,0,bytes);assert(!event(EV_SYN,SYN_REPORT,0,bytes));assert(!release(bytes));
    /* A second contact cannot turn into a phantom key or swipe. */
    begin(x,y,bytes);event(EV_ABS,ABS_MT_SLOT,1,bytes);event(EV_ABS,ABS_MT_TRACKING_ID,20,bytes);
    event(EV_ABS,ABS_MT_POSITION_X,x+72,bytes);event(EV_ABS,ABS_MT_POSITION_Y,y,bytes);assert(!event(EV_SYN,SYN_REPORT,0,bytes));
    event(EV_ABS,ABS_MT_TRACKING_ID,-1,bytes);event(EV_SYN,SYN_REPORT,0,bytes);event(EV_ABS,ABS_MT_SLOT,0,bytes);assert(!release(bytes));
    begin(150,200,bytes);move(350,210,bytes);assert(!release(bytes) && active_session==1);
    begin(350,200,bytes);move(150,210,bytes);assert(!release(bytes) && active_session==0);
    begin(150,200,bytes);event(EV_ABS,ABS_MT_POSITION_X,350,bytes);assert(!release(bytes) && active_session==1);
    activate_session(0);
    activate_session(2);begin(150,200,bytes);move(350,210,bytes);release(bytes);assert(active_session==0);
    for(unsigned i=0;i<rows+20;i++)feed("scroll\r\n");
    unsigned count=sessions[0].history_count;
    begin(300,200,bytes);move(302,200+3*cell_h,bytes);assert(sessions[0].scroll==3);release(bytes);
    begin(300,300,bytes);move(301,300-2*cell_h,bytes);release(bytes);assert(sessions[0].scroll==1);
    begin(300,200,bytes);move(300,700,bytes);release(bytes);assert(sessions[0].scroll<=count);
    begin(20,20,bytes);release(bytes);assert(!sessions[0].scroll);
    scroll_lines(3);assert(key_bytes(1,0,bytes)==1 && !sessions[0].scroll);
    reset_touch();
}
static void power_checks(void)
{
    struct input_event power={0};power.type=EV_KEY;power.code=KEY_POWER;power.value=1;
    power_event(&power,100);assert(!power_tick(1299));assert(power_tick(1300) && power_menu);assert(!power_tick(2500));
    power.value=0;power_event(&power,2600);assert(power_menu && !power_held);
    unsigned top=screen_h/5,height=screen_h*3/5,header=height/6;
    for(unsigned i=0;i<4;i++)assert(menu_hit(screen_w/2,top+header+(2*i+1)*(height-header)/8)==(int)i+1);
    assert(menu_hit(0,top)==POWER_NONE);
    unsigned command=0;const char *argument=0;
    for(int action=POWER_OFF;action<=POWER_SYSTEM;action++)assert(!power_plan(action,1,&command,&argument));
    assert(power_plan(POWER_OFF,0,&command,&argument) && command==LINUX_REBOOT_CMD_POWER_OFF && !argument);
    assert(power_plan(POWER_DOWNLOAD,0,&command,&argument) && command==LINUX_REBOOT_CMD_RESTART2 && !strcmp(argument,"download"));
    assert(power_plan(POWER_SYSTEM,0,&command,&argument) && command==LINUX_REBOOT_CMD_RESTART && !argument);
    assert(!power_plan(POWER_CANCEL,0,&command,&argument) && !power_plan(99,0,&command,&argument));
    char bytes[4];reset_touch();power_action=POWER_NONE;
    begin(0,top,bytes);move(screen_w/2,top+header+(height-header)/8,bytes);release(bytes);assert(power_action==POWER_NONE);
    begin(screen_w/2,top+header+7*(height-header)/8,bytes);assert(!release(bytes) && !power_menu);
    power.value=1;power_event(&power,3000);power.value=0;power_event(&power,3100);assert(!power_tick(5000));
    power.value=1;power_event(&power,6000);power.type=EV_SYN;power.code=SYN_DROPPED;power_event(&power,6100);assert(!power_tick(9000));
}
static void save_ppm(const char *path,unsigned char *map,const struct fb_fix_screeninfo *f)
{
    FILE *out=fopen(path,"wb");assert(out);fprintf(out,"P6\n%u %u\n255\n",screen_w,screen_h);
    for(unsigned y=0;y<screen_h;y++)for(unsigned x=0;x<screen_w;x++){
        unsigned at=y*f->line_length+x*4;unsigned char rgb[3]={map[at+2],map[at+1],map[at]};assert(fwrite(rgb,1,3,out)==3);
    }
    assert(!fclose(out));
}
static void rendering(unsigned width,unsigned height,const char *preview)
{
    dimensions(width,height);sessions_init();reset_touch();geometry_and_keys();
    sessions[0].pty_index=4;sessions[1].pty_index=5;
    clock_format(1577836800L+14*3600+32*60);assert(!strcmp(clock_text,"14:32 UTC"));
    text_copy(network_text,sizeof(network_text),"wlan0 192.168.1.141");
    feed("burak-alpine # uname -r\r\n3.18.140-SIMPLE-KERNEL_V1.0\r\nburak-alpine # ls\r\nbin  etc  home  lib  proc  sys\r\nburak-alpine # ");
    struct fb_var_screeninfo v={0};struct fb_fix_screeninfo f={0};
    v.xres=v.xres_virtual=width;v.yres=v.yres_virtual=height;v.bits_per_pixel=32;
    v.red=(struct fb_bitfield){16,8,0};v.green=(struct fb_bitfield){8,8,0};v.blue=(struct fb_bitfield){0,8,0};v.transp=(struct fb_bitfield){24,8,0};
    f.type=FB_TYPE_PACKED_PIXELS;f.visual=FB_VISUAL_TRUECOLOR;f.line_length=width*4+16;f.smem_len=f.line_length*height;
    unsigned char *map=malloc(f.smem_len+64);assert(map);memset(map,0xa5,f.smem_len+64);render(map,&v,&f,1);
    for(unsigned i=0;i<64;i++)assert(map[f.smem_len+i]==0xa5);
    for(unsigned y=0;y<height;y++)for(unsigned x=width*4;x<f.line_length;x++)assert(map[y*f.line_length+x]==0xa5);
    unsigned char *before=malloc(f.smem_len);assert(before);memcpy(before,map,f.smem_len);
    writes=outside_cursor_writes=0;trace_blink=1;render(map,&v,&f,0);trace_blink=0;
    assert(writes>0 && writes<cell_w*cell_h*2 && outside_cursor_writes==0);
    unsigned first=header_h+cy*cell_h,last=first+cell_h;
    for(unsigned y=0;y<height;y++)for(unsigned x=0;x<f.line_length;x++)
        if(y<first || y>=last || x<cx*cell_w*4 || x>=(cx+1)*cell_w*4)assert(before[y*f.line_length+x]==map[y*f.line_length+x]);
    free(before);
    if(preview)save_ppm(preview,map,&f);
    trace_keyboard=1;keyboard_writes=0;activate_session(1);feed("Independent terminal session two\r\n# ");render(map,&v,&f,1);
    trace_keyboard=0;assert(!keyboard_writes); /* Switching must preserve the keyboard. */
    for(unsigned i=0;i<rows+8;i++)feed("Previous output in terminal two\r\n");scroll_lines(5);render(map,&v,&f,1);assert(!painted_cursor_visible);
    if(preview)save_ppm("build/terminal-scroll-preview.ppm",map,&f);
    power_checks();power_menu=1;power_test_mode=1;power_menu_painted=0;render(map,&v,&f,1);
    if(preview)save_ppm("build/power-menu-preview.ppm",map,&f);
    power_menu=0;power_menu_painted=0;painted_once=0;
    for(unsigned i=0;i<64;i++)assert(map[f.smem_len+i]==0xa5);
    free(map);
}
int main(int argc,char **argv)
{
    parser_history_sessions();touch_and_gestures();
    rendering(320,480,0);rendering(720,1280,argc==2?argv[1]:0);
    clock_format(0);assert(!strcmp(clock_text,"CLOCK UNSET"));
    puts("PASS: independent terminal state, bounded scrollback, swipe/scroll gestures, long-press keys, complete ASCII layout, power menu and partial framebuffer painting");return 0;
}
