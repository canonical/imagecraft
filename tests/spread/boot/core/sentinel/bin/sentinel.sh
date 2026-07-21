#!/bin/bash

if [ "$(uname -m)" = "x86_64" ]; then
  SERIAL_CONSOLE="/dev/ttyS0"
else
  SERIAL_CONSOLE="/dev/ttyAMA0"
fi
echo "HELLO FROM IMAGECRAFT" > $SERIAL_CONSOLE

sleep 5
dbus-send --system --print-reply \
        --dest=org.freedesktop.login1 /org/freedesktop/login1 \
        "org.freedesktop.login1.Manager.PowerOff" boolean:true
