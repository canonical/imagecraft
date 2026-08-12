#!/bin/bash

for dev in /dev/console /dev/ttyS0 /dev/ttyAMA0 /dev/ttyAMA1; do
  echo "HELLO FROM SENTINEL SNAP" 2>/dev/null >"$dev"
done

sleep 5
dbus-send --system --print-reply \
  --dest=org.freedesktop.login1 /org/freedesktop/login1 \
  "org.freedesktop.login1.Manager.PowerOff" boolean:true
