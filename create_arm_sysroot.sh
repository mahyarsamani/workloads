#!/bin/bash
set -e

# 1. Create a directory for our sysroot
SYSROOT_DIR="$(pwd)/sysroots/aarch64"
mkdir -p "$SYSROOT_DIR"

# 2. Install debootstrap to setup a fake root
sudo debootstrap --arch=arm64 --foreign jammy "$SYSROOT_DIR" http://ports.ubuntu.com/ubuntu-ports/

# 3. Setup the emulator bridge
sudo cp /usr/bin/qemu-aarch64-static "$SYSROOT_DIR/usr/bin/"

# 4. Mount virtual filesystems needed for package installation
echo "Mounting virtual filesystems..."
sudo mount -t proc /proc "$SYSROOT_DIR/proc"
sudo mount -t sysfs /sys "$SYSROOT_DIR/sys"
sudo mount -o bind /dev "$SYSROOT_DIR/dev"
sudo mount -o bind /dev/pts "$SYSROOT_DIR/dev/pts"

cleanup() {
    echo "Unmounting virtual filesystems..."
    sudo umount -l "$SYSROOT_DIR/dev/pts" 2>/dev/null || true
    sudo umount -l "$SYSROOT_DIR/dev" 2>/dev/null || true
    sudo umount -l "$SYSROOT_DIR/sys" 2>/dev/null || true
    sudo umount -l "$SYSROOT_DIR/proc" 2>/dev/null || true
}
trap cleanup EXIT

# 5. Run second stage and install DEV dependencies natively via chroot
echo "Configuring sysroot natively..."
sudo chroot "$SYSROOT_DIR" /bin/bash << 'EOF'
set -e

# Run debootstrap second stage
/debootstrap/debootstrap --second-stage

# Install core packages
apt-get update -y
apt-get -y -o Dpkg::Options::="--force-confnew" upgrade
apt-get install -y --no-install-recommends software-properties-common ca-certificates build-essential libc6-dev gnupg

# Add universe repository and PPA for newer GCC
add-apt-repository -y universe
add-apt-repository -y ppa:ubuntu-toolchain-r/test
apt-get update -y

# Install all compiler toolchains and dependencies
apt-get install -y gcc-13 g++-13 gfortran-13 python3-pip cmake openmpi-bin libopenmpi-dev libpfm4 libpfm4-dev

# Configure GCC 13 as default
update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-13 130
update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-13 130
update-alternatives --install /usr/bin/gfortran gfortran /usr/bin/gfortran-13 130
update-alternatives --set gcc /usr/bin/gcc-13
update-alternatives --set g++ /usr/bin/g++-13
update-alternatives --set gfortran /usr/bin/gfortran-13

# Wire up cc, c++, cpp to follow gcc
update-alternatives --install /usr/bin/cc cc /usr/bin/gcc 130
update-alternatives --set cc /usr/bin/gcc
update-alternatives --install /usr/bin/c++ c++ /usr/bin/g++ 130
update-alternatives --set c++ /usr/bin/g++
update-alternatives --install /usr/bin/cpp cpp /usr/bin/cpp-13 130
update-alternatives --set cpp /usr/bin/cpp-13

echo "Sysroot configuration complete."
EOF

# 6. CONVERT TO RELATIVE SYMLINKS (Crucial step)
echo "Converting symlinks..."
sudo apt-get install -y symlinks
sudo symlinks -cr "$SYSROOT_DIR"

# 7. Install gem5 headers and library
echo "Building and installing gem5 m5 utility to sysroot..."
TEMP_GEM5_DIR=$(mktemp -d)
git clone https://github.com/gem5/gem5.git --depth=1 --filter=blob:none --no-checkout --sparse --single-branch --branch=stable "$TEMP_GEM5_DIR"
cd "$TEMP_GEM5_DIR"
git sparse-checkout add util/m5 util/gem5_bridge include
git checkout
cd util/m5
scons build/arm64/out/m5 CROSS_COMPILE=aarch64-linux-gnu- CXX="aarch64-linux-gnu-gcc --sysroot=$SYSROOT_DIR" CC="aarch64-linux-gnu-gcc --sysroot=$SYSROOT_DIR"
sudo mkdir -p "$SYSROOT_DIR/usr/local/include/gem5"
sudo cp -r ../../include/gem5/* "$SYSROOT_DIR/usr/local/include/gem5/"
sudo cp src/m5_mmap.h "$SYSROOT_DIR/usr/local/include/gem5/"
sudo mkdir -p "$SYSROOT_DIR/usr/local/lib"
sudo cp build/arm64/out/libm5.a "$SYSROOT_DIR/usr/local/lib/"
cd "$SYSROOT_DIR/../.."
rm -rf "$TEMP_GEM5_DIR"
