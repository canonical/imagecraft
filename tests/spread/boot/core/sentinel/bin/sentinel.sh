#!/bin/bash

if [ "$(dpkg --print-architecture)" = "amd64" ]; then
  SERIAL_CONSOLE="/dev/ttyS0"
else
  SERIAL_CONSOLE="/dev/ttyAMA0"
fi
echo "HELLO FROM IMAGECRAFT" > $SERIAL_CONSOLE

sleep 5
poweroff
