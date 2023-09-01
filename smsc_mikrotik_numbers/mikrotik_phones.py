#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Описание:
запускаем 4 раза в сутки
Читаем полученные смс от комплексов. Ищем нужные json и записываем в db.

Автор: Dmitrii Seldev
Дата: 18.05.2023
Версия: 0.1
"""

import requests
import json
import re
import psycopg2 as pg

def format_response(respose: list) -> list:
    output = []
    dictionary = {}
    for val in respose:
        for pair in val.split(', '):
            key, value = pair.split(' = ')
            dictionary[key] = value
        #remove_trash = re.search(r'\{.*\}', dictionary['message']).group(0)
        message = json.loads(re.search(r'\{.*\}', dictionary['message']).group(0))
        output.append((message['hostname'], dictionary['phone'], message['uicc'], message['operator'], message['serial']))
    return output


def main():
    with open("config.json") as input_cfg:
        config = json.load(input_cfg)

    # paramets for request
    params = {
        "get_answers":"1",          # default paramet to take the answer
        "hour":"24",                # how many hours we will see
        "cnt":"10000",              # how many message we want to see ( maximum limit 10000 )
        "login":config["login"],
        "psw":config["password"]
    }
    
    parsering_val = []
    try:
        request = requests.get(config["read_smsc_url"],params=params)
        response = list(request.iter_lines(decode_unicode=True))
        find_json_in_response = [line for line in response if '{"' in line]
        parsering_val = format_response(find_json_in_response)
    except Exception as error:
        print(error)

    # block connect to db and write data
    conn = pg.connect(
    host=config["postgress"]["address"],
    port=config["postgress"]["port"],
    database=config["postgress"]["db"],
    user=config["postgress"]["login"],
    password=config["postgress"]["pass"]
    )
    cursor = conn.cursor()

    print(len(parsering_val))
    for record in parsering_val:
        operators = ('megafon', 'tele2', 'mts', 'rostelecom', 'beeline')
        strange_name = ['25001', 25001]
        hostname = record[0].lower()
        phone = record[1]
        uicc = record[2]
        operator = record[3].lower()
        serial = record[4]

        for rec in operators:
            if rec in operator:
                operator = rec
                break
        if operator in strange_name:
            operator = operators[2]
        
        cursor.execute("SELECT * FROM analitics_zabbix_smsc_mikrotik_phones WHERE phone = %s", (phone,))
        existing_record = cursor.fetchone()

        if existing_record:
            if existing_record[0] != hostname:
                cursor.execute("DELETE FROM analitics_zabbix_smsc_mikrotik_phones WHERE phone = %s", (phone,))
                cursor.execute("INSERT INTO analitics_zabbix_smsc_mikrotik_phones (hostname, phone, uicc, operator, serial) VALUES (%s, %s, %s, %s, %s)", (hostname, phone, uicc, operator, serial))
                print("Запись обновлена")
            else:
                print("Запись уже существует и hostname совпадает")
        else:
            cursor.execute("DELETE FROM analitics_zabbix_smsc_mikrotik_phones WHERE hostname = %s", (hostname,))
            cursor.execute("INSERT INTO analitics_zabbix_smsc_mikrotik_phones (hostname, phone, uicc, operator, serial) VALUES (%s, %s, %s, %s, %s)", (hostname, phone, uicc, operator, serial))
            print("Новая запись добавлена")

    # close connection
    conn.commit()
    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()