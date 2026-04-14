#!/bin/bash

mkdir -p /etc/systemd/system-preset

mv /home/gem5/00-default.preset /etc/systemd/system-preset/00-default.preset
mv /home/gem5/10-enable-essential.preset /etc/systemd/system-preset/10-enable-essential.preset

systemctl preset-all

