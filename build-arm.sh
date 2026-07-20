#!/bin/bash

# Copyright (c) 2024 The Regents of the University of California.
# SPDX-License-Identifier: BSD 3-Clause

PACKER_VERSION="1.10.0"

# This part installs the packer binary on the arm64 machine as we are assuming
# that we are building the disk image on an arm64 machine.
if [ ! -f ./packer ]; then
    wget https://releases.hashicorp.com/packer/${PACKER_VERSION}/packer_${PACKER_VERSION}_linux_arm64.zip;
    unzip packer_${PACKER_VERSION}_linux_arm64.zip;
    rm packer_${PACKER_VERSION}_linux_arm64.zip;
fi

# Parse optional flags
REBUILD_MODULES=false
while [[ "$1" == --* ]]; do
    case "$1" in
        --rebuild-modules)
            REBUILD_MODULES=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check if the Ubuntu version variable is provided
if [ -z "$1" ]; then
    echo "Usage: $0 [--rebuild-modules] <ubuntu_version> [image_name]"
    echo "Example: $0 22.04 or $0 --rebuild-modules 22.04"
    exit 1
fi

# Store the Ubuntu version from the command line argument
ubuntu_version="$1"

# Check if the specified Ubuntu version is valid
if [[ "$ubuntu_version" != "22.04" && "$ubuntu_version" != "24.04" ]]; then
    echo "Error: Invalid Ubuntu version '$ubuntu_version'. Must be '22.04' or '24.04'."
    exit 1
fi

# Store the image name from the second command line argument or default to "arm-ubuntu"
image_name="${2:-arm-ubuntu}"

# Optionally rebuild kernel modules from scratch
if [ "$REBUILD_MODULES" = true ]; then
    echo "Rebuilding kernel modules..."
    rm -rf ./modules/u2204/files
    pushd ./modules/u2204
    bash copy_modules.sh
    popd
fi

# make the flash0.img file
cd ./files
dd if=/dev/zero of=flash0.img bs=1M count=64
dd if=/usr/share/qemu-efi-aarch64/QEMU_EFI.fd of=flash0.img conv=notrunc
cd ..

# Install the needed plugins
./packer init ./packer-scripts/arm-ubuntu.pkr.hcl

# Build the image with the specified Ubuntu version
./packer build -var "ubuntu_version=${ubuntu_version}" -var "image_name=${image_name}" ./packer-scripts/arm-ubuntu.pkr.hcl
