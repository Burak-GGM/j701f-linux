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
#include "../kernel/diagnostic/j701f-ramboot.c"

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

static void addresses(ulong start, ulong end, int wide)
{
    int node = fdt_path_offset(previous, "/chosen");
    if (wide) {
        fdt64_t a = cpu_to_fdt64(start), b = cpu_to_fdt64(end);
        assert(!fdt_setprop(previous, node, "linux,initrd-start", &a, sizeof(a)));
        assert(!fdt_setprop(previous, node, "linux,initrd-end", &b, sizeof(b)));
    } else {
        fdt32_t a = cpu_to_fdt32(start), b = cpu_to_fdt32(end);
        assert(!fdt_setprop(previous, node, "linux,initrd-start", &a, sizeof(a)));
        assert(!fdt_setprop(previous, node, "linux,initrd-end", &b, sizeof(b)));
    }
}

static void reset(void)
{
    assert(!fdt_create_empty_tree(previous, 65536));
    assert(fdt_add_subnode(previous, 0, "chosen") >= 0);
    addresses((ulong)payload, (ulong)payload + J701F_FIT_BYTES, 0);
    bd.bi_dram[0] = (struct test_bank){0x40000000UL, 0x3e400000UL};
    bd.bi_dram[1] = (struct test_bank){0x80000000UL, 0x40000000UL};
    global = (struct test_gd){&bd, 0xbff00000UL};
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
    payload = mmap((void *)0x43000000UL, J701F_FIT_BYTES, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    assert(previous == (void *)0x42000000UL && payload == (void *)0x43000000UL);
    FILE *input = fopen(argv[1], "rb");
    assert(input && fread(payload, 1, J701F_FIT_BYTES, input) == J701F_FIT_BYTES);
    assert(fgetc(input) == EOF); fclose(input);
    reset(); expect(1); /* Valid 32-bit Samsung properties. */
    reset(); addresses((ulong)payload, (ulong)payload + J701F_FIT_BYTES, 1); expect(1);
    reset(); board_name = "j6lte"; expect(0);
    reset(); bd.bi_dram[1].size -= 4096; expect(0);
    reset(); global.relocaddr = 0xb0000000UL; expect(0);
    reset(); assert(!fdt_del_node(previous, fdt_path_offset(previous, "/chosen"))); expect(0);
    reset(); addresses(J701F_TARGETS_END - 4096, J701F_TARGETS_END - 4096 + J701F_FIT_BYTES, 0); expect(0);
    reset(); addresses((ulong)payload + 1, (ulong)payload + 1 + J701F_FIT_BYTES, 0); expect(0);
    reset(); addresses((ulong)payload, (ulong)payload + J701F_FIT_BYTES - 1, 0); expect(0);
    reset(); addresses(J701F_SOURCE_LIMIT - 4096, J701F_SOURCE_LIMIT - 4096 + J701F_FIT_BYTES, 0); expect(0);
    reset(); ((unsigned char *)payload)[1024] ^= 1; expect(0); ((unsigned char *)payload)[1024] ^= 1;
    reset(); ((unsigned char *)payload)[0] ^= 1; expect(0); ((unsigned char *)payload)[0] ^= 1;
    reset(); env_failure = -1; expect(0);
    assert(!munmap(previous, 65536)); assert(!munmap(payload, J701F_FIT_BYTES));
    puts("PASS: 2 valid RAM handoffs; 11 invalid handoffs stopped before bootm");
    return 0;
}
