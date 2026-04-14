#!/bin/bash

# Copyright (c) 2024 The Regents of the University of California.
# SPDX-License-Identifier: BSD 3-Clause

echo "Installing user packages..."

# Put your package installation commands here
# add the official Toolchain PPA that ships newer GCC for Jammy (22.04)
add-apt-repository -y ppa:ubuntu-toolchain-r/test    # installs a signed apt source

sudo apt-get -y update

sudo apt-get -y -o Dpkg::Options::="--force-confnew" upgrade

apt-get install -y --no-install-recommends software-properties-common ca-certificates build-essential



# install GCC 13 and C++
apt-get install -y gcc-13 g++-13

# Make gcc/g++ masters point to 13
update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-13 130
update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-13 130
update-alternatives --set gcc /usr/bin/gcc-13
update-alternatives --set g++ /usr/bin/g++-13

# Wire up cc, c++, cpp as their own masters (can't be slaves of gcc)
# These will follow whatever /usr/bin/gcc and /usr/bin/g++ point to.
update-alternatives --install /usr/bin/cc  cc  /usr/bin/gcc   130
update-alternatives --set cc /usr/bin/gcc

update-alternatives --install /usr/bin/c++ c++ /usr/bin/g++   130
update-alternatives --set c++ /usr/bin/g++

update-alternatives --install /usr/bin/cpp cpp /usr/bin/cpp-13 130
update-alternatives --set cpp /usr/bin/cpp-13

# Install desired packages
sudo apt-get -y -o Dpkg::Options::="--force-confnew" install python3-pip gfortran cmake openmpi-bin libopenmpi-dev libpfm4 libpfm4-dev

echo "Done installing user packages."
