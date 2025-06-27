#!/bin/bash

# Copyright (c) 2024 The Regents of the University of California.
# SPDX-License-Identifier: BSD 3-Clause

echo "Disabling unused services and networking for simulation."

# === Disable networking ===
echo "Disabling network by default."
if [ -f /etc/netplan/50-cloud-init.yaml ]; then
    mv /etc/netplan/50-cloud-init.yaml /etc/netplan/50-cloud-init.yaml.bak
elif [ -f /etc/netplan/00-installer-config.yaml ]; then
    mv /etc/netplan/00-installer-config.yaml /etc/netplan/00-installer-config.yaml.bak
fi
netplan apply 2>/dev/null

# Disable services that wait for networking
systemctl disable systemd-networkd-wait-online.service
systemctl mask systemd-networkd-wait-online.service
systemctl disable systemd-networkd.service
systemctl mask systemd-networkd.service
systemctl disable systemd-resolved.service
systemctl mask systemd-resolved.service

# === Disable cloud-init ===
echo "Disabling cloud-init."
touch /etc/cloud/cloud-init.disabled
systemctl disable cloud-init.service
systemctl mask cloud-init.service
systemctl disable cloud-config.service cloud-final.service cloud-init-local.service
systemctl mask cloud-config.service cloud-final.service cloud-init-local.service

# === Disable background update and time sync services ===
systemctl disable unattended-upgrades.service
systemctl mask unattended-upgrades.service
systemctl disable apt-daily.timer apt-daily-upgrade.timer
systemctl mask apt-daily.timer apt-daily-upgrade.timer
systemctl disable systemd-timesyncd.service
systemctl mask systemd-timesyncd.service

# === Disable rarely needed system services ===
for svc in \
    ModemManager.service \
    udisks2.service \
    snapd.service \
    polkit.service \
    rsyslog.service \
    irqbalance.service \
    networkd-dispatcher.service \
    systemd-tmpfiles-clean.timer \
    systemd-tmpfiles-clean.service \
    systemd-update-utmp.service \
    systemd-update-utmp-runlevel.service
do
    systemctl disable "$svc"
    systemctl mask "$svc"
done

# === Optional: Disable logging services if not needed ===
# systemctl disable systemd-journald.service
# systemctl mask systemd-journald.service

# === Keep essential services ===
echo "Keeping essential services: systemd-udevd, logind, sshd (optional)."

# === Optional: Disable SSH if not needed ===
# systemctl disable ssh.service
# systemctl mask ssh.service

echo "Finished disabling unnecessary services."
