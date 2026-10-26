/* SPDX-License-Identifier: GPL-2.0 */
#include "j701f-embedded-file.h"
.section .rodata.j701f_fit,"a"
.balign 8
.global j701f_embedded_fit
.global j701f_embedded_fit_end
j701f_embedded_fit:
.incbin J701F_EMBEDDED_FILE
j701f_embedded_fit_end:
