#!/usr/bin/env python
import signal
import sys
import can
import time
import json
import os
from can import Message
import yaml
from can import Message
from flask import Flask, jsonify, make_response
from flask_restful import Resource, Api
import threading
from threading import Thread, Lock
app = Flask(__name__)
api = Api(app)


thread_lock = Lock()


VESC_STATUS_DICT =  dict();

class vesc_status():
    rpm = None
    total_current = None
    total_amp_hours_consumed = None
    total_amp_hours_regenerative = None
    total_watt_hours_regenerative = None
    total_watt_hours_consumed = None
    mosfet_temperature = None
    motor_temperature = None
    total_input_current = None
    current_pid_position = None

    def __init__(self):
        pass
    def toJson(self):
        return json.dumps(self.toDict())

    def toDict(self):
        return {
            "rpm": self.rpm,
            "total_current": self.total_current,
            "total_amp_hours_consumed": self.total_amp_hours_consumed,
            "total_amp_hours_regenerative": self.total_amp_hours_regenerative,
            "total_watt_hours_regenerative": self.total_watt_hours_regenerative,
            "total_watt_hours_consumed": self.total_watt_hours_consumed,
            "mosfet_temperature": self.mosfet_temperature,
            "motor_temperature": self.motor_temperature,
            "total_input_current": self.total_input_current,
            "current_pid_position": self.current_pid_position
        }
    def __dict__(self):
        return self.toDict()

    def __json__(self):
        return self.__dict__


class vesc_send_values():
    def __init__(self):
        pass
    
#### BASE ADRESSES + VESC ID
PACKET_1_BASE = 2304
PACKET_2_BASE = 3584
PACKET_3_BASE = 3840
PACKET_4_BASE = 4096
PACKET_1 = 1
PACKET_2 = 2
PACKET_3 = 3
PACKET_4 = 4

SET_PACKET_DUTYCYCLE = 0
SET_PACKET_CURRENT = 1
SET_PACKET_CURRENTBRAKE = 2
SET_PACKET_RPM = 3
SET_PACKET_POSITION = 4


def check_is_vesc(_msg, _vid):
    str_id = str(_msg.arbitration_id)
    if len(str_id) == 4:

        if _msg.arbitration_id == (PACKET_1_BASE+_vid):
            return True, PACKET_1
        elif _msg.arbitration_id == (PACKET_2_BASE+_vid):
            return True, PACKET_2
        elif _msg.arbitration_id == (PACKET_3_BASE+_vid):
            return True, PACKET_3
        elif _msg.arbitration_id == (PACKET_4_BASE+_vid):
            return True, PACKET_4
    return False, None


def parse_packet_1(_msg, _vid):
    VESC_STATUS_DICT[str(_vid)].rpm = int.from_bytes([_msg.data[3], _msg.data[2], _msg.data[1], _msg.data[0]],byteorder='little', signed=False)
    VESC_STATUS_DICT[str(_vid)].total_current = int.from_bytes([_msg.data[4], _msg.data[5]], byteorder='little', signed=False) / 10.0


def parse_packet_2(_msg, _vid):
    VESC_STATUS_DICT[str(_vid)].total_amp_hours_consumed = int.from_bytes([_msg.data[3], _msg.data[2], _msg.data[1], _msg.data[0]],byteorder='little', signed=False) / 10000.0
    VESC_STATUS_DICT[str(_vid)].total_amp_hours_regenerative = int.from_bytes([_msg.data[4], _msg.data[5], _msg.data[6], _msg.data[7]], byteorder='little', signed=False) / 10000.0

def parse_packet_3(_msg, _vid):
    VESC_STATUS_DICT[str(_vid)].total_watt_hours_consumed = int.from_bytes([_msg.data[3], _msg.data[2], _msg.data[1], _msg.data[0]], byteorder='little', signed=False) / 10000.0
    VESC_STATUS_DICT[str(_vid)].total_watt_hours_regenerative = int.from_bytes([_msg.data[4], _msg.data[5], _msg.data[6], _msg.data[7]], byteorder='little', signed=False) / 10000.0

def parse_packet_4(_msg, _vid):
    VESC_STATUS_DICT[str(_vid)].mosfet_temperature = int.from_bytes([_msg.data[0], _msg.data[1]], byteorder='little',
                                                               signed=True) / 100.0
    VESC_STATUS_DICT[str(_vid)].motor_temperature = int.from_bytes([_msg.data[2], _msg.data[3]], byteorder='little',
                                                               signed=True) / 100.0
    VESC_STATUS_DICT[str(_vid)].total_input_current = int.from_bytes([_msg.data[4], _msg.data[5]], byteorder='little',
                                                               signed=False) / 10.0
    VESC_STATUS_DICT[str(_vid)].current_pid_position = int.from_bytes([_msg.data[6], _msg.data[7]], byteorder='little',
                                                               signed=False)



def  create_vesc_data_object(_vid):
    VESC_STATUS_DICT[str(_vid)] = vesc_status()

def int_to_bytes(val, num_bytes):
    return [(val & (0xff << pos*8)) >> pos*8 for pos in reversed(range(num_bytes))]

def signal_handler(sig, frame):
    print('You pressed Ctrl+C!')
    sys.exit(0)
# Press the green button in the gutter to run the script.

def send_rpm(_bus, _vid, _value: float):
    send_value_over_can(_bus, _vid, int(_value), SET_PACKET_RPM)

def send_current(_bus, _vid, _value: float):
    send_value_over_can(_bus, _vid, int(_value*1000.0), SET_PACKET_CURRENT)

def send_currentbrake(_bus, _vid, _value: float):
    send_value_over_can(_bus, _vid, int(_value*1000.0), SET_PACKET_CURRENTBRAKE)

def send_dutycycle(_bus, _vid, _value: float):
    send_value_over_can(_bus, _vid, int(_value*100000.0), SET_PACKET_DUTYCYCLE)

def send_position(_bus, _vid, _value: float):
    send_value_over_can(_bus, _vid, int(_value*100000.0), SET_PACKET_POSITION)

def send_value_over_can(_bus, _vid, _rpm, _packet_id):
    id_bytes = int_to_bytes(int(_vid), 2)
    id_int = int(str('3' + str(id_bytes[0]) + str(id_bytes[1])), 16)
    #val = int_to_bytes(int(_rpm), 4)
    val = hex(_rpm)
    val = int(val, 16)
    val = int_to_bytes(int(val), 4)
    msg = Message(is_extended_id=True, arbitration_id=id_int, data=[val[0], val[1], val[2], val[3]])
    _bus.send(msg)


def can_thread(_cfg, _lock, _bus):
    global VESC_STATUS_DICT

    ids = cfg['vesc_controller_ids']

    send_rpm(_bus, ids[0], 3000)


    while True:
        # GET LAST CAN MESSAGE
        msg = _bus.recv()
        if msg is None:
            continue
        # PARSE PACKET
        for vid in ids:
            valid, pid = check_is_vesc(msg, vid)
            # IF VALID PACKET FOUND
            if valid:
                _lock.acquire()
                if pid == PACKET_1:
                    parse_packet_1(msg, vid)
                elif pid == PACKET_2:
                    parse_packet_2(msg, vid)
                elif pid == PACKET_3:
                    parse_packet_3(msg, vid)
                elif pid == PACKET_4:
                    parse_packet_4(msg, vid)
                _lock.release()

        time.sleep(0.01)




@app.route('/',methods = ['GET'])
def login():
    global thread_lock
    data = None
    if thread_lock.acquire(blocking=True, timeout=1000):
        data = VESC_STATUS_DICT
        thread_lock.release()


    if data:

        # CREATE CONTROLLER INFO DICT
        resp = dict()

        for vid in data.keys():#
            d =  data[vid].toDict()
            resp[vid] = d


        return make_response(jsonify(resp), 200)
    else:
        return make_response(jsonify({"err": "lock_failed_timeout"}), 500)




if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)


    # LOAD CONFIG
    local_path = os.path.dirname(os.path.abspath(__file__))
    cfg = None
    with open(os.path.join(local_path, 'config.yaml'), 'r') as yaml_file:
        cfg = yaml.safe_load(yaml_file)


    if cfg is None:
        print("cfg loading error")
        exit(-1)

    # CREATE CONTROLLER INFO DICT
    for vid in cfg['vesc_controller_ids']:
        create_vesc_data_object(vid)


    # CONNECT CAN BUS
    bus = can.interface.ThreadSafeBus(bustype=str(cfg['can_type']), channel=str(cfg['can_interface']),
                            bitrate=int(cfg['can_baudrate']))

    # START CAN THREAD
    can_thread_instance = threading.Thread(target=can_thread, args=(cfg, thread_lock, bus, ))
    can_thread_instance.start()

    app.run(host=cfg['webserver_host'], port=cfg['webserver_port'])
    can_thread_instance.join(1000)

