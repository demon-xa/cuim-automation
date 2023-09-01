#!/usr/bin/python

import json
import csv
import requests
from pprint import pprint
import re
import psycopg2 as pg
from psycopg2.extensions import AsIs
from sys import exit
from time import sleep
from atlassian import Confluence
from datetime import datetime


# Global variables
with open("config.json") as input_cfg:
    config = json.load(input_cfg)

template_text = ['BT V','SIM NUMBER','{']
# smsc vars
smsc_login = config["smsc"]["login"]
smsc_pass = config["smsc"]["pass"]
limit_counts = config["smsc"]["limit_counts"]
smsc_history_url = config["smsc"]["history_url"]
smsc_contacts_url = config["smsc"]["contacts_url"]
smsc_operator_url = config["smsc"]["sim_info"]
requests_per_minute = config["smsc"]["limit_for_requests_operator"]
interval = 60 / requests_per_minute
#postgres vars
host=config["postgress"]["address"]
port=config["postgress"]["port"]
database=config["postgress"]["db"]
user=config["postgress"]["login"]
password=config["postgress"]["pass"]
db_phone_table = config["postgress"]['table_phones']
#confluence
confluence_url = config["confluence"]["confluence_url"]
confluence_user = config["confluence"]["user"]
confluence_pass = config["confluence"]["password"]
confluence_space = config["confluence"]["space"]
confluence_page = config["confluence"]["page"]
ATTACHMENT_FILE = 'comp_errors'

operators = {
'megafon': 'мегафон',
'tele2': 'теле2',
'mts': 'мтс',
'rostelecom': 'ростеле',
'beeline': 'билайн'
}   

# send request to smsc
def smsc_query(url: str, params: dict) -> list:
    request = requests.get(url, params)
    if request.status_code == 200:
        response = list(request.iter_lines(decode_unicode=True))
        if 'ERROR = ' in response[0]:
            exit("ERROR request to smsc")
        return response
    else:
        print(f"Error. Code response: {request.status_code}")
        exit("ERROR request to smsc")


# make list hostname, phone, type [{'message': 'lbp08061', 'phone': '79319737247', 'type': 'bt'},]
def format_response(response: list) -> list:
    result =[]
    dictionary = {}
    for line in response:
        line = line.replace(', received', ' ,;, received').replace(', phone',' ,;, phone').replace(', message',' ,;, message').replace(', to_phone',' ,;, to_phone').replace(', sent', ' ,;, sent')
        for pair in line.split(' ,;, '):
            try:
                key, value = pair.split(' = ')
            except Exception as error:
                #print(error)
                continue
            dictionary[key] = value
        try:
            message = None
            device_type = None
            phone = dictionary['phone']
            sent = dictionary['sent']
            # check on BT V
            if template_text[0] in dictionary['message']:
                message = re.search(r'(LB|DK).\d+', dictionary['message']).group(0).lower()
                device_type = 'bt'
            # check on SIM NUMBER
            elif template_text[1] in dictionary['message']:
                message = dictionary['message'].split()[6].lower()
                device_type = 'bt'
            # check on Mikrotik
            elif template_text[2] in dictionary['message']:
                #print(dictionary['message'])
                data = json.loads(re.search(r'\{.*\}', dictionary['message']).group(0))
                message = data['hostname']
                device_type = data['type']
            if message:
                result.append({'message': message, 'phone': phone, 'type': device_type, 'sent': sent})
            dictionary.clear()
        except Exception as error:
            #print(error)
            continue
    return result
    
# get complex with APP number
def get_actual_terminals(filename: str) -> list:
    actual_list = []
    with open(filename, 'r') as file:
        csv_reader = csv.reader(file)
        for row in csv_reader:
            cell_value = row[0].split(';')
            try:
                if cell_value[1]:
                    actual_list.append(cell_value[0].lower())
            except IndexError:
                continue
    return actual_list

# remove old data
def remove_old_sms(sms_list: list, last_time_sms: str) -> list:
    filtered_list = [sms for sms in sms_list if sms['sent'] >= last_time_sms]
    return filtered_list

def check_operator(phone: str) -> str:
    data = {}
    url = f"{smsc_operator_url}?get_operator=1&login={smsc_login}&psw={smsc_pass}&phone={phone}"
    response = requests.get(url)
    pairs = response.text.split(', ')
    for pair in pairs:
        key, value = pair.split(' = ')
        data[key] = value
    for key in operators:
        if operators[key] in data['operator'].lower():
            operator = key
    sleep(interval)
    return operator

def is_file_empty(file_path):
    with open(file_path, 'r') as file:
        content = file.read()
        return len(content) == 0

def main():

    actual_terminals = get_actual_terminals(config["hosts_file_name"])    
    print(f"Find the count of complexes in Zabbix with installed APP: {len(actual_terminals)}")

    params_history = {
    "get_answers":"1",          # default paramet to take the answer
    "hour":"1",                # how many hours we will see ( maximum limit 72 )
    "cnt":limit_counts,         # how many message we want to see ( maximum limit 10000 )
    "login":smsc_login,
    "psw":smsc_pass  }

    smsc_history = smsc_query(smsc_history_url,params_history)
    history_list = format_response(smsc_history)
    last_time_sms = None
    # read/write last reading time
    try:
        with open('last_time_sms', 'r') as file:
            last_time_sms = file.read()
        with open('last_time_sms', 'w') as file:
            file.write(history_list[0]['sent'])
    except Exception:
        print("can't rw file")

    history_list = remove_old_sms(history_list,last_time_sms)
    unique_history_list = [dict(t) for t in {tuple(sorted(d.items())) for d in history_list}]
    
    # make 2 list. Terminals with\without errors
    complex_with_hostname = []
    error_names_in_sms = []

    for item in unique_history_list:
        message = item['message']
        for name in actual_terminals:
            if message in name:
                item['hostname'] = name
                item['operator'] = check_operator(item['phone'])
                complex_with_hostname.append(item)
                break
        else:
            error_names_in_sms.append(item)

    if error_names_in_sms:
        with open(ATTACHMENT_FILE, 'a') as file:
            for item in error_names_in_sms:
                file.write(json.dumps(item) + '\n')
            file.write('\n')
        print("\nTerminals with errors in names:\n")
        pprint(error_names_in_sms)
    if complex_with_hostname:
        print("\nTerminal without errors in names:\n")
        pprint(complex_with_hostname)


    conn = pg.connect( host=host, port=port, database=database, user=user, password=password )
    cursor = conn.cursor()
    for record in complex_with_hostname:
        phone = record['phone']
        hostname = record['hostname']
        type = record['type']
        operator = record['operator']
        
        cursor.execute("SELECT * FROM %s WHERE hostname = %s and type = %s", (AsIs(db_phone_table), hostname, type))
        existing_record = cursor.fetchone()

        if existing_record:
            if existing_record[1] != phone:
                cursor.execute("UPDATE %s SET phone = %s, operator = %s, last_update = CURRENT_TIMESTAMP WHERE hostname = %s and type = %s", (AsIs(db_phone_table), phone, operator, hostname, type))
                print(f"Update record in db. hostname: {hostname} type: {type} phone: {phone}")
                with open(ATTACHMENT_FILE, 'a') as file:
                    file.write(f"Update phone hostname: {hostname} type: {type} phone: {phone}\n")
            else:
                cursor.execute("UPDATE %s SET last_update = CURRENT_TIMESTAMP WHERE hostname = %s and type = %s", (AsIs(db_phone_table), hostname, type))
                print(f"We already have this hostname: {hostname} type: {type} in db. Update time")
        else:
            cursor.execute("INSERT INTO %s (hostname, phone, type, operator, last_update) VALUES (%s, %s, %s, %s,CURRENT_TIMESTAMP)", (AsIs(db_phone_table), hostname, phone, type, operator))
            print(f"Add new record in db. hostname: {hostname} type: {type} phone: {phone}")

    # close connection
    conn.commit()
    cursor.close()
    conn.close()

    current_time = datetime.now().time()
    if current_time.hour == 8 and current_time.minute == 0 and not is_file_empty(ATTACHMENT_FILE):     
        # copy file in confluence
        # Check connection and namespace and page
        try:
            confluence = Confluence(url = confluence_url, username = confluence_user, password = confluence_pass)
        except Exception as e:
            print("Не могу соединится с confluence по адресу: " + confluence_url)
            print(e)
        page_ID = confluence.get_page_id(confluence_space, confluence_page)
        if page_ID is None:
            print("Страница не найдена: " + confluence_page + " в пространстве " + confluence_space)
            exit()
        else:
            print ("Найдена страница : " + confluence_page + " page_ID: " + str(page_ID) )
        
        # add content
        body_part_1 = "Лог проверки"
        body_part_1 = body_part_1 + '  <p><a href="http://conf.grav.su/download/attachments/' + page_ID + '/' + ATTACHMENT_FILE + '">' + ATTACHMENT_FILE + '</a></p>'
        # try write data
        try:
            confluence.update_page(page_ID, confluence_page, str(body_part_1), parent_id=None, type='page', representation='storage', minor_edit=False)
            # remove old attachment
            confluence.delete_attachment(page_id = page_ID, filename = ATTACHMENT_FILE)
            # add attachment
            confluence.attach_file(filename = ATTACHMENT_FILE,  page_id = page_ID)
        except Exception as e:
            print("Я не могу обновить страницу page_ID " + str(page_ID))
            print("Убедитесь что страница существует")
        #clear file
        with open('ATTACHMENT_FILE', 'w') as file:
            file.write("")

if __name__ == '__main__':
    main()