#!/usr/bin/env python
import signal
import sys
import can
import time
import json
import os
from can import Message
import yaml
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
#### BASE ADRESSES + VESC ID
PACKET_1_BASE = 2304
PACKET_2_BASE = 3584
PACKET_3_BASE = 3840
PACKET_4_BASE = 4096
PACKET_1 = 1
PACKET_2 = 2
PACKET_3 = 3
PACKET_4 = 4

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


def signal_handler(sig, frame):
    print('You pressed Ctrl+C!')
    sys.exit(0)
# Press the green button in the gutter to run the script.




def can_thread(_cfg, _lock):
    global VESC_STATUS_DICT
    # CONNECT TO CANBUS
    bus = can.interface.Bus(bustype=str(_cfg['can_type']), channel=str(_cfg['can_interface']),
                            bitrate=int(_cfg['can_baudrate']))
    ids = cfg['vesc_controller_ids']

    while True:
        # GET LAST CAN MESSAGE
        msg = bus.recv()
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

    # START CAN THREAD
    can_thread_instance = threading.Thread(target=can_thread, args=(cfg, thread_lock, ))
    can_thread_instance.start()

    app.run(host=cfg['webserver_host'], port=cfg['webserver_port'])
    can_thread_instance.join(1000)

