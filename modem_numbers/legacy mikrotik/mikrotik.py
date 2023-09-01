#!/usr/bin/python3
# -*- coding: utf-8 -*-

from routeros import *
import time
import json
import configparser
import psycopg2 as pg

def getConfig(file='mikrotik.ini', section=None, default={}):
    if (section is None):
        raise Exception('Не задана секция конфига {0} для чтения параметров'.format(file))
    
    config = default if len(default) else {}
    parser = configparser.RawConfigParser()
    parser.read(file)

    if (parser.has_section(section)):
        for (var, val) in parser.items(section):
            config[var] = val
    else:
        raise Exception('Не найдена секция {s} в файле {f}'.format(s=section, f=file))
    return config

while True:
    try:
        print('connect to Postgres')
        pgCon = pg.connect(**getConfig(section='postgresql'))
        pgCur = pgCon.cursor()

        print('connect to Mikrotik')
        routeros = login(**getConfig(section='mikrotik'))
        while True:
            # 
            for sms in routeros('/tool/sms/inbox/print', '?>phone='):
                print(sms)
                try:
                    message = json.loads(sms['message'])
                except Exception as error:
                    # Удялем все сообщения не содержащие json объект
                    print(error)
                    routeros('/tool/sms/inbox/remove', '=.id={}'.format(sms['.id']))
                    continue
                # В случае ошибки добавления записи в БД, исключение приведет к попытке переподключения 
                if 'type' in message and 'hostname' in message:
                    match message['type']:
                        case 'mikrotik':
                            if 'uicc' in message and 'operator' in message and 'serial' in message:
                                pgCur.execute("call set_mikrotik(%(hostname)s,%(phone)s,%(uicc)s,%(operator)s,%(serial)s)", {
                                    'hostname': message['hostname'],
                                    'phone': sms['phone'],
                                    'uicc': message['uicc'],
                                    'operator': message['operator'],
                                    'serial': message['serial']
                                })
                                pgCon.commit()
                        case 'immodem':
                            if 'uicc' in message and 'operator' in message:
                                pgCur.execute("call set_immodem(%(hostname)s,%(phone)s,%(uicc)s,%(operator)s)", {
                                    'hostname': message['hostname'],
                                    'phone': sms['phone'],
                                    'uicc': message['uicc'],
                                    'operator': message['operator']
                                })
                                pgCon.commit()
                # Удаление сообщения после добавления в БД
                routeros('/tool/sms/inbox/remove', '=.id={}'.format(sms['.id']))
            time.sleep(1)
    except Exception as error:
        print(error)
    finally:
        if pgCon:
            pgCon.close()
        if routeros:
            routeros.close()
        time.sleep(30)
