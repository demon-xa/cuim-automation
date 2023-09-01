#!/usr/bin/python

'''
скрипт полу-ручной
скрипт берет данные по хостам со страницы конфлюенса об обновлениях ПО.
оставляет только названия хостов. Точность 98,5%  (1848 из 1885 хостов в файле)
с свйта smsc надо выбрать историю за период и сохранить в файл sms_answers.csv
после запустить скрипт и он заполнит таблицу.
'''

import json
import requests
import csv
import psycopg2 as pg

# clear file and return dict with empty set
def clean_zabbix_csv_file(filename: str) -> dict:
    data_dict = {}
    with open(filename, 'r') as file:
        csv_reader = csv.reader(file)
        for row in csv_reader:
            cell_value = row[0].split(';')
            try:
                if cell_value[1]:
                    if '-pc' in cell_value[0]:
                        find_cell = cell_value[0].split('-')[0]
                        data_dict[find_cell.upper()] = None
                    else:
                        data_dict[cell_value[0].upper()] = None
            except IndexError:
                continue
    return data_dict

def clear_smsc_csv_file(filename: str) -> dict:
    data_dict = {}
    exeption_names = ['UNKNOWN', 'TST§§000', 'BT', 'TEST', 'unknown', 'test']
    with open(filename, 'r', encoding='cp1251') as file:
        csv_reader = csv.reader(file)
        for row in csv_reader:
            cell_value = row[0].split(';')
            #print(cell_value)
            try:
                if 'BT V' in cell_value[3]:
                    find_cell = cell_value[3].strip('"').lstrip().split()
                    if find_cell[0] not in exeption_names:
                        data_dict[find_cell[0].upper()] = cell_value[1]
            except Exception as error:
                print(error)
    return data_dict


def main():
    final_dict = {}
    
    with open("config.json") as input_cfg:
        config = json.load(input_cfg)
    
    url = config["confluence_file_url"]
    file_path_zabbix = config["hosts_file_name"]
    file_path_smsc = config["smsc_file"]
    username = config["confluence_user"]
    password = config["confluence_pass"]

    # make session
    session = requests.Session()
    session.auth = (username, password)

    # download and save file
    response = session.get(url)
    response.raise_for_status()

    with open(file_path_zabbix, "wb") as file:
        file.write(response.content)

    clear_zabbix_dict = clean_zabbix_csv_file(file_path_zabbix)
    #print(clear_zabbix_dict)
    print("Найдено уникальных хостов в zabbix: " + str(len(clear_zabbix_dict)))

    clear_smsc_dict = clear_smsc_csv_file(file_path_smsc)
    print("Найдено уникальных хостов в smsc: " + str(len(clear_smsc_dict)))

    # diff 2 dict
    for key in clear_smsc_dict:
        if key in clear_zabbix_dict:
            clear_zabbix_dict[key] = clear_smsc_dict[key]
    # get final dict
    for key, value in clear_zabbix_dict.items():
        if value is not None:
            final_dict[key] = value
    print("Итого найдено телефонов: " + str(len(final_dict)))

    # block connect to db and write data
    conn = pg.connect(
    host=config["postgress"]["address"],
    port=config["postgress"]["port"],
    database=config["postgress"]["db"],
    user=config["postgress"]["login"],
    password=config["postgress"]["pass"]
    )
    cur = conn.cursor()
    values = [(key, value) for key, value in final_dict.items()]
    query = "INSERT INTO {} (hostname, phone) VALUES (%s, %s) ON CONFLICT (hostname) DO NOTHING".format(config["postgress"]["table_smsc"])
    cur.executemany(query, values)

    # close connection
    conn.commit()
    cur.close()
    conn.close()

    
if __name__ == '__main__':
    main()