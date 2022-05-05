#!/bin/bash
cd "$(dirname "$0")"


# ENBALE KERNEL MODULES FOR CAN
#modprobe can
#modprobe can-raw

#modprobe slcan

ifconfig can0 down  || true


# SETUP CAN INTERFACE
# -s SPEED -s5 => 250k
slcan_attach -f -n can0 -s5 -o /dev/ttyCAN
slcand ttyCAN can0
ifconfig can0 up



python3 main.py
