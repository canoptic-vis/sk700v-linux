#!/bin/sh
# Install (or with --uninstall, remove) the SK700V display service. Run with sudo.
set -e
cd "$(dirname "$0")"

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run with sudo: sudo ./install.sh" >&2
    exit 1
fi

if [ "$1" = "--uninstall" ]; then
    systemctl disable --now sk700v-display 2>/dev/null || true
    rm -f /usr/local/bin/sk700v-display /etc/systemd/system/sk700v-display.service \
          /etc/udev/rules.d/70-sk700v.rules
    systemctl daemon-reload
    udevadm control --reload
    echo "SK700V display service removed."
    exit 0
fi

install -m 755 sk700v-display.py /usr/local/bin/sk700v-display
install -m 644 sk700v-display.service /etc/systemd/system/sk700v-display.service
install -m 644 70-sk700v.rules /etc/udev/rules.d/70-sk700v.rules
udevadm control --reload && udevadm trigger
systemctl daemon-reload
systemctl enable --now sk700v-display
echo "SK700V display service installed and running."
echo "Check it with: systemctl status sk700v-display"
