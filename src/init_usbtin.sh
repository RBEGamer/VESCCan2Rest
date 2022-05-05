#!/bin/bash

#if [ "$EUID" -ne 0 ]
#  then echo "Please run as root"
#  exit
#fi

# ENBALE KERNEL MODULES FOR CAN
modprobe can
modprobe can-raw
modprobe slcan

ifconfig can0 down  || true


# SETUP CAN INTERFACE
# -s SPEED -s5 => 250k
slcan_attach -f -n can0 -s5 -o /dev/ttyCAN
slcand ttyCAN can0
ifconfig can0 up
