#!/usr/bin/env python
import signal
import sys
import can
import time
import json
import os
from can import Message
import yaml
from can import ThreadSafeBus
from can import Message
from flask import Flask, jsonify, make_response
from flask_restful import Resource, Api
import threading
from threading import Thread, Lock

app = Flask(__name__)
api = Api(app)

#### BASE ADRESSES + VESC ID
PACKET_1_BASE = 2304
PACKET_2_BASE = 3584
PACKET_3_BASE = 3840
PACKET_4_BASE = 4096
PACKET_1 = 1
PACKET_2 = 2
PACKET_3 = 3
PACKET_4 = 4
# PACKET IDS TO SET VALUES THIRD BIT
SET_PACKET_DUTYCYCLE = 0
SET_PACKET_CURRENT = 1
SET_PACKET_CURRENTBRAKE = 2
SET_PACKET_RPM = 3
SET_PACKET_POSITION = 4

thread_lock = Lock()
thread_lock_send = Lock()

VESC_STATUS_DICT = dict()
VESC_SEND_DICT = dict()


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
    rpm = None
    current = None
    currentbrake = None
    dutycycle = None
    position = None

    def __init__(self):
        self.reset()

    def reset(self):
        self.rpm = None
        self.current = None
        self.currentbrake = None
        self.dutycycle = None
        self.position = None

    def set_rpm(self, _value: float):
        self.reset()
        self.rpm = _value

    def set_current(self, _value: float):
        self.reset()
        self.current = int(_value * 10.0)

    def set_currentbrake(self, _value: float):
        self.reset()
        self.currentbrake = int(_value * 10.0)

    def set_dutycycle(self, _value: float):
        self.reset()
        self.dutycycle = int(_value * 1000.0)

    def set_position(self, _value: float):
        self.reset()
        self.position = int(_value * 1000.0)

    def get_current_set_value(self):
        if self.rpm is not None and self.current is None and self.currentbrake is None and self.dutycycle is None and self.position is None:
            return SET_PACKET_RPM, self.rpm
        elif self.rpm is None and self.current is not None and self.currentbrake is None and self.dutycycle is None and self.position is None:
            return SET_PACKET_CURRENT, self.current
        elif self.rpm is None and self.current is None and self.currentbrake is not None and self.dutycycle is None and self.position is None:
            return SET_PACKET_CURRENTBRAKE, self.currentbrake
        elif self.rpm is None and self.current is None and self.currentbrake is None and self.dutycycle is not None and self.position is None:
            return SET_PACKET_DUTYCYCLE, self.dutycycle
        elif self.rpm is None and self.current is None and self.currentbrake is None and self.dutycycle is None and self.position is not None:
            return SET_PACKET_POSITION, self.position
        else:
            return None, None


def check_is_vesc(_msg, _vid):
    str_id = str(_msg.arbitration_id)
    if len(str_id) == 4:

        if _msg.arbitration_id == (PACKET_1_BASE + _vid):
            return True, PACKET_1
        elif _msg.arbitration_id == (PACKET_2_BASE + _vid):
            return True, PACKET_2
        elif _msg.arbitration_id == (PACKET_3_BASE + _vid):
            return True, PACKET_3
        elif _msg.arbitration_id == (PACKET_4_BASE + _vid):
            return True, PACKET_4
    return False, None


def parse_packet_1(_msg, _vid):
    VESC_STATUS_DICT[str(_vid)].rpm = int.from_bytes([_msg.data[3], _msg.data[2], _msg.data[1], _msg.data[0]],
                                                     byteorder='little', signed=False)
    VESC_STATUS_DICT[str(_vid)].total_current = int.from_bytes([_msg.data[4], _msg.data[5]], byteorder='little',
                                                               signed=False) / 10.0


def parse_packet_2(_msg, _vid):
    VESC_STATUS_DICT[str(_vid)].total_amp_hours_consumed = int.from_bytes(
        [_msg.data[3], _msg.data[2], _msg.data[1], _msg.data[0]], byteorder='little', signed=False) / 10000.0
    VESC_STATUS_DICT[str(_vid)].total_amp_hours_regenerative = int.from_bytes(
        [_msg.data[4], _msg.data[5], _msg.data[6], _msg.data[7]], byteorder='little', signed=False) / 10000.0


def parse_packet_3(_msg, _vid):
    VESC_STATUS_DICT[str(_vid)].total_watt_hours_consumed = int.from_bytes(
        [_msg.data[3], _msg.data[2], _msg.data[1], _msg.data[0]], byteorder='little', signed=False) / 10000.0
    VESC_STATUS_DICT[str(_vid)].total_watt_hours_regenerative = int.from_bytes(
        [_msg.data[4], _msg.data[5], _msg.data[6], _msg.data[7]], byteorder='little', signed=False) / 10000.0


def parse_packet_4(_msg, _vid):
    VESC_STATUS_DICT[str(_vid)].mosfet_temperature = int.from_bytes([_msg.data[0], _msg.data[1]], byteorder='little',
                                                                    signed=True) / 100.0
    VESC_STATUS_DICT[str(_vid)].motor_temperature = int.from_bytes([_msg.data[2], _msg.data[3]], byteorder='little',
                                                                   signed=True) / 100.0
    VESC_STATUS_DICT[str(_vid)].total_input_current = int.from_bytes([_msg.data[4], _msg.data[5]], byteorder='little',
                                                                     signed=False) / 10.0
    VESC_STATUS_DICT[str(_vid)].current_pid_position = int.from_bytes([_msg.data[6], _msg.data[7]], byteorder='little',
                                                                      signed=False)


def create_vesc_data_object(_vid):
    VESC_STATUS_DICT[str(_vid)] = vesc_status()
    VESC_SEND_DICT[str(_vid)] = vesc_send_values()


def int_to_bytes(val, num_bytes):
    return [(val & (0xff << pos * 8)) >> pos * 8 for pos in reversed(range(num_bytes))]


def send_value_over_can(_bus, _vid: int, _value: int, _packet_id: int):
    # ID IS IN HEX BUT PYTHON-CAN NEEDS INTEGER BASE 10 AS ID SO CONVERT IT
    id_bytes = int_to_bytes(int(_vid), 2)
    id_int = int(str(str(_packet_id) + str(id_bytes[0]) + str(id_bytes[1])), 16)
    val = hex(_value)
    val = int(val, 16)
    val = int_to_bytes(int(val), 4)
    # EXTENDED IS IMPORTANT
    msg = Message(is_extended_id=True, arbitration_id=id_int, data=[val[0], val[1], val[2], val[3]])
    _bus.send(msg)


def signal_handler(sig, frame):
    print('You pressed Ctrl+C!')
    sys.exit(0)



def can_thread(_cfg, _lock: Lock, _lock_send: Lock, _bus):
    global VESC_STATUS_DICT
    global VESC_SEND_DICT
    ids = cfg['vesc_controller_ids']


    while True:
        # SEND CAN VALUE IF A VALUES WAS SET IN DICT
        for k in VESC_SEND_DICT.keys():
            if _lock_send.acquire(blocking=True, timeout=20):
                pid, dt = VESC_SEND_DICT[k].get_current_set_value()
                if pid is not None and dt is not None:
                    send_value_over_can(_bus, int(k), dt, pid)
                _lock_send.release()


        # GET CAN MESSAGES AND STORE INTO DICT
        msg = _bus.recv(timeout=20)
        if msg is None:
            continue
        # PARSE PACKET
        for vid in ids:
            valid, pid = check_is_vesc(msg, vid)
            # IF VALID PACKET FOUND
            if valid and pid is not None:
                if _lock.acquire(blocking=True, timeout=20):
                    if pid == PACKET_1:
                        parse_packet_1(msg, vid)
                    elif pid == PACKET_2:
                        parse_packet_2(msg, vid)
                    elif pid == PACKET_3:
                        parse_packet_3(msg, vid)
                    elif pid == PACKET_4:
                        parse_packet_4(msg, vid)
                    _lock.release()

        time.sleep(0.02)


def flask_set_can_msg(_vid, _value, _req):
    global thread_lock_send
    global VESC_SEND_DICT
    # CHECK IF VID IN CONTROLLERS
    if str(_vid) in VESC_SEND_DICT:
        if thread_lock_send.acquire(blocking=True, timeout=100):

            if _req == SET_PACKET_RPM:
                VESC_SEND_DICT[str(_vid)].set_rpm(int(_value))
            elif _req == SET_PACKET_CURRENT:
                VESC_SEND_DICT[str(_vid)].set_current(int(_value))
            elif _req == SET_PACKET_CURRENTBRAKE:
                VESC_SEND_DICT[str(_vid)].set_currentbrake(int(_value))
            elif _req == SET_PACKET_POSITION:
                VESC_SEND_DICT[str(_vid)].set_position(int(_value))
            elif _req == SET_PACKET_DUTYCYCLE:
                VESC_SEND_DICT[str(_vid)].set_dutycycle(int(_value))

            thread_lock_send.release()
            return make_response(jsonify({"vid": _vid, "value": _value}), 200)
    else:
        return make_response(jsonify({"err": "vid not registered"}), 404)


@app.route('/set_rpm/<vid>/<value>', methods=['GET'])
def set_rpm(vid, value):
    return flask_set_can_msg(vid, value, SET_PACKET_RPM)

@app.route('/set_current/<vid>/<value>', methods=['GET'])
def set_current(vid, value):
    return flask_set_can_msg(vid, value, SET_PACKET_CURRENT)

@app.route('/set_currentbrake/<vid>/<value>', methods=['GET'])
def set_currentbrake(vid, value):
    return flask_set_can_msg(vid, value, SET_PACKET_CURRENTBRAKE)

@app.route('/set_position/<vid>/<value>', methods=['GET'])
def set_position(vid, value):
    return flask_set_can_msg(vid, value, SET_PACKET_POSITION)

@app.route('/set_dutycycle/<vid>/<value>', methods=['GET'])
def set_dutycycle(vid, value):
    return flask_set_can_msg(vid, value, SET_PACKET_DUTYCYCLE)


@app.route('/')
def get_home():
    return make_response(jsonify({"status": "/status", "set_rpm": "/set_rpm/<vid>/<value>", "set_current": "/set_current/<vid>/<value>", "set_currentbrake": "/set_currentbrake/<vid>/<value>", "set_position": "/set_position/<vid>/<value>", "set_dutycycle": "/set_dutycycle/<vid>/<value>"}), 200)

@app.route('/status', methods=['GET'])
def get_state():
    global thread_lock
    global VESC_STATUS_DICT
    data = None
    if thread_lock.acquire(blocking=True, timeout=1000):
        data = VESC_STATUS_DICT
        thread_lock.release()

    if data:
        # CREATE CONTROLLER INFO DICT
        resp = dict()
        # LOAD DICT FOR EACH CONTROLLER
        for vid in data.keys():  #
            d = data[vid].toDict()
            resp[vid] = d
        # RESPONSE JSON
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
    bus = can.interface.Bus(bustype=str(cfg['can_type']), channel=str(cfg['can_interface']),
                            bitrate=int(cfg['can_baudrate']))

    # START CAN THREAD
    can_thread_instance = threading.Thread(target=can_thread, args=(cfg, thread_lock, thread_lock_send, bus,))
    can_thread_instance.start()

    app.run(host=cfg['webserver_host'], port=cfg['webserver_port'])
    can_thread_instance.join(1000)
