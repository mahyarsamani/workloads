#!/bin/bash

# Copyright (c) 2024 The Regents of the University of California.
# SPDX-License-Identifier: BSD 3-Clause

echo "Installing user packages..."

# Put your package installation commands here
sudo apt-get -y update

sudo apt-get -y -o Dpkg::Options::="--force-confnew" upgrade

# Install desired packages
sudo apt-get -y -o Dpkg::Options::="--force-confnew" install python3-pip gfortran cmake openmpi-bin libopenmpi-dev

echo "Done installing user packages."
