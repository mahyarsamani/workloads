#!/bin/bash

mkdir -p sysroots/aarch64
sudo debootstrap --arch=arm64 --foreign stable sysroots/aarch64 http://deb.debian.org/debian

# 3. Setup the emulator bridge
sudo cp /usr/bin/qemu-aarch64-static sysroots/aarch64/usr/bin/

# 4. Run second stage and install DEV dependencies
# This ensures you have crt1.o, libc.so, and headers for cross-compiling
sudo chroot sysroots/aarch64 /debootstrap/debootstrap --second-stage
sudo chroot sysroots/aarch64 apt-get update
sudo chroot sysroots/aarch64 apt-get install -y libc6-dev libstdc++-12-dev

# 5. CONVERT TO RELATIVE SYMLINKS (Crucial step)
# This makes the sysroot portable and prevents it from looking at your host /lib
sudo apt-get install -y symlinks
sudo symlinks -cr sysroots/aarch64