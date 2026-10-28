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
found the CP mailbox registers at zero, then unloaded itself. This is still
an inactive modem link. The host build had unresolved-symbol warnings because
the output tree has no `Module.symvers`; Claude rebuilt against the phone's
kernel tree for the actual trial.
The next stages are a small modular CP
driver, a bounded firmware loader and finally cellular userspace. Booting
the modem also needs a security request and an IPC handshake. Device-specific
NV data will remain in a private copy, with writes held in RAM during early
development. See the [technical notes](https://github.com/Burak-GGM/j701f-linux/blob/main/docs/j701f-modem.md).
