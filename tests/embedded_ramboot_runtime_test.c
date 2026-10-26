/* Run the actual loader guards with mocked boot/environment APIs on the host.
 * Never executes bootm or accesses a phone. libfdt parses real FDT bytes. */
#include <assert.h>
#include <fcntl.h>
#include <openssl/sha.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>
#include "ramboot-host.h"
#include "../kernel/diagnostic/j701f-embedded-ramboot.c"

static struct test_bd bd;
static struct test_gd global;
struct test_gd *gd = &global;
static void *previous;
static void *payload;
static unsigned handoffs;
static int env_failure;
static const char *board_name;

const char *env_get(const char *key)
{
    assert(!strcmp(key, "board"));
    return board_name;
}
int env_set(const char *key, const char *value)
{
    assert(!strcmp(key, "verify") || !strcmp(key, "fdt_high") ||
           !strcmp(key, "initrd_high") || !strcmp(key, "bootargs"));
    assert(value && *value);
    return env_failure;
}
ulong get_prev_bl_fdt_addr(void) { return (ulong)previous; }
void sha256_csum_wd(const unsigned char *input, unsigned len, unsigned char *output, unsigned chunk)
{
    assert(chunk == CHUNKSZ_SHA256);
    assert(SHA256(input, len, output));
}
int fit_check_format(const void *fit, ulong bytes)
{
    return fdt_check_full(fit, bytes); /* Guard scope; not a bootm emulator. */
}
int run_commandf(const char *format, ...)
{
    assert(!strcmp(format, "bootm %lx#conf-j701f-diagnostic"));
    handoffs++;
    return -1; /* Never executes the payload. */
}

static void reset(void)
{
    assert(!fdt_create_empty_tree(previous, 65536));
    assert(fdt_add_subnode(previous, 0, "chosen") >= 0);
    bd.bi_dram[0] = (struct test_bank){0x40000000UL, 0x3e400000UL};
    bd.bi_dram[1] = (struct test_bank){0x80000000UL, 0x40000000UL};
    global = (struct test_gd){&bd, 0xbf000000UL, 0x01000000UL};
    board_name = "j7velte";
    handoffs = env_failure = 0;
}

static void expect(unsigned count)
{
    assert(do_j701f_ramboot(NULL, 0, 1, NULL) == CMD_RET_FAILURE);
    assert(handoffs == count);
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    previous = mmap((void *)0x42000000UL, 65536, PROT_READ | PROT_WRITE,
                    MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    payload = mmap((void *)0xbf100000UL, J701F_FIT_BYTES, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    assert(previous == (void *)0x42000000UL && payload == (void *)0xbf100000UL);
    FILE *input = fopen(argv[1], "rb");
    assert(input && fread(payload, 1, J701F_FIT_BYTES, input) == J701F_FIT_BYTES);
    assert(fgetc(input) == EOF); fclose(input);
    reset(); expect(1); /* No firmware initrd properties are necessary. */
    reset(); /* Misleading firmware initrd does not select the payload. */
    assert(!fdt_setprop_u32(previous, fdt_path_offset(previous, "/chosen"), "linux,initrd-start", 1));
    expect(1);
    reset(); board_name = "j6lte"; expect(0);
    reset(); board_name = NULL; expect(0);
    reset(); bd.bi_dram[0].start += 4096; expect(0);
    reset(); bd.bi_dram[1].size -= 4096; expect(0);
    reset(); global.relocaddr = 0xb0000000UL; expect(0);
    reset(); global.relocaddr = 0xc0000000UL; expect(0);
    reset(); global.mon_len = 0; expect(0);
    reset(); global.mon_len = ULONG_MAX; expect(0);
    reset(); global.mon_len = 4096; expect(0); /* Payload outside monitor. */
    reset(); global.relocaddr = (ulong)payload + 8; expect(0); /* Before monitor. */
    reset(); assert(!fdt_del_node(previous, fdt_path_offset(previous, "/chosen"))); expect(0);
    reset(); ((unsigned char *)previous)[0] ^= 1; expect(0);
    reset(); ((unsigned char *)payload)[1024] ^= 1; expect(0); ((unsigned char *)payload)[1024] ^= 1;
    reset(); ((unsigned char *)payload)[0] ^= 1; expect(0); ((unsigned char *)payload)[0] ^= 1;
    reset(); env_failure = -1; expect(0);
    assert(!munmap(previous, 65536)); assert(!munmap(payload, J701F_FIT_BYTES));
    puts("PASS: 2 valid embedded handoffs; 15 invalid handoffs stopped before bootm");
    return 0;
}
