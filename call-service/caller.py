#!/usr/bin/python3
import os
from time import sleep
import csv
import json
import requests
from sys import exit
from loguru import logger
from subprocess import run

# select dev or prod
dev_stand = False
if dev_stand:
    stand = 'dev'
else:
    stand = 'prod'

#read config.json
with open("config.json") as input_cfg:
    config = json.load(input_cfg)

send_sms_to = "Not send SMS"
cdr_file = config[stand]['cdr_file']
queuedir = config[stand]['queuedir']
asterisk_outgoing_folder = config[stand]['asterisk_outgoing_folder']
log_file = config[stand]['logfile']

# add logger config
logger.add(log_file, rotation=config['rotate_mb'], level=config['logfile_lvl'], format="{time} - {level} - {message}")

last_file = cname = number = ctype = ''
exeption_time_of_call = ('30','9','12','13')
SMSC_STATUS_URL = config['smsc_status_url']
PARAMS_MEGAFON = {
    'login': config['login_megafon'],
    'psw': config['pass_megafon']
}
PARAMS_RESELLER = {
    'login': config['login_reseller'],
    'psw': config['pass_reseller']
}
STATUS_RESPONECE = {
    'Status = 0' : 'fail',  #The message was sent to the operator's SMS center for delivery.
    'Status = 1' : 'online', #The message was successfully delivered to the subscriber.
    'Status = 20' : 'offline' #An attempt to deliver a message failed
}

# send sms via smsc.ru
def send_smsc_sms(parameters: dict) -> str:
    params = {**parameters, **params_for_ping}
    request_ping = requests.get(config['smsc_send_url'], params)
    logger.info(f"_Request to send sms : {request_ping.text}")
    if request_ping.status_code == 200:
        return request_ping.text
    else:
        exit(1)

# check from smsc.ru
def check_smsc_status(parameters: dict) -> str:
    id_ping = send_smsc_sms(parameters).split(' ')[-1]
    # wait for update status on smsc
    sleep(60)
    # check status
    params_check_status = {**parameters, 'phone': number, 'id': id_ping}
    request_status = requests.get(SMSC_STATUS_URL, params_check_status)
    logger.info(f"_Request status to smsc : {request_status.text}")
    respoonce_text = request_status.text.split(", ")
    if respoonce_text[0] in STATUS_RESPONECE:
        return STATUS_RESPONECE[respoonce_text[0]]

# send status in zabbix
def send_in_zabbix(data: dict) -> None:
    # Convert the dictionary to JSON
    json_data = json.dumps(data)
    # Make the POST request with the JSON data
    response = requests.post(config['zabbix_url'], data=json_data)
    logger.info(f"_Send to Zabbix status code: {response.status_code}")

def make_call_file() -> None:
    with open(last_file, 'a') as file:
        # Запись значения переменной в несколько строк
        default_part = """MaxRetries: 0
RetryTime: 1
WaitTime: 30
Context: from-internal
Extension: s
Callerid: 1000
Priority: 1"""
        lines = ["Channel: Local/" + number + "@from-internal\n",
                default_part]
        # Запись строк в файл
        file.writelines(lines)
        logger.info(f"_Create call file")

def remove_tmp_file() -> None:
    try:
        os.remove(file_path)
        #print(f"{last_file} has been removed.")
    except Exception as e:
        logger.info(f"_Failed to remove the file: {str(e)}")

def move_call_file_to_asterisk() -> None:
    if dev_stand is False:
        # change rights (chmod)
        os.chmod(last_file, 0o777)  # set rights (rwxrwxrwx)
        # change owner and group (chown)
        os.chown(last_file, config['user_id_group'], config['user_id_group'])
        # Move file in call folder (shutil.move)
    run(["mv", last_file, asterisk_outgoing_folder])
    logger.info(f"_Files moved for call")

def read_cdr_file(lines: int)-> list:
    # Read 4 last lines
    with open(cdr_file, 'r', newline='') as file:
        reader = csv.reader(file)
        find_lines = []
        last_lines = reversed(list(reader)[lines:])
        for line in last_lines:
            if number in line:
                find_lines.append(line)
        return find_lines

def check_asterisk_answer() -> str:
    status = 'error'
    last_lines = read_cdr_file(-4)
    # Find needed information in file
    for line in last_lines:
        # line example ['2023-04-11 14:10:38', '79650483643', 'NO ANSWER', '30']
        if line[2] == 'NO ANSWER' and line[3] == exeption_time_of_call[0]:
            status = 'online'
        elif line[2] == 'ANSWERED':
            status = 'offline'
        elif line[2] == 'BUSY' and line[3] in exeption_time_of_call:
            status = 'offline'
        else:
            if operator == 'Megafon':
                status  = check_smsc_status(PARAMS_MEGAFON)
                logger.info(f"_Megafon sms status: {status}")
            else:
                status = check_smsc_status(PARAMS_RESELLER)
                logger.info(f"_Expensive sms status: {status}")
                if status == 'fail':
                    status = 'offline'
        break
    return status

if __name__ == "__main__":
    # Verify if the folder path is valid
    try:
        if not os.path.isdir(queuedir):
            logger.info(f"Invalid folder path!")
        else:
            # Get the last file in the folder
            last_file = os.listdir(queuedir)[-1]
    except IndexError:
        print(f"Queue folder empty!")
        exit(1)
        
    file_path = queuedir + last_file
    with open(file_path, 'r') as file:
        try:
            lines = file.readlines()
            cname = lines[0].strip()
            number = lines[1].strip()
            ctype = lines[2].strip()
            operator = lines[3].strip()
        except IndexError:
            operator = "No info"

    params_for_ping = {
        'phones': number,
        'ping': 1
    }

    logger.info(f"Start check number: {number}")

    make_call_file()

    remove_tmp_file()

    move_call_file_to_asterisk()

    sleep(config[stand]['timeout_befor_check_call'])

    status = check_asterisk_answer()
    logger.info(f"_Call status: {status}")

    # add sms status
    if operator:
        send_sms_to = "send sms to " + operator

    data = {
        "name": cname,
        "phone": number,
        "type": ctype,
        "status": status,
        "sms" : send_sms_to,
        "call_status": read_cdr_file(-2)
    }
    logger.info(f"_Data to send in Zabbix: {data}")

    if dev_stand is False:
        send_in_zabbix(data)

    logger.info(f"_Finish_")
