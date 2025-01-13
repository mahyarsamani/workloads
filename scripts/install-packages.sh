#!/bin/bash

sudo apt-get -y update

# Force apt-get to keep existing config files (confold) and accept defaults (confdef)
sudo apt-get -y \
  -o Dpkg::Options::="--force-confdef" \
  -o Dpkg::Options::="--force-confold" \
  upgrade

# Install desired packages
sudo apt-get -y \
  -o Dpkg::Options::="--force-confdef" \
  -o Dpkg::Options::="--force-confold" \
  install python3-pip gfortran cmake openmpi-bin libopenmpi-dev
