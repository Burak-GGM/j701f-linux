/* Small RAM-only framebuffer terminal and single-finger touchscreen keyboard.
 * Reuse the tested framebuffer bounds, font, pixel packing and scanout quirk.
 * No libc, Android UI libraries, storage mounts, or vendor input ioctls.
 */
#define FB_HEARTBEAT_TEST
#include "fb-heartbeat.c"
#include <linux/input.h>
#include <linux/reboot.h>
#include <linux/if.h>
#include <linux/sockios.h>
#include <asm-generic/ioctls.h>
#include <asm-generic/termbits.h>

enum { MAX_COLS=120, MAX_ROWS=80, MAX_SLOTS=32, MAX_SESSIONS=3, HISTORY_LINES=512 };
struct terminal_session {
    unsigned char grid[MAX_ROWS][MAX_COLS], history[HISTORY_LINES][MAX_COLS];
    unsigned x,y,stored_x,stored_y,history_head,history_count,scroll;
    int escape,args[8],arg_index;
    long master,pid;
    unsigned pty_index;
};
static struct terminal_session sessions[MAX_SESSIONS];
static unsigned active_session,cols,rows;
#define cells sessions[active_session].grid
#define cx sessions[active_session].x
#define cy sessions[active_session].y
#define saved_x sessions[active_session].stored_x
#define saved_y sessions[active_session].stored_y
#define escape_state sessions[active_session].escape
#define arguments sessions[active_session].args
#define argument_index sessions[active_session].arg_index
static int shifted,symbols,control_key,alt_key;
static unsigned length(const char *s){unsigned n=0;while(s[n])n++;return n;}
static int equal_string(const char *a,const char *b){while(*a && *a==*b){a++;b++;}return *a==*b;}
static void decimal(char *out,unsigned value){char reverse[12];unsigned n=0;do{reverse[n++]='0'+value%10;value/=10;}while(value);for(unsigned i=0;i<n;i++)out[i]=reverse[n-1-i];out[n]=0;}
static void text_copy(char *out,unsigned capacity,const char *s){unsigned i=0;while(i+1<capacity && s[i]){out[i]=s[i];i++;}out[i]=0;}
static void text_append(char *out,unsigned capacity,const char *s){unsigned i=length(out),j=0;while(i+1<capacity && s[j])out[i++]=s[j++];out[i]=0;}
static void number_append(char *out,unsigned capacity,unsigned value){char n[12];decimal(n,value);text_append(out,capacity,n);}
static char clock_text[24]="CLOCK UNSET",network_text[64]="OFFLINE";
static char painted_clock[24],painted_network[64],painted_session_text[48],painted_scroll_text[32];
static int painted_session=-1;
static void clock_format(long seconds)
{
    if(seconds<1577836800L){text_copy(clock_text,sizeof(clock_text),"CLOCK UNSET");return;}
    unsigned minute=(unsigned)((seconds/60)%1440);
    clock_text[0]='0'+minute/60/10;clock_text[1]='0'+minute/60%10;clock_text[2]=':';
    clock_text[3]='0'+minute%60/10;clock_text[4]='0'+minute%60%10;
    text_copy(clock_text+5,sizeof(clock_text)-5," UTC");
}
static unsigned scale, cell_w, cell_h, header_h, keyboard_y, keyboard_h;
static unsigned screen_w, screen_h;
static int highlighted_row=-1, highlighted_col=-1;
static unsigned char painted_cells[MAX_ROWS][MAX_COLS];
static int painted_once, painted_cursor_visible;
static unsigned painted_cursor_x,painted_cursor_y;
static int painted_shift,painted_symbols,painted_control,painted_alt,painted_key_row=-1,painted_key_col=-1;
enum { POWER_NONE, POWER_OFF, POWER_DOWNLOAD, POWER_SYSTEM, POWER_CANCEL };
static int power_held,power_triggered,power_menu,power_menu_painted,power_action;
static long power_started;
static int power_test_mode;
static int power_selected;

static void power_event(const struct input_event *event,long now)
{
    if(event->type==EV_SYN && event->code==SYN_DROPPED){power_held=power_triggered=0;return;}
    if(event->type!=EV_KEY || event->code!=KEY_POWER)return;
    if(event->value==1 && !power_held){power_held=1;power_triggered=0;power_started=now;}
    if(event->value==0){power_held=power_triggered=0;}
}

static int power_tick(long now)
{
    if(!power_held || power_triggered || now-power_started<1200)return 0;
    power_triggered=1;power_menu=!power_menu;power_menu_painted=0;painted_once=0;power_selected=POWER_NONE;
    return 1;
}

static int menu_hit(unsigned x,unsigned y)
{
    unsigned left=screen_w/10,width=screen_w*8/10,top=screen_h/5,height=screen_h*3/5;
    unsigned header=height/6;
    if(x<left || x>=left+width || y<top+header || y>=top+height)return POWER_NONE;
    unsigned row=(y-top-header)*4/(height-header);
    return row<4?(int)row+POWER_OFF:POWER_NONE;
}

/* A dry run never produces a reboot request. Only these three destinations
 * are allowed; no shell command, partition write, or invented reboot address. */
static int power_plan(int action,int dry_run,unsigned *command,const char **argument)
{
    *argument=0;
    if(dry_run)return 0;
    switch(action){
    case POWER_OFF:*command=LINUX_REBOOT_CMD_POWER_OFF;return 1;
    case POWER_DOWNLOAD:*command=LINUX_REBOOT_CMD_RESTART2;*argument="download";return 1;
    case POWER_SYSTEM:*command=LINUX_REBOOT_CMD_RESTART;return 1;
    default:return 0;
    }
}

static void clear_cells(void)
{
    for (unsigned y=0; y<MAX_ROWS; y++) for (unsigned x=0; x<MAX_COLS; x++) cells[y][x]=' ';
    cx=cy=0;
}

static void sessions_init(void)
{
    for(unsigned i=0;i<MAX_SESSIONS;i++){
        volatile unsigned char *p=(volatile unsigned char *)&sessions[i];
        for(usize n=0;n<sizeof(sessions[i]);n++)p[n]=0;
        sessions[i].master=-1;sessions[i].pty_index=~0U;
        active_session=i;clear_cells();
    }
    active_session=0;painted_once=0;painted_session=-1;
}

static void activate_session(unsigned index)
{
    if(index>=MAX_SESSIONS || index==active_session)return;
    active_session=index;shifted=control_key=alt_key=0;
    highlighted_row=highlighted_col=-1;
}

static void scroll_lines(int delta)
{
    struct terminal_session *t=&sessions[active_session];
    long value=(long)t->scroll+delta;
    t->scroll=value<0?0:value>(long)t->history_count?t->history_count:(unsigned)value;
}

static unsigned char visible_cell(unsigned y,unsigned x)
{
    struct terminal_session *t=&sessions[active_session];
    unsigned line=t->history_count-t->scroll+y;
    return line<t->history_count?t->history[(t->history_head+line)%HISTORY_LINES][x]:t->grid[line-t->history_count][x];
}

static void newline(void)
{
    if (++cy < rows) return;
    struct terminal_session *t=&sessions[active_session];
    unsigned at=(t->history_head+t->history_count)%HISTORY_LINES;
    for(unsigned x=0;x<cols;x++)t->history[at][x]=cells[0][x];
    if(t->history_count<HISTORY_LINES)t->history_count++;
    else t->history_head=(t->history_head+1)%HISTORY_LINES;
    if(t->scroll && t->scroll<t->history_count)t->scroll++;
    for (unsigned y=1; y<rows; y++) for (unsigned x=0; x<cols; x++) cells[y-1][x]=cells[y][x];
    for (unsigned x=0; x<cols; x++) cells[rows-1][x]=' ';
    cy=rows-1;
}

static unsigned bounded(int v, unsigned limit) { return v<0 ? 0 : (unsigned)v>=limit ? limit-1 : (unsigned)v; }

static void csi(unsigned char command)
{
    int n=arguments[0] ? arguments[0] : 1;
    switch (command) {
    case 'A': cy=bounded((int)cy-n, rows); break;
    case 'B': cy=bounded((int)cy+n, rows); break;
    case 'C': cx=bounded((int)cx+n, cols); break;
    case 'D': cx=bounded((int)cx-n, cols); break;
    case 'G': cx=bounded(n-1,cols); break;
    case 'd': cy=bounded(n-1,rows); break;
    case 'H': case 'f': cy=bounded(n-1,rows); cx=bounded((arguments[1]?arguments[1]:1)-1,cols); break;
    case 's': saved_x=cx; saved_y=cy; break;
    case 'u': cx=bounded(saved_x,cols); cy=bounded(saved_y,rows); break;
    case 'J':
        if (arguments[0]==2 || arguments[0]==3) {
            if(arguments[0]==3){sessions[active_session].history_head=sessions[active_session].history_count=sessions[active_session].scroll=0;}
            unsigned old_x=cx,old_y=cy; clear_cells(); cx=old_x; cy=old_y;
        } else for (unsigned y=0;y<rows;y++) for(unsigned x=0;x<cols;x++) {
            unsigned at=y*cols+x, cursor=cy*cols+cx;
            if ((arguments[0]==0 && at>=cursor) || (arguments[0]==1 && at<=cursor)) cells[y][x]=' ';
        }
        break;
    case 'K': for(unsigned x=0;x<cols;x++)
        if(arguments[0]==2 || (arguments[0]==0 && x>=cx) || (arguments[0]==1 && x<=cx)) cells[cy][x]=' ';
        break;
    default: break; /* SGR and unsupported modes are ignored, never printed. */
    }
}

static void terminal_byte(unsigned char b)
{
    if (escape_state==3) { /* OSC title: consume through BEL or ST. */
        if(b==7) escape_state=0; else if(b==27) escape_state=4;
        return;
    }
    if(escape_state==4) { escape_state=b=='\\' ? 0 : 3; return; }
    if(escape_state==1) {
        if(b=='[') { escape_state=2; argument_index=0; for(unsigned i=0;i<8;i++) arguments[i]=0; }
        else if(b==']') escape_state=3;
        else { escape_state=0; if(b=='7'){saved_x=cx;saved_y=cy;} if(b=='8'){cx=bounded(saved_x,cols);cy=bounded(saved_y,rows);} }
        return;
    }
    if(escape_state==2) {
        if(b>='0' && b<='9') { if(arguments[argument_index]<1000) arguments[argument_index]=arguments[argument_index]*10+b-'0'; }
        else if(b==';') { if(argument_index<7) argument_index++; }
        else if(b>=0x40 && b<=0x7e) { csi(b); escape_state=0; }
        return;
    }
    if(b==27){escape_state=1;return;}
    if(b=='\r'){cx=0;return;}
    if(b=='\n'){newline();return;}
    if(b==8){if(cx)cx--;return;}
    if(b=='\t'){unsigned stop=(cx/8+1)*8;while(cx<stop && cx<cols)cells[cy][cx++]=' ';return;}
    if(b<32 || b==127)return;
    if(cx>=cols){cx=0;newline();}
    cells[cy][cx++]=b<127 ? b : '?';
}

static const unsigned char lower[26][7]={
    {0,0,14,1,15,17,15},{16,16,30,17,17,17,30},{0,0,15,16,16,16,15},
    {1,1,15,17,17,17,15},{0,0,14,17,31,16,14},{6,8,28,8,8,8,8},
    {0,15,17,17,15,1,14},{16,16,30,17,17,17,17},{4,0,12,4,4,4,14},
    {2,0,6,2,2,18,12},{16,16,18,20,24,20,18},{12,4,4,4,4,4,14},
    {0,0,26,21,21,21,21},{0,0,30,17,17,17,17},{0,0,14,17,17,17,14},
    {0,30,17,17,30,16,16},{0,15,17,17,15,1,1},{0,0,22,24,16,16,16},
    {0,0,15,16,14,1,30},{8,8,28,8,8,9,6},{0,0,17,17,17,19,13},
    {0,0,17,17,17,10,4},{0,0,17,17,21,21,10},{0,0,17,10,4,10,17},
    {0,17,17,17,15,1,14},{0,0,31,2,4,8,31}
};
static const unsigned char digits[10][7]={
    {14,17,19,21,25,17,14},{4,12,4,4,4,4,14},{14,17,1,2,4,8,31},
    {30,1,1,14,1,1,30},{2,6,10,18,31,2,2},{31,16,16,30,1,1,30},
    {14,16,16,30,17,17,14},{31,1,2,4,8,8,8},{14,17,17,14,17,17,14},
    {14,17,17,15,1,1,14}
};

static void glyph(unsigned char c,unsigned char g[7])
{
    const unsigned char *source=0;
    if(c>='A' && c<='Z')source=alphabet[c-'A'];
    if(c>='a' && c<='z')source=lower[c-'a'];
    if(c>='0' && c<='9')source=digits[c-'0'];
    for(unsigned i=0;i<7;i++)g[i]=source?source[i]:0;
    if(source)return;
    switch(c){
    case ' ':break;
    case '.':g[6]=4;break;case ',':g[5]=4;g[6]=8;break;
    case ':':g[2]=4;g[5]=4;break;case ';':g[2]=4;g[5]=4;g[6]=8;break;
    case '/':for(unsigned i=0;i<7;i++)g[i]=1U<<(i*4/6);break;
    case '\\':for(unsigned i=0;i<7;i++)g[i]=16U>>(i*4/6);break;
    case '-':g[3]=31;break;case '_':g[6]=31;break;case '=':g[2]=g[4]=31;break;
    case '+':g[1]=g[2]=g[4]=g[5]=4;g[3]=31;break;
    case '|':for(unsigned i=0;i<7;i++)g[i]=4;break;
    case '[':g[0]=g[6]=14;for(unsigned i=1;i<6;i++)g[i]=8;break;
    case ']':g[0]=g[6]=14;for(unsigned i=1;i<6;i++)g[i]=2;break;
    case '(':case '{':g[0]=g[6]=2;g[1]=g[5]=4;g[2]=g[3]=g[4]=8;break;
    case ')':case '}':g[0]=g[6]=8;g[1]=g[5]=4;g[2]=g[3]=g[4]=2;break;
    case '<':g[1]=2;g[2]=4;g[3]=8;g[4]=4;g[5]=2;break;
    case '>':g[1]=8;g[2]=4;g[3]=2;g[4]=4;g[5]=8;break;
    case '\'':case '`':g[0]=g[1]=4;break;case '"':g[0]=g[1]=10;break;
    case '!':g[0]=g[1]=g[2]=g[3]=4;g[5]=4;break;
    case '?':g[0]=14;g[1]=17;g[2]=2;g[3]=4;g[5]=4;break;
    case '#':g[1]=g[3]=31;g[0]=g[2]=g[4]=g[5]=10;break;
    case '$':g[0]=4;g[1]=15;g[2]=20;g[3]=14;g[4]=5;g[5]=30;g[6]=4;break;
    case '%':g[0]=g[1]=25;g[2]=2;g[3]=4;g[4]=8;g[5]=g[6]=19;break;
    case '&':g[0]=12;g[1]=18;g[2]=20;g[3]=8;g[4]=21;g[5]=18;g[6]=13;break;
    case '*':g[1]=21;g[2]=14;g[3]=31;g[4]=14;g[5]=21;break;
    case '^':g[0]=4;g[1]=10;g[2]=17;break;
    case '~':g[2]=13;g[3]=22;break;
    case '@':g[0]=14;g[1]=17;g[2]=23;g[3]=21;g[4]=23;g[5]=16;g[6]=14;break;
    default:g[0]=g[6]=31;g[1]=g[5]=17;g[2]=g[3]=g[4]=4;break;
    }
}

static void dimensions(unsigned w,unsigned h)
{
    screen_w=w;screen_h=h;scale=w>=600?3:2;cell_w=6*scale;cell_h=9*scale;
    header_h=2*cell_h+12;keyboard_y=h*3/5;keyboard_h=h-keyboard_y;
    cols=w/cell_w;if(cols>MAX_COLS)cols=MAX_COLS;
    rows=(keyboard_y-header_h)/cell_h;if(rows>MAX_ROWS)rows=MAX_ROWS;
}

/* Staggered QWERTY layout. The shortcut strip replaces the image's toolbar. */
static const char *normal_keys[3]={"qwertyuiop","asdfghjkl","zxcvbnm"};
static const char *key_hints[3]={"1234567890","@#$%&-+()","*\"':;!?"};
static const char *symbol_keys[2][3]={
    {"1234567890","@#$%&-+()","*\"':;!?"},
    {"!@#$%^&*()","[]{}<>\\|~","=+/_`:$"}
};
static unsigned key_count(unsigned row){static const unsigned counts[5]={8,10,9,9,5};return row<5?counts[row]:0;}
struct key_rect {unsigned x,y,w,h;};
static struct key_rect key_geometry(unsigned row,unsigned col)
{
    struct key_rect r={0};if(col>=key_count(row))return r;
    unsigned shortcut_h=keyboard_h/8,start=0,end=0;
    if(row==0){r.x=col*screen_w/8;r.w=(col+1)*screen_w/8-r.x;r.y=keyboard_y;r.h=shortcut_h;}
    else{
        if(row==1){start=col*2;end=start+2;}
        if(row==2){start=1+col*2;end=start+2;}
        if(row==3){start=col==0?0:col==8?17:3+(col-1)*2;end=col==0?3:col==8?20:start+2;}
        if(row==4){static const unsigned edges[6]={0,3,5,14,16,20};start=edges[col];end=edges[col+1];}
        r.x=start*screen_w/20;r.w=end*screen_w/20-r.x;
        r.y=keyboard_y+shortcut_h+(row-1)*(keyboard_h-shortcut_h)/4;
        r.h=keyboard_y+shortcut_h+row*(keyboard_h-shortcut_h)/4-r.y;
    }
    unsigned gap=screen_w>=600?4:2;r.x+=gap;r.y+=gap;r.w-=2*gap;r.h-=2*gap;return r;
}
static int key_hit(unsigned x,unsigned y,unsigned *row,unsigned *col)
{
    for(unsigned r=0;r<5;r++)for(unsigned c=0;c<key_count(r);c++){
        struct key_rect k=key_geometry(r,c);
        if(x>=k.x && x<k.x+k.w && y>=k.y && y<k.y+k.h){*row=r;*col=c;return 1;}
    }
    return 0;
}
static char key_character(unsigned row,unsigned col,int secondary)
{
    unsigned line=row-1,index=col;
    if(row==3){if(col==0 || col==8)return 0;index=col-1;}
    if(row<1 || row>3 || col>=key_count(row))return 0;
    char c=secondary&&!symbols?key_hints[line][index]:(symbols?symbol_keys[shifted!=0][line][index]:normal_keys[line][index]);
    if(shifted && !symbols && !secondary && c>='a' && c<='z')c-='a'-'A';
    return c;
}
static const char *key_label(unsigned row,unsigned col,char one[2])
{
    static const char *shortcuts[8]={"ESC","CTRL","ALT","TAB","LEFT","DOWN","UP","RIGHT"};
    if(row==0)return shortcuts[col];
    if(row==3 && col==0)return symbols?"1/2":"SHIFT";
    if(row==3 && col==8)return "BS";
    if(row==4){static const char *bottom[5]={"?123",",","SPACE",".","ENTER"};return col==0&&symbols?"ABC":bottom[col];}
    one[0]=key_character(row,col,0);one[1]=0;return one;
}
static unsigned modified_key(char out[4],unsigned n)
{
    if(control_key && n==1){unsigned char c=out[0];if(c>='a' && c<='z')c-='a'-'A';if(c>='@' && c<='_')out[0]=c&31;else if(c==' ')out[0]=0;}
    if(alt_key && n<4){for(unsigned i=n;i>0;i--)out[i]=out[i-1];out[0]=27;n++;}
    control_key=alt_key=0;
    if(!symbols)shifted=0;
    sessions[active_session].scroll=0;return n;
}
static unsigned key_bytes(unsigned row,unsigned col,char out[4])
{
    if(col>=key_count(row))return 0;
    if(row==0){
        if(col==1){control_key=!control_key;return 0;}
        if(col==2){alt_key=!alt_key;return 0;}
        if(col==0 || col==3){out[0]=col==0?27:'\t';return modified_key(out,1);}
        out[0]=27;out[1]='[';out[2]="DBAC"[col-4];return modified_key(out,3);
    }
    if(row==3 && col==0){shifted=!shifted;return 0;}
    if(row==3 && col==8){out[0]=127;return modified_key(out,1);}
    if(row==4){if(col==0){symbols=!symbols;shifted=0;return 0;}out[0]=col==1?',':col==2?' ':col==3?'.':'\r';return modified_key(out,1);}
    out[0]=key_character(row,col,0);return modified_key(out,1);
}

struct touch_slot { int active,x,y,has_x,has_y; };
static struct touch_slot contacts[MAX_SLOTS];
static int selected_slot, touch_pressed, dropped;
static struct input_absinfo touch_x,touch_y;

static int touch_position(int value,const struct input_absinfo *axis,unsigned extent)
{
    long v=value;if(v<axis->minimum)v=axis->minimum;if(v>axis->maximum)v=axis->maximum;
    return (v-axis->minimum)*(extent-1)/(axis->maximum-axis->minimum);
}

enum { GESTURE_NONE,GESTURE_KEY,GESTURE_TERMINAL,GESTURE_SCROLL,GESTURE_SWIPE,GESTURE_HEADER,GESTURE_MENU };
static int gesture,gesture_slot=-1,gesture_cancelled,gesture_sent;
static unsigned gesture_row,gesture_col,gesture_scroll;
static int gesture_x,gesture_y,gesture_last_x,gesture_last_y;
static long input_now,gesture_started;
static int magnitude(int v){return v<0?-v:v;}
static void cancel_touch(void){gesture=GESTURE_NONE;gesture_cancelled=1;highlighted_row=highlighted_col=-1;}

/* Long-press hints and tap release are mutually exclusive. */
static unsigned input_tick(long now,char out[4])
{
    if(gesture!=GESTURE_KEY || gesture_cancelled || gesture_sent || symbols || now-gesture_started<450)return 0;
    char c=key_character(gesture_row,gesture_col,1);if(!c)return 0;
    gesture_sent=1;out[0]=c;return modified_key(out,1);
}
static void move_touch(int x,int y)
{
    gesture_last_x=x;gesture_last_y=y;
    int dx=x-gesture_x,dy=y-gesture_y;
    if(gesture==GESTURE_KEY){
        unsigned row,col;
        if(!key_hit(x,y,&row,&col) || row!=gesture_row || col!=gesture_col || magnitude(dx)>(int)screen_w/20 || magnitude(dy)>(int)screen_w/20)cancel_touch();
    }
    if(gesture==GESTURE_TERMINAL){
        if(magnitude(dx)>(int)screen_w/7 && magnitude(dx)>2*magnitude(dy))gesture=GESTURE_SWIPE;
        else if(magnitude(dy)>=(int)cell_h && magnitude(dy)>2*magnitude(dx))gesture=GESTURE_SCROLL;
    }
    if(gesture==GESTURE_SCROLL){sessions[active_session].scroll=gesture_scroll;scroll_lines(dy/(int)cell_h);}
}
static unsigned finish_touch(char out[4])
{
    unsigned n=0;
    if(!gesture_cancelled){
        if(gesture==GESTURE_KEY && !gesture_sent){n=input_tick(input_now,out);if(!gesture_sent)n=key_bytes(gesture_row,gesture_col,out);}
        if(gesture==GESTURE_SWIPE){int dx=gesture_last_x-gesture_x;
            activate_session((active_session+(dx>0?1:MAX_SESSIONS-1))%MAX_SESSIONS);}
        if(gesture==GESTURE_HEADER)sessions[active_session].scroll=0;
        if(gesture==GESTURE_MENU){int action=menu_hit(gesture_last_x,gesture_last_y);
            if(action==(int)gesture_row && action==POWER_CANCEL){power_menu=0;power_menu_painted=0;painted_once=0;}
            else if(action==(int)gesture_row && action!=POWER_NONE)power_action=action;
        }
    }
    gesture=GESTURE_NONE;gesture_slot=-1;touch_pressed=0;gesture_cancelled=gesture_sent=0;
    highlighted_row=highlighted_col=-1;return n;
}
static unsigned input_event_bytes(const struct input_event *event,char out[4])
{
    if(event->type==EV_SYN && event->code==SYN_DROPPED){
        dropped=1;cancel_touch();touch_pressed=1;
        for(unsigned i=0;i<MAX_SLOTS;i++)contacts[i]=(struct touch_slot){0};return 0;
    }
    if(dropped){if(event->type==EV_SYN && event->code==SYN_REPORT)dropped=0;return 0;}
    if(event->type==EV_ABS && event->code==ABS_MT_SLOT){selected_slot=event->value;return 0;}
    if(event->type==EV_ABS && selected_slot>=0 && selected_slot<MAX_SLOTS){
        struct touch_slot *slot=&contacts[selected_slot];
        if(event->code==ABS_MT_TRACKING_ID)slot->active=event->value>=0;
        if(event->code==ABS_MT_POSITION_X){slot->x=event->value;slot->has_x=1;}
        if(event->code==ABS_MT_POSITION_Y){slot->y=event->value;slot->has_y=1;}
    }
    if(event->type!=EV_SYN || event->code!=SYN_REPORT)return 0;
    int finger_index=-1;unsigned count=0;
    for(unsigned i=0;i<MAX_SLOTS;i++)if(contacts[i].active){finger_index=i;count++;}
    if(!count){
        /* A final motion and release can arrive in the same frame. */
        if(touch_pressed && gesture_slot>=0 && gesture_slot<MAX_SLOTS && !gesture_cancelled){
            struct touch_slot *last=&contacts[gesture_slot];
            if(last->has_x && last->has_y)move_touch(touch_position(last->x,&touch_x,screen_w),touch_position(last->y,&touch_y,screen_h));
        }
        return finish_touch(out);
    }
    if(count!=1 || (touch_pressed && gesture_slot!=finger_index)){cancel_touch();touch_pressed=1;return 0;}
    struct touch_slot *finger=&contacts[finger_index];
    if(!finger->has_x || !finger->has_y || gesture_cancelled)return 0;
    int x=touch_position(finger->x,&touch_x,screen_w),y=touch_position(finger->y,&touch_y,screen_h);
    if(!touch_pressed){
        touch_pressed=1;gesture_slot=finger_index;gesture_x=gesture_last_x=x;gesture_y=gesture_last_y=y;
        gesture_started=input_now;gesture_sent=0;gesture_scroll=sessions[active_session].scroll;
        if(power_menu){gesture=GESTURE_MENU;gesture_row=menu_hit(x,y);}
        else if(y<(int)header_h)gesture=GESTURE_HEADER;
        else if(y<(int)keyboard_y)gesture=GESTURE_TERMINAL;
        else if(key_hit(x,y,&gesture_row,&gesture_col)){gesture=GESTURE_KEY;highlighted_row=gesture_row;highlighted_col=gesture_col;}
        else cancel_touch();
        return 0;
    }
    move_touch(x,y);
    return 0;
}

static void rectangle(unsigned char *map,const struct fb_var_screeninfo *v,const struct fb_fix_screeninfo *f,
                      unsigned x,unsigned y,unsigned w,unsigned h,unsigned c)
{
    for(unsigned yy=y;yy<y+h && yy<v->yres;yy++)for(unsigned xx=x;xx<x+w && xx<v->xres;xx++)pixel(map,v,f,xx,yy,c);
}

static void label(unsigned char *map,const struct fb_var_screeninfo *v,const struct fb_fix_screeninfo *f,
                  const char *s,unsigned x,unsigned y,unsigned size,unsigned c)
{
    for(;*s;s++,x+=6*size){unsigned char g[7];glyph(*s,g);
        for(unsigned r=0;r<7;r++)for(unsigned bit=0;bit<5;bit++)if(g[r]&(16>>bit))
            rectangle(map,v,f,x+bit*size,y+r*size,size,size,c);
    }
}

static void rounded_key(unsigned char *map,const struct fb_var_screeninfo *v,const struct fb_fix_screeninfo *f,
                        struct key_rect k,unsigned fill)
{
    unsigned radius=screen_w>=600?10:5;
    for(unsigned y=0;y<k.h;y++){
        unsigned inset=0;
        if(y<radius || k.h-1-y<radius){unsigned edge=y<radius?y:k.h-1-y;
            unsigned d=radius-edge;while(inset<radius && (radius-inset)*(radius-inset)+d*d>radius*radius)inset++;
        }
        rectangle(map,v,f,k.x+inset,k.y+y,k.w-2*inset,1,fill);
    }
}
static void render(unsigned char *map,const struct fb_var_screeninfo *v,const struct fb_fix_screeninfo *f,int cursor_visible)
{
    unsigned bg=color(v,24,25,27),white=color(v,237,239,241),green=color(v,76,175,80),muted=color(v,154,158,163);
    if(power_menu){
        if(power_menu_painted)return;
        rectangle(map,v,f,0,0,v->xres,v->yres,bg);
        unsigned x=screen_w/10,w=screen_w*8/10,top=screen_h/5,h=screen_h*3/5,header=h/6;
        label(map,v,f,"POWER MENU",x+12,top+12,scale,white);
        static const char *options[4]={"POWER OFF","DOWNLOAD MODE","REBOOT SYSTEM","CANCEL"};
        for(unsigned i=0;i<4;i++){
            unsigned y=top+header+i*(h-header)/4,end=top+header+(i+1)*(h-header)/4;
            rectangle(map,v,f,x+2,y+2,w-4,end-y-4,i==3 || power_selected==(int)i+1?color(v,0,80,55):color(v,48,50,54));
            label(map,v,f,options[i],x+12,y+(end-y-7*scale)/2,scale,white);
        }
        if(power_test_mode)label(map,v,f,"TEST MODE: NO REBOOT",x,top+h+12,2,green);
        power_menu_painted=1;return;
    }
    if(!painted_once)rectangle(map,v,f,0,0,v->xres,v->yres,bg);
    char tty[48]="T",scroll[32]="";
    number_append(tty,sizeof(tty),active_session+1);text_append(tty,sizeof(tty),screen_w>=600?" /dev/pts/":" pts/");
    if(sessions[active_session].pty_index==~0U)text_append(tty,sizeof(tty),"-");else number_append(tty,sizeof(tty),sessions[active_session].pty_index);
    if(sessions[active_session].scroll){text_copy(scroll,sizeof(scroll),"SCROLL ");number_append(scroll,sizeof(scroll),sessions[active_session].scroll);text_append(scroll,sizeof(scroll)," / LIVE");}
    unsigned small=screen_w>=600?2:1,top_size=screen_w>=600?3:2;
    if(!painted_once || !equal_string(clock_text,painted_clock) || !equal_string(tty,painted_session_text) ||
       !equal_string(network_text,painted_network) || !equal_string(scroll,painted_scroll_text)){
        rectangle(map,v,f,0,0,screen_w,header_h,color(v,34,36,40));
        label(map,v,f,clock_text,8,9,top_size,white);
        label(map,v,f,tty,screen_w-length(tty)*6*top_size-8,9,top_size,white);
        label(map,v,f,network_text,8,header_h/2+3,small,equal_string(network_text,"OFFLINE")?muted:green);
        label(map,v,f,scroll,screen_w-length(scroll)*6*small-8,header_h/2+3,small,muted);
        text_copy(painted_clock,sizeof(painted_clock),clock_text);text_copy(painted_network,sizeof(painted_network),network_text);
        text_copy(painted_session_text,sizeof(painted_session_text),tty);text_copy(painted_scroll_text,sizeof(painted_scroll_text),scroll);
    }
    cursor_visible=cursor_visible && !sessions[active_session].scroll;
    unsigned cursor_x=bounded(cx,cols);
    for(unsigned y=0;y<rows;y++)for(unsigned x=0;x<cols;x++){
        int old_cursor=painted_cursor_visible && x==painted_cursor_x && y==painted_cursor_y;
        int new_cursor=cursor_visible && x==cursor_x && y==cy;
        unsigned char value=visible_cell(y,x);
        if(painted_once && painted_session==(int)active_session && painted_cells[y][x]==value && !old_cursor && !new_cursor)continue;
        rectangle(map,v,f,x*cell_w,header_h+y*cell_h,cell_w,cell_h,bg);
        char one[2]={value,0};label(map,v,f,one,x*cell_w,header_h+y*cell_h,scale,white);painted_cells[y][x]=value;
    }
    if(cursor_visible)rectangle(map,v,f,cursor_x*cell_w,header_h+cy*cell_h+7*scale,5*scale,2,green);
    int modes_changed=painted_shift!=shifted || painted_symbols!=symbols || painted_control!=control_key || painted_alt!=alt_key;
    for(unsigned row=0;row<5;row++)for(unsigned col=0;col<key_count(row);col++){
        int selected=highlighted_row==(int)row && highlighted_col==(int)col;
        int was_selected=painted_key_row==(int)row && painted_key_col==(int)col;
        int selection_changed=painted_key_row!=highlighted_row || painted_key_col!=highlighted_col;
        if(painted_once && !modes_changed && !(selection_changed && (selected || was_selected)))continue;
        struct key_rect k=key_geometry(row,col);
        int modifier=(row==0 && ((col==1 && control_key)||(col==2 && alt_key))) || (row==3 && col==0 && shifted);
        unsigned fill=selected||modifier?color(v,60,116,78):row==4&&col==4?green:row==0?color(v,45,47,51):color(v,65,67,71);
        rounded_key(map,v,f,k,fill);
        char one[2];const char *text=key_label(row,col,one);
        unsigned size=key_character(row,col,0)?scale+2:small;
        if(row==4 && (col==1 || col==3))size=scale+2;
        unsigned width=length(text)*6*size;
        label(map,v,f,text,k.x+(k.w>width?(k.w-width)/2:0),k.y+(k.h-7*size)/2,size,white);
        char hint=key_character(row,col,1);
        if(hint && !symbols){char h[2]={hint,0};label(map,v,f,h,k.x+k.w-6*small-5,k.y+5,small,muted);}
    }
    painted_once=1;painted_session=active_session;painted_cursor_x=cursor_x;painted_cursor_y=cy;painted_cursor_visible=cursor_visible;
    painted_shift=shifted;painted_symbols=symbols;painted_control=control_key;painted_alt=alt_key;
    painted_key_row=highlighted_row;painted_key_col=highlighted_col;
}

#ifndef TERMINAL_TEST
/* Clang may lower structure copies to this freestanding support routine. */
void *memcpy(void *destination,const void *source,usize count)
{
    volatile unsigned char *out=destination;
    const volatile unsigned char *in=source;
    for(usize i=0;i<count;i++)out[i]=in[i];return destination;
}
enum { READ=63,CLOSE=57,FCNTL=25,DUP3=24,PPOLL=73,CLOCK_GETTIME=113,KILL=129,
       SETSID=157,CLONE=220,EXECVE=221,WAIT4=260,REBOOT=142,SYNC=81,SOCKET=198,MUNMAP=215 };
struct poll_fd { int fd; short events,revents; };
static long syscall6(long n,long a,long b,long c,long d,long e,long f)
{
    register long x0 __asm__("x0")=a;register long x1 __asm__("x1")=b;register long x2 __asm__("x2")=c;
    register long x3 __asm__("x3")=d;register long x4 __asm__("x4")=e;register long x5 __asm__("x5")=f;
    register long x8 __asm__("x8")=n;
    __asm__ volatile("svc 0":"+r"(x0):"r"(x1),"r"(x2),"r"(x3),"r"(x4),"r"(x5),"r"(x8):"memory","cc");return x0;
}
static long io(long fd,long cmd,void *arg){return syscall6(A64_IOCTL,fd,cmd,(long)arg,0,0,0);}
static long open_file(const char *path,long flags){return syscall6(A64_OPENAT,-100,(long)path,flags|02000000,0,0,0);}
static void close_fd(long fd){syscall6(CLOSE,fd,0,0,0,0,0);}
static void message(const char *s){syscall6(A64_WRITE,2,(long)s,length(s),0,0,0);}
static void value_message(const char *label,long n){char b[16];message(label);if(n<0){message("-");n=-n;}decimal(b,n);message(b);message("\n");}
static long milliseconds(void){long t[2];if(syscall6(CLOCK_GETTIME,1,(long)t,0,0,0,0)<0)return 0;return t[0]*1000+t[1]/1000000;}
#define child_pid sessions[active_session].pid

static long start_shell(void)
{
    long master=open_file("/dev/ptmx",2|04000);if(master<0){message("PTY master open failed\n");return -1;}
    int unlocked=0;unsigned index;
    if(io(master,TIOCSPTLCK,&unlocked)<0 || io(master,TIOCGPTN,&index)<0){close_fd(master);message("PTY setup failed\n");return -1;}
    char path[40]="/dev/pts/";decimal(path+9,index);long slave=open_file(path,2);
    if(slave<0){close_fd(master);message("PTY slave open failed\n");return -1;}
    struct termios settings;
    if(io(slave,TCGETS,&settings)<0){close_fd(slave);close_fd(master);return -1;}
    settings.c_iflag=ICRNL|IXON;settings.c_oflag=OPOST|ONLCR;
    settings.c_lflag=ISIG|ICANON|ECHO|ECHOE|ECHOK|IEXTEN;
    settings.c_cc[VERASE]=127;settings.c_cc[VINTR]=3;settings.c_cc[VEOF]=4;settings.c_cc[VKILL]=21;
    if(io(slave,TCSETS,&settings)<0){close_fd(slave);close_fd(master);return -1;}
    struct {unsigned short row,col,x,y;} size={(unsigned short)rows,(unsigned short)cols,0,0};
    if(io(slave,TIOCSWINSZ,&size)<0){close_fd(slave);close_fd(master);return -1;}
    sessions[active_session].pty_index=index;
    child_pid=syscall6(CLONE,17,0,0,0,0,0);
    if(child_pid<0){close_fd(slave);close_fd(master);return -1;}
    if(!child_pid){
        close_fd(master);
        if(syscall6(SETSID,0,0,0,0,0,0)<0 || io(slave,TIOCSCTTY,0)<0)syscall6(A64_EXIT_GROUP,1,0,0,0,0,0);
        for(int fd=0;fd<3;fd++)if(syscall6(DUP3,slave,fd,0,0,0,0)<0)syscall6(A64_EXIT_GROUP,1,0,0,0,0,0);
        close_fd(slave);
        long marker=open_file("/etc/j701f-root",0);int alpine=marker>=0;if(alpine)close_fd(marker);
        char *argv[]={"/bin/sh","-i",0};char *env[]={"PATH=/usr/sbin:/usr/bin:/sbin:/bin",alpine?"HOME=/root":"HOME=/","TERM=vt100",alpine?"PS1=burak-alpine # ":"PS1=j701f-linux # ",0};
        syscall6(EXECVE,(long)argv[0],(long)argv,(long)env,0,0,0);syscall6(A64_EXIT_GROUP,127,0,0,0,0,0);
    }
    close_fd(slave);sessions[active_session].master=master;value_message("Interactive PTY shell PID: ",child_pid);return master;
}

static void end_shell(long master)
{
    close_fd(master);sessions[active_session].master=-1;syscall6(KILL,-child_pid,1,0,0,0,0);
    long until=milliseconds()+1000;int status;
    while(milliseconds()<until){long waited=syscall6(WAIT4,child_pid,(long)&status,1,0,0,0);if(waited==child_pid || waited==-10)return;
        const long delay[2]={0,20000000};syscall6(A64_NANOSLEEP,(long)delay,0,0,0,0,0);}
    syscall6(KILL,child_pid,9,0,0,0,0);syscall6(WAIT4,child_pid,(long)&status,0,0,0,0);
}

static int touch_monotonic_clock;
static long touch_event_time(const struct input_event *event,long now)
{
    /* Queued taps must retain their real duration, even after a slow pan.
     * Older kernels can refuse EVIOCSCLOCKID; preserve the previous timing
     * behavior in that case rather than mix realtime and monotonic clocks. */
    long stamp=event->time.tv_sec*1000+event->time.tv_usec/1000;
    return touch_monotonic_clock && stamp>0 && stamp<=now?stamp:now;
}
static long find_touch(void)
{
    for(unsigned n=0;n<64;n++){
        char path[40]="/dev/input/event";decimal(path+16,n);long fd=open_file(path,04000);if(fd<0)continue;
        struct input_absinfo slot;
        if(io(fd,EVIOCGABS(ABS_MT_POSITION_X),&touch_x)<0 || io(fd,EVIOCGABS(ABS_MT_POSITION_Y),&touch_y)<0 ||
           io(fd,EVIOCGABS(ABS_MT_SLOT),&slot)<0 || touch_x.maximum<=touch_x.minimum || touch_y.maximum<=touch_y.minimum ||
           slot.minimum!=0 || slot.maximum<0 || slot.maximum>=MAX_SLOTS){close_fd(fd);continue;}
        message("Touchscreen: ");message(path);message("\n");
        value_message("Touch X minimum: ",touch_x.minimum);value_message("Touch X maximum: ",touch_x.maximum);
        value_message("Touch Y minimum: ",touch_y.minimum);value_message("Touch Y maximum: ",touch_y.maximum);
        selected_slot=slot.value;
        int values[MAX_SLOTS+1];
        values[0]=ABS_MT_POSITION_X;
        if(io(fd,EVIOCGMTSLOTS(sizeof(values)),values)<0){close_fd(fd);continue;}
        for(int i=0;i<=slot.maximum;i++){contacts[i].x=values[i+1];contacts[i].has_x=1;}
        values[0]=ABS_MT_POSITION_Y;
        if(io(fd,EVIOCGMTSLOTS(sizeof(values)),values)<0){close_fd(fd);continue;}
        for(int i=0;i<=slot.maximum;i++){contacts[i].y=values[i+1];contacts[i].has_y=1;}
        values[0]=ABS_MT_TRACKING_ID;
        if(io(fd,EVIOCGMTSLOTS(sizeof(values)),values)<0){close_fd(fd);continue;}
        for(int i=0;i<=slot.maximum;i++){contacts[i].active=values[i+1]>=0;if(contacts[i].active)touch_pressed=1;}
        int clock_id=1;touch_monotonic_clock=io(fd,EVIOCSCLOCKID,&clock_id)>=0;
        value_message("Touch event monotonic clock: ",touch_monotonic_clock);
        return fd;
    }
    message("No supported multitouch slot device found\n");return -1;
}

static long find_power_key(void)
{
    for(unsigned n=0;n<64;n++){
        char path[40]="/dev/input/event";decimal(path+16,n);long fd=open_file(path,04000);if(fd<0)continue;
        unsigned char bits[(KEY_CNT+7)/8];for(unsigned i=0;i<sizeof(bits);i++)bits[i]=0;
        if(io(fd,EVIOCGBIT(EV_KEY,sizeof(bits)),bits)>=0 && (bits[KEY_POWER/8]&(1U<<(KEY_POWER%8)))){
            message("Power key: ");message(path);message("\n");return fd;
        }
        close_fd(fd);
    }
    message("No power key device found; terminal remains available\n");return -1;
}

static void dispatch_power(int action,int test)
{
    static const char *names[]={"none","power off","download mode","system","cancel"};
    if(action<POWER_OFF || action>POWER_SYSTEM)return;
    message(test?"TEST ONLY power selection: ":"Power selection: ");message(names[action]);message("\n");
    unsigned command=0;const char *argument=0;
    if(!power_plan(action,test,&command,&argument)){power_selected=action;power_menu_painted=0;return;}
    syscall6(SYNC,0,0,0,0,0,0);
    long result=syscall6(REBOOT,LINUX_REBOOT_MAGIC1,LINUX_REBOOT_MAGIC2,command,(long)argument,0,0);
    value_message("Reboot syscall returned: ",result);
    power_menu=0;power_menu_painted=0;painted_once=0;
    const char *error="\r\nPower action returned; inspect /tmp/display.log.\r\n";for(;*error;error++)terminal_byte(*error);
}

static int network_interface(long fd,const char *name)
{
    struct ifreq request={0};text_copy(request.ifr_name,sizeof(request.ifr_name),name);
    if(equal_string(name,"lo") || io(fd,SIOCGIFFLAGS,&request)<0 || !(request.ifr_flags&IFF_UP) || !(request.ifr_flags&IFF_RUNNING))return 0;
    text_copy(network_text,sizeof(network_text),name);
    text_append(network_text,sizeof(network_text)," NO IP");
    if(io(fd,SIOCGIFADDR,&request)<0 || request.ifr_addr.sa_family!=2)return 1;
    const unsigned char *address=(const unsigned char *)&request.ifr_addr;
    if(!(address[4]|address[5]|address[6]|address[7]))return 1;
    text_copy(network_text,sizeof(network_text),name);text_append(network_text,sizeof(network_text)," ");
    for(unsigned i=4;i<8;i++){if(i!=4)text_append(network_text,sizeof(network_text),".");number_append(network_text,sizeof(network_text),address[i]);}
    return 2;
}
static void refresh_status(int refresh_network)
{
    long time[2];clock_format(syscall6(CLOCK_GETTIME,0,(long)time,0,0,0,0)<0?0:time[0]);
    if(!refresh_network)return;
    text_copy(network_text,sizeof(network_text),"OFFLINE");
    long fd=syscall6(SOCKET,2,2|02000000,0,0,0,0);if(fd<0)return;
    int wifi=network_interface(fd,"wlan0");
    if(wifi!=2){
        char pending[64];text_copy(pending,sizeof(pending),network_text);
        struct ifreq list[16];struct ifconf config={.ifc_len=sizeof(list),.ifc_req=list};
        if(io(fd,SIOCGIFCONF,&config)>=0){
            unsigned count=config.ifc_len<0?0:(unsigned)config.ifc_len/sizeof(list[0]);if(count>16)count=16;
            int found=0;
            for(unsigned i=0;i<count;i++){list[i].ifr_name[IFNAMSIZ-1]=0;if(network_interface(fd,list[i].ifr_name)==2){found=1;break;}}
            if(!found)text_copy(network_text,sizeof(network_text),pending);
        }
    }
    close_fd(fd);
}
static long ensure_shell(void)
{
    if(sessions[active_session].master>=0)return sessions[active_session].master;
    long fd=start_shell();if(fd<0)return -1;
    escape_state=0;
    const char *welcome="\r\nShell ready. Swipe right for another terminal.\r\n";
    for(;*welcome;welcome++)terminal_byte(*welcome);
    return fd;
}
static unsigned send_input(char bytes[4],unsigned count)
{
    if(!count)return 0;
    long fd=ensure_shell();if(fd<0)return 0;
    long n=syscall6(A64_WRITE,fd,(long)bytes,count,0,0,0);
    if(n!=(long)count){message("PTY input write failed\n");return 0;}return 1;
}
static int pty_test(void)
{
    dimensions(720,1280);sessions_init();int result=0;
    for(unsigned i=0;i<MAX_SESSIONS;i++){
        active_session=i;if(start_shell()<0){result=1;break;}
        if(i && sessions[i].pty_index==sessions[i-1].pty_index){result=1;break;}
        char command[160]="SESSION_VALUE=";number_append(command,sizeof(command),i+1);
        text_append(command,sizeof(command),"; printf 'PTY-%s-%s\\n' 'SHELL-OK' \"$SESSION_VALUE\"\n");
        long fd=sessions[i].master;syscall6(A64_WRITE,fd,(long)command,length(command),0,0,0);
    }
    long until=milliseconds()+5000;char captured[MAX_SESSIONS][8192];unsigned used[MAX_SESSIONS]={0},found=0;
    while(!result && found!=(1U<<MAX_SESSIONS)-1 && milliseconds()<until){
        struct poll_fd pollers[MAX_SESSIONS];
        for(unsigned i=0;i<MAX_SESSIONS;i++)pollers[i]=(struct poll_fd){sessions[i].master,1,0};
        const long delay[2]={0,100000000};syscall6(PPOLL,(long)pollers,MAX_SESSIONS,(long)delay,0,8,0);
        for(unsigned i=0;i<MAX_SESSIONS;i++)if(pollers[i].revents&1){
            char data[1024];long n=syscall6(READ,sessions[i].master,(long)data,sizeof(data),0,0,0);if(n<=0)continue;
            syscall6(A64_WRITE,2,(long)data,n,0,0,0);
            for(long j=0;j<n && used[i]<sizeof(captured[i]);j++)captured[i][used[i]++]=data[j];
            char marker[32]="PTY-SHELL-OK-";number_append(marker,sizeof(marker),i+1);unsigned size=length(marker);
            for(unsigned at=0;at+size<=used[i];at++){unsigned j=0;while(j<size && captured[i][at+j]==marker[j])j++;if(j==size)found|=1U<<i;}
        }
    }
    if(found!=(1U<<MAX_SESSIONS)-1)result=1;
    for(unsigned i=0;i<MAX_SESSIONS;i++){active_session=i;if(sessions[i].master>=0)end_shell(sessions[i].master);}
    if(!result)message("PTY-THREE-SESSIONS-OK\n");return result;
}

static int main_terminal(int argc,char **argv)
{
    int test=argc==3 && equal_string(argv[1],"--test");
    if(argc==2 && equal_string(argv[1],"--pty-test"))return pty_test();
    if(argc==2 && equal_string(argv[1],"--status-test")){
        refresh_status(1);message("CLOCK: ");message(clock_text);message("\nNETWORK: ");message(network_text);message("\n");return 0;
    }
    if(argc!=2 && !test){message("Usage: ondevice-terminal [--test] /dev/fbN\n");return 2;}
    long framebuffer=open_file(argv[test?2:1],2);if(framebuffer<0)return 1;
    struct fb_var_screeninfo v;struct fb_fix_screeninfo f;
    if(io(framebuffer,FBIOGET_VSCREENINFO,&v)<0 || io(framebuffer,FBIOGET_FSCREENINFO,&f)<0 || !valid_layout(&v,&f))return 1;
    if(io(framebuffer,FBIOBLANK,0)<0)return 1;
    v.activate=FB_ACTIVATE_NOW|FB_ACTIVATE_FORCE;
    if(io(framebuffer,FBIOPUT_VSCREENINFO,&v)<0 || io(framebuffer,FBIOGET_VSCREENINFO,&v)<0 || io(framebuffer,FBIOGET_FSCREENINFO,&f)<0 || !valid_layout(&v,&f))return 1;
    if(v.xres<320 || v.yres<480){message("Display too small for touchscreen keyboard\n");return 1;}
    dimensions(v.xres,v.yres);sessions_init();
    long touch=find_touch();if(touch<0)return 1;
    if(test && io(touch,EVIOCGRAB,(void *)1)<0){message("Cannot isolate trial touchscreen input; temporary trial refused\n");return 1;}
    if(test)message("TEST TOUCHSCREEN INPUT ISOLATED\n");
    long power=find_power_key();power_test_mode=test;
    long address=syscall6(A64_MMAP,0,f.smem_len,3,1,framebuffer,0);
    if((unsigned long)address>=(unsigned long)-4095)return 1;
    long snapshot=0;
    if(test){
        snapshot=syscall6(A64_MMAP,0,f.smem_len,3,34,-1,0);
        if((unsigned long)snapshot>=(unsigned long)-4095){message("Cannot snapshot the display; temporary trial refused\n");return 1;}
        memcpy((void *)snapshot,(const void *)address,f.smem_len);
    }
    struct fb_var_screeninfo render_mode;
    for(usize i=0;i<sizeof(v);i++)((volatile unsigned char *)&render_mode)[i]=((unsigned char *)&v)[i];
    if(j701f_scanout_swap(&v,&f))swap_red_blue(&render_mode);
    v.activate=FB_ACTIVATE_NOW;
    if(ensure_shell()<0){if(test)syscall6(MUNMAP,snapshot,f.smem_len,0,0,0,0);return 1;}
    refresh_status(1);message("ONDEVICE TERMINAL READY\n");
    long until=test?milliseconds()+180000:0,status_at=milliseconds();unsigned key_presses=0,output_bytes=0,status_ticks=0,touch_events=0,touch_drops=0;
    int old_blink=-1,dirty=1,result=0;
    while(!test || milliseconds()<until){
        struct poll_fd pollers[MAX_SESSIONS+2];
        for(unsigned i=0;i<MAX_SESSIONS;i++)pollers[i]=(struct poll_fd){sessions[i].master,1,0};
        pollers[MAX_SESSIONS]=(struct poll_fd){touch,1,0};pollers[MAX_SESSIONS+1]=(struct poll_fd){power,1,0};
        const long delay[2]={0,50000000};long polled=syscall6(PPOLL,(long)pollers,MAX_SESSIONS+2,(long)delay,0,8,0);
        if(polled<0 && polled!=-4){result=1;break;}
        unsigned visible=active_session;
        for(unsigned i=0;i<MAX_SESSIONS;i++){
            active_session=i;
            if(pollers[i].revents&1){char buffer[4096];long n=syscall6(READ,sessions[i].master,(long)buffer,sizeof(buffer),0,0,0);
                if(n>0){for(long j=0;j<n;j++)terminal_byte(buffer[j]);output_bytes+=n;if(i==visible)dirty=1;}}
            if(pollers[i].revents&(8|16)){
                end_shell(sessions[i].master);if(ensure_shell()<0){result=1;break;}if(i==visible)dirty=1;
            }
        }
        active_session=visible;if(result)break;
        if(pollers[MAX_SESSIONS].revents&1){
            /* Drain the nonblocking evdev queue before painting. Limiting a
             * read to 32 events and then panning can delay the next release
             * behind a display update, or overflow the UI's input queue. */
            for(unsigned batch=0;batch<64;batch++){
                struct input_event events[128];long n=syscall6(READ,touch,(long)events,sizeof(events),0,0,0);
                if(n==-4)continue;
                if(n==-11)break;
                if(n<=0 || n%(long)sizeof(events[0])){message("Touchscreen read failed\n");result=1;break;}
                for(unsigned i=0;i<(unsigned)n/sizeof(events[0]);i++){
                    touch_events++;
                    if(events[i].type==EV_SYN && events[i].code==SYN_DROPPED){touch_drops++;message("Touchscreen event queue overflow; cancelling incomplete gesture\n");}
                    input_now=touch_event_time(&events[i],milliseconds());char bytes[4];unsigned count=input_event_bytes(&events[i],bytes);
                    power_event(&events[i],input_now);
                    if(events[i].type==EV_SYN){dirty=1;if(ensure_shell()<0){result=1;break;}}
                    key_presses+=send_input(bytes,count);
                }
                if(result)break;
            }
        }
        if(result)break;
        if(pollers[MAX_SESSIONS].revents&(8|16)){message("Touchscreen disconnected\n");result=1;break;}
        if(power>=0 && (pollers[MAX_SESSIONS+1].revents&1)){
            struct input_event events[16];long n=syscall6(READ,power,(long)events,sizeof(events),0,0,0);
            if(n>0)for(unsigned i=0;i<(unsigned)n/sizeof(events[0]);i++)power_event(&events[i],milliseconds());
        }
        if(power>=0 && (pollers[MAX_SESSIONS+1].revents&(8|16))){close_fd(power);power=-1;power_held=0;}
        long now=milliseconds();char held[4];unsigned held_count=power_menu?0:input_tick(now,held);
        if(held_count){key_presses+=send_input(held,held_count);dirty=1;}
        if(power_tick(now)){if(touch_pressed)cancel_touch();message(power_menu?"POWER MENU OPEN\n":"POWER MENU CLOSED\n");dirty=1;}
        if(power_action!=POWER_NONE){dispatch_power(power_action,test);power_action=POWER_NONE;dirty=1;}
        if(now-status_at>=1000){refresh_status((++status_ticks&1)==0);status_at=now;dirty=1;}
        int blink=(now/500)&1;
        if(dirty || blink!=old_blink){render((unsigned char *)address,&render_mode,&f,blink);
            long pan=io(framebuffer,FBIOPAN_DISPLAY,&v);if(pan<0){value_message("Terminal pan failed: ",pan);result=1;break;}dirty=0;old_blink=blink;}
    }
    for(unsigned i=0;i<MAX_SESSIONS;i++){active_session=i;if(sessions[i].master>=0)end_shell(sessions[i].master);}
    if(test){
        memcpy((void *)address,(const void *)snapshot,f.smem_len);io(framebuffer,FBIOPAN_DISPLAY,&v);
        syscall6(MUNMAP,snapshot,f.smem_len,0,0,0,0);message("PREVIOUS FRAMEBUFFER RESTORED\n");
        io(touch,EVIOCGRAB,0);
    }
    close_fd(touch);close_fd(framebuffer);if(power>=0)close_fd(power);
    value_message("Keyboard presses sent to shell: ",key_presses);value_message("Shell output bytes: ",output_bytes);
    value_message("Touchscreen events processed: ",touch_events);value_message("Touchscreen queue overflows: ",touch_drops);
    message("ONDEVICE TERMINAL TEST COMPLETE\n");return result;
}

__attribute__((used,noreturn)) static void terminal_entry(long *stack)
{
    int result=main_terminal(stack[0],(char **)(stack+1));syscall6(A64_EXIT_GROUP,result,0,0,0,0,0);for(;;){}
}
__asm__(".global _start\n_start:\nmov x0, sp\nbl terminal_entry\n");
#endif
