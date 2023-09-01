#!/usr/bin/python

'''
Скрипт смотрит smsс 4 раза в сутки и выбирает 10000 записей.
Далее выделяет смс-ки от БТ
Сравниваем полученный номер в телефонном справочнике и смски.
Если совпадает hostname, то ничего не делаем если не совпадает, то удаляем запись в БД и делаем новую.

Так же есть дополнительная проверка на hostname
'''

import json
import requests
import psycopg2 as pg
import re
import csv
from atlassian import Confluence

# clear file and return dict with empty set
def clean_zabbix_csv_file(filename: str) -> dict:
    data_list = []
    with open(filename, 'r') as file:
        csv_reader = csv.reader(file)
        for row in csv_reader:
            cell_value = row[0].split(';')
            try:
                if cell_value[1]:
                    data_list.append(cell_value[0].lower())
            except IndexError:
                continue
    return data_list

def format_phone_response(response: list) -> dict:
    output = {}
    dictionary = {}
    for val in response:
        for pair in val.split(', '):
            key, value = pair.split(' = ')
            dictionary[key] = value
        output[dictionary['name']] = dictionary['phone']
        #remove_trash = re.search(r'\{.*\}', dictionary['message']).group(0)
        #message = json.loads(re.search(r'\{.*\}', dictionary['message']).group(0))
    return output

def format_history_response(response: list) -> list:
    result = []
    dictionary = {}
    for val in response:
        for pair in val.split(', '):
            message = None
            try:
                key, value = pair.split(' = ')
            except Exception:
                continue
            dictionary[key] = value
            try:
                message = re.search(r'(LB|DK).\d+', dictionary['message']).group(0)
                phone = dictionary['phone']
            except Exception:
                continue
        if message:  
            result.append({'message': message, 'phone': phone})
    return result

def find_errors_in_name(check_dict: dict) -> list:
    result = []
    for val in check_dict:
        if 'hostname' not in val:
            write_to_file('Найден комплекс без контакта: ' + str(val))
            continue
        if val['message'][:-1].lower() != val['hostname'].split('-')[0][:-1].lower():
            write_to_file("Строки не совпадают в нижнем регистре: " + str(val))
        else:
            result.append(val)
    return result

def write_to_file(content) -> None:
        with open(ATTACHMENT_FILE, "a") as file:
            file.write(content + "\n")

def find_contacts_with_verison_app(zabbix_hosts: list, contacts: dict) -> dict:
    clear_contacts = {}
    for host in zabbix_hosts:
        for key, value in contacts.items():
            if host == key.lower():
                clear_contacts[key.lower()] = value
    return clear_contacts

ATTACHMENT_FILE = 'data.txt'

def main():
    
    with open("config.json") as input_cfg:
        config = json.load(input_cfg)
    
    confluence_url = config["confluence"]["confluence_url"]
    confluence_host_version_url = config["confluence"]["confluence_file_url"]
    confluence_user = config["confluence"]["user"]
    confluence_pass = config["confluence"]["password"]
    confluence_space = config["confluence"]["space"]
    confluence_page = config["confluence"]["page"]
    
    file_path_zabbix = config["hosts_file_name"]

    smsc_login = config["smsc_login"]
    smsc_pass = config["smsc_pass"]

    # make session
    session = requests.Session()
    session.auth = (confluence_user, confluence_pass)

    # download and save file
    response = session.get(confluence_host_version_url)
    response.raise_for_status()

    with open(file_path_zabbix, "wb") as file:
        file.write(response.content)

    clear_zabbix_list = clean_zabbix_csv_file(file_path_zabbix)
    #print(clear_zabbix_dict)
    print("Найдено уникальных хостов в zabbix: " + str(len(clear_zabbix_list)))

    #clean file
    with open(ATTACHMENT_FILE, "w") as file:
            file.write("")
    # paramets for request
    params_hostory = {
        "get_answers":"1",          # default paramet to take the answer
        "hour":"24",                # how many hours we will see
        "cnt":"10000",              # how many message we want to see ( maximum limit 10000 )
        "login":smsc_login,
        "psw":smsc_pass
    }

    contact_dict = []
    request_history = requests.get(config["smsc_history_url"],params=params_hostory)
    response_history = list(request_history.iter_lines(decode_unicode=True))
    print("Найдено записей в истории: " + str(len(response_history)))
    find_bt_in_response = [line for line in response_history if 'BT V' in line]
    history_dict = format_history_response(find_bt_in_response)

    request_contacts = requests.get(config["smsc_contacts_url"],params={"get": '1', 'login': params_hostory["login"], 'psw': params_hostory["psw"]})
    response_contacts = list(request_contacts.iter_lines(decode_unicode=True))
    contact_dict = format_phone_response(response_contacts)

    contacs_for_update = find_contacts_with_verison_app(clear_zabbix_list, contact_dict)
    print("Найдено контактов для обновления в БД: " + str(len(contacs_for_update)))

    # add hostname in history_dict
    for item in history_dict:
        phone = item['phone']
        for key, value in contact_dict.items():
            if value == phone:
                item['hostname'] = key
                break

    update_info = find_errors_in_name(history_dict)
    # block connect to db and write data
    conn = pg.connect(
    host=config["postgress"]["address"],
    port=config["postgress"]["port"],
    database=config["postgress"]["db"],
    user=config["postgress"]["login"],
    password=config["postgress"]["pass"]
    )
    cursor = conn.cursor()

    for hostname, phone in contacs_for_update.items():
        query = f"UPDATE analitics_zabbix_smsc_bt_phones SET phone = '{phone}' WHERE hostname = '{hostname}'"
        cursor.execute(query)
        print("Запись добавлена из контактов")
    
    conn.commit()

    for record in update_info:
        phone = record['phone']
        hostname = record['hostname'].lower()

        cursor.execute("SELECT * FROM analitics_zabbix_smsc_bt_phones WHERE phone = %s", (phone,))
        existing_record = cursor.fetchone()

        if existing_record:
            if existing_record[0] != hostname:
                cursor.execute("DELETE FROM analitics_zabbix_smsc_bt_phones WHERE phone = %s", (phone,))
                cursor.execute("INSERT INTO analitics_zabbix_smsc_bt_phones (hostname, phone, last_update) VALUES (%s, %s, CURRENT_TIMESTAMP)", (hostname, phone))
                print("Запись обновлена")
            else:
                print("Запись уже существует и hostname совпадает")
        else:
            cursor.execute("DELETE FROM analitics_zabbix_smsc_bt_phones WHERE hostname = %s", (hostname,))
            cursor.execute("INSERT INTO analitics_zabbix_smsc_bt_phones (hostname, phone, last_update) VALUES (%s, %s, CURRENT_TIMESTAMP)", (hostname, phone))
            print("Новая запись добавлена")

    # close connection
    conn.commit()
    cursor.close()
    conn.close()

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

if __name__ == '__main__':
    main()


    #ignore LBL00001