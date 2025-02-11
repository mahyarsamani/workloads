#!/bin/bash

# Copyright (c) 2024 The Regents of the University of California.
# SPDX-License-Identifier: BSD 3-Clause

echo "Post Installation Started."


echo "Installing serial service for autologin after systemd."
mkdir /etc/systemd/system/serial-getty@.service.d/
mv serial-getty@.service-override.conf /etc/systemd/system/serial-getty@.service.d/override.conf

# Installing the packages in this script instead of the user-data
# file dueing ubuntu autoinstall. The reason is that sometimes
# the package install failes. This method is more reliable.

echo "Installing packages required for gem5-bridge (m5) and libm5."
apt-get update
apt-get install -y scons
apt-get install -y git
apt-get install -y vim
apt-get install -y build-essential

# Add after_boot.sh to bashrc in the gem5 user account
# This will run the script after the user automatically logs in
echo "Adding after_boot.sh to the gem5 user's .bashrc."
echo -e "\nif [ -z \"\$AFTER_BOOT_EXECUTED\" ]; then\n   export AFTER_BOOT_EXECUTED=1\n    /home/gem5/after_boot.sh\nfi\n" >> /home/gem5/.bashrc

# Remove the motd
rm /etc/update-motd.d/*

# Build and install the gem5-bridge (m5) binary, library, and headers
echo "Building and installing gem5-bridge (m5) and libm5."

# Ensure the ISA environment variable is set
if [ -z "$ISA" ]; then
  echo "Error: ISA environment variable is not set."
  exit 1
fi

# moving modules to the correct location
mv /home/gem5/5.15.167 /lib/modules/5.15.167
depmod --quick -a 5.15.167
update-initramfs -u -k 5.15.167

# Just get the files we need
git clone https://github.com/nkrim/gem5.git --depth=1 --filter=blob:none --no-checkout --sparse --single-branch --branch=gem5-bridge
pushd gem5
# Checkout just the files we need
git sparse-checkout add util/m5
git sparse-checkout add util/gem5_bridge
git sparse-checkout add include
git checkout
# Install the headers globally so that other benchmarks can use them
cp -r include/gem5 /usr/local/include/

# Build the library and binary
pushd util/m5
scons build/${ISA}/out/m5
cp build/${ISA}/out/m5 /usr/local/bin/
cp build/${ISA}/out/libm5.a /usr/local/lib/
popd   # util/m5
popd   # gem5

# rename the m5 binary to gem5-bridge
mv /usr/local/bin/m5 /usr/local/bin/gem5-bridge
# Set the setuid bit on the m5 binary
chmod 4755 /usr/local/bin/gem5-bridge
chmod u+s /usr/local/bin/gem5-bridge

#create a symbolic link to the gem5 binary for backward compatibility
ln -s /usr/local/bin/gem5-bridge /usr/local/bin/m5

# delete the git repo for gem5
rm -rf gem5
echo "Done building and installing gem5-bridge (m5) and libm5."
