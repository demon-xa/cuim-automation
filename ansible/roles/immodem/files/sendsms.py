#!/usr/bin/python3

import serial
import json
import socket

info={
    "type":"immodem",
    "hostname": socket.gethostname(),
    "uicc":"",
    "operator":""
}
cmdList=['AT+CMGF=1', 'AT+CSMP=17,167,0,0', 'AT+CMGS="+79315906271"', b'\x1A']

def command(serial, cmd):
    if type(cmd) is str:
        cmd=cmd.encode()

    serial.write(cmd+b'\x0d'+b'\x0a')
    print(serial.readline().decode().strip())
    return serial.readlines()[1].decode()

# try:
    # /dev/ttyUSB4
    # /dev/SIM7600
ser = serial.Serial('/dev/SIM7600', 9600, timeout=1)
#info['uicc'] = command(ser, 'AT+CICCID').split(':')[1].strip() or 'unknown'
info['operator'] = command(ser, 'AT+CSPN?').split('"')[1].strip() or 'unknown'

cmdList.insert(len(cmdList)-1, json.dumps(info, separators=(',', ':')))

for cmd in cmdList:
    print(cmd)
    command(ser, cmd)
# except Exception as error:
#     print(error)
# finally:
if ser:
    ser.close()
