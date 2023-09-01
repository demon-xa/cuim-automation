#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Описание:
Читаем полученные смс от комплексов. Ищем нужные json и записываем в csv file.

Автор: Dmitrii Seldev
Дата: 19.04.2023
Версия: 0.1
"""

import requests
import json
from pprint import pprint
import csv
import re
#import psycopg2 as pg

def format_response(respose: list) -> list:
    output = []
    dictionary = {}
    for val in respose:
        for pair in val.split(', '):
            key, value = pair.split(' = ')
            dictionary[key] = value
        #remove_trash = re.search(r'\{.*\}', dictionary['message']).group(0)
        message = json.loads(re.search(r'\{.*\}', dictionary['message']).group(0))
        output.append((message['hostname'], dictionary['phone'], message['uicc'], message['operator'], dictionary['sent']))
    return output


def main():
    with open("config.json") as input_cfg:
        config = json.load(input_cfg)

    # paramets for request
    params = {
        "get_answers":"1",          # default paramet to take the answer
        "hour":"24",                 # how many hours we will see
        "cnt":"10000",              # how many message we want to see ( maximum limit 10000 )
        "login":config["login"],
        "psw":config["password"]
    }

    #test_list = ('id = 344826327, received = 20.04.2023 14:58:54, phone = 79991192384, message = {"operator":"MegaFon","hostname":"osa-test-complex","type":"immodem","uicc":"897010210934202385"}, to_phone = 79315906271, sent = 20.04.2023 14:58:50', 'id = 344826318, received = 20.04.2023 14:58:42, phone = 79991192384, message = {"operator":"MegaFon","type":"immodem","uicc":"897010210934202385","hostname":"osa-test-complex"}, to_phone = 79315906271, sent = 20.04.2023 14:58:38', 'id = 344824299, received = 20.04.2023 14:24:53, phone = 79991192384, message = {"uicc":"897010210934202385","hostname":"osa-test-complex","operator":"MegaFon","type":"immodem"}, to_phone = 79315906271, sent = 20.04.2023 14:24:49')
    parsering_val = []
    try:
        request = requests.get(config["read_smsc_url"],params=params)
        response = list(request.iter_lines(decode_unicode=True))
        find_json_in_response = [line for line in response if '{"' in line]
        parsering_val = format_response(find_json_in_response)
        with open('output5.csv', 'a', newline='') as file:
            writer = csv.writer(file, delimiter=';')
            for row in parsering_val:
                writer.writerow(row)
    except Exception as error:
        print(error)


if __name__ == '__main__':
    main()