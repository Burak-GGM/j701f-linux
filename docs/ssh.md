# SSH milestone — 2026-10-07

SSH from this laptop to the normal Alpine system is working. After the GUI preparation's normal reboot, the phone uses `192.168.1.140`; Wi-Fi DHCP can change that address.

```sh
ssh burak-alpine@192.168.1.140
```

The account `burak-alpine` was created with UID/GID 1000, home `/home/burak-alpine` and shell `/bin/sh`. It authenticates with the laptop's existing `~/.ssh/id_ed25519` key: only its public half was copied into the phone's `authorized_keys`. The private key remains on the laptop. The account has an unknown random password generated on the phone; SSH password authentication is disabled. This is a regular user account. Subsequently, the user explicitly approved unrestricted passwordless sudo; `sudo -i` now opens a root shell, and `sudo apk add ...` works. `/etc/sudoers.d/j701f` grants `burak-alpine ALL=(root) NOPASSWD: ALL`. SSH authentication remains key-only and direct root SSH login stays disabled. Root access is also available through the existing local/USB terminal.

The first connection using the laptop's normal known_hosts file may ask for host verification. The phone's ED25519 fingerprint, obtained through USB, is:

```
SHA256:yb51tyRyOfRJL7UFUgnEb5KV2nT9/jlpNsB3XJclqkc
```

Test connections used a dedicated `build/phone-ssh-known-hosts` file containing the host public key read over USB and `StrictHostKeyChecking=yes`. No existing laptop known_hosts entries were replaced. Host keys live on the phone in `/etc/ssh` and are not included in repository source or flash images.

## Why registration did not start SSH

The user installed OpenSSH and OpenRC, then registered sshd with rc-update. Live inspection showed no SSH listener, no host keys and no burak-alpine user. Our `/etc/inittab` calls the custom J701F startup and does not invoke OpenRC runlevels. The sshd registration was under sysinit, not default.

OpenRC installation alone does not change this boot path. Alpine's standard integration explicitly invokes OpenRC from BusyBox inittab, as described in the [Alpine OpenRC documentation](https://wiki.alpinelinux.org/wiki/OpenRC). `rc-update` registers a service; starting it is separate, as shown in [Alpine's SSH setup](https://wiki.alpinelinux.org/wiki/Setting_up_a_SSH_server).

The reported `hwdrivers`/`machine-id` missing `dev` dependencies concern the installed OpenRC service set. They do not describe the running J701F init services. A full OpenRC migration and its device-services integration were not performed for this SSH fix. OpenRC remains installed and its existing service registrations remain intact; rc-status does not show the SSH service supervised by BusyBox init. Avoid starting a second sshd through rc-service while this service is running.

## Startup and settings

`system/sshd` installs as `/sbin/j701f-sshd`, with a respawn entry in our inittab. It waits when OpenSSH or the provisioned config is absent, generates missing host keys with `ssh-keygen -A`, validates configuration, and runs sshd in the foreground for init to supervise. Runtime logging goes to `/run/j701f-sshd.log`. Keys persist on DATA; runtime logs reside in RAM.

`system/sshd-config` was provisioned as `/etc/ssh/sshd_config.d/00-j701f.conf`. It enables public-key authentication, restricts login to burak-alpine, and disables root, password and keyboard-interactive SSH login. The user's existing package-managed sshd_config was preserved. The public-key file has mode 0600, its directory 0700, and both belong to burak-alpine.

The image builder includes the optional service wrapper, but not the installed OpenSSH packages, private host keys, user account or authorized key/config. Existing flash images predate this live installation. No partitions were reflashed to enable SSH.

## Verification

`sshd -t` passed; effective authentication settings were checked with `sshd -T`. Init reload started the foreground service, listening on port 22. An authenticated, host-key-verified network connection returned UID 1000, the expected kernel and Alpine 3.24.0. An interactive pseudo-terminal was also tested. Reports: `build/phone-ssh-start.txt` and `build/phone-ssh-test.txt`. Shell syntax and the 14 system-image unit tests passed. During the subsequent CPU BOOT-parameter trial, a normal reboot automatically restored Wi-Fi and SSH, with the same host key and a new DHCP address `.140`. The dedicated known-hosts file now pins both observed addresses to the key obtained through USB.

Inspect the running server from the USB root terminal:

```sh
netstat -lnt
ps | grep sshd
cat /run/j701f-sshd.log
```
