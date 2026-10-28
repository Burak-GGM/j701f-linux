# Modem

The J701F has an integrated Samsung Shannon 315 cellular modem. Mainline
Linux boots the phone, but calls, SMS and mobile data are not working yet.
The modem has its own firmware and talks to Linux through reserved memory and
a mailbox; the current mainline system has no driver or boot service for it.

The first development step is a host-only reader for the 512-byte table at
the start of a RADIO image. `tools/modem-radio-toc.py` checks the `BOOT` and
`MAIN` sections and their file bounds without copying their firmware or
touching the phone. Its format follows the public
[Samsung TOC template](https://github.com/Comsecuris/shannonRE/blob/master/010/sam.bt).
The tool passed malformed-header tests and the header of a stock SM-J701F
CP package on the development computer. Claude also read the phone's first
512 RADIO bytes through USB serial without writing to it; they match the
factory header exactly. The tool does not validate a
firmware signature or start the modem.

Source for a one-shot read-only mailbox diagnostic was compiled and loaded
once. It read the CP power register through the secure monitor (`0xb`) and
found the CP mailbox registers at zero, then unloaded itself. Claude's next
bounded trial copied BOOT and MAIN into reserved CP RAM and the secure monitor
accepted them. It did not power or start the CP, so there is still no modem
link. Nothing has been written to a phone partition.

The factory driver uses SIPC5 channels for boot, formatted commands and the
radio file service. A host-only frame parser and a synthetic NV request model
are now tested. The model keeps all writes in RAM and cannot read EFS. The
actual J701F response format remains to be measured after the CP starts.
`libsamsung-ipc` has useful Samsung protocol support but no J701F backend;
the eventual path is a J701F backend, then the `samsungipcd` AT bridge and
ModemManager. None is installed as a working modem service. See the
[technical notes](https://github.com/Burak-GGM/j701f-linux/blob/main/docs/j701f-modem.md)
and [userspace design](https://github.com/Burak-GGM/j701f-linux/blob/main/docs/j701f-modem-userspace.md).
