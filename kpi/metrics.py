#!/usr/bin/python3
# -*- coding: utf-8 -*-

import psycopg2 as pg
import configparser
import pygsheets as gs
import datetime as time
import argparse
from sys import exit

CHART_NAME = "График"
SD_GROUPS = {
    '-c': 'ЦУИМ',
    '-o': 'ОСА',
    'section_cuim': 'googlesheets-cuim',
    'section_oca': 'googlesheets-oca'
}
# Создание парсера аргументов командной строки
parser = argparse.ArgumentParser(description='Полученние данных из SD по группам.')

# Добавление аргументов
parser.add_argument('-c', action='store_true', help='Заявки ЦУИМ')
parser.add_argument('-o', action='store_true', help='Заявки ОСА')

# Парсинг аргументов
args = parser.parse_args()

if args.c:
    search_group = SD_GROUPS['-c']
    section = SD_GROUPS['section_cuim']
elif args.o:
    search_group = SD_GROUPS['-o']
    section = SD_GROUPS['section_oca']
else:
    print("Не указан аргумент")
    exit(1)

# Описание тестовой среды
dev = False
prod_ini = "metrics.ini"
dev_ini = "metrics.ini.test"
prod_google_cred = "google_credentials.json"
dev_google_cred = "google_credentials.json.test"
google_cred = ""
config_ini = ""

if dev:
    google_cred = dev_google_cred
    config_ini = dev_ini
else:
    google_cred = prod_google_cred
    config_ini = prod_ini

def getConfig(file=config_ini, section=None, default={}):
#def getConfig(file='metrics.ini', section=None, default={}):
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

def getDateSlice():
    # Время смещено из-за временного лага в БД (~3ч) и из-за задержек между интервалами запуска скрипта
    today = time.date.today() - time.timedelta(days=1)
    start = today - time.timedelta(days=today.weekday())
    end = start + time.timedelta(days=6)

    # print('{} {} {}'.format(today, start, end))
    return start, end

def getWorksheet(table, title):
    for worksheet in table.worksheets():
        if (worksheet.title == title):
            return worksheet
    return table.add_worksheet(title, index=1)

try:
    metrics = [['title', 'count', 'maintenance']]
    tasksCount = 0
    pgCon = False
    
    timeStart, timeEnd = getDateSlice()

    with open('metrics.sql', 'r', encoding='utf-8') as fsql:
        # Postgres
        pgCon = pg.connect(**getConfig(section='postgresql'))
        pgCur = pgCon.cursor()
        pgCur.execute(fsql.read().format(
            timeStart=timeStart,
            timeEnd=timeEnd,
            search_group=search_group
        ))

        for (title, count, maintenance) in pgCur.fetchall():
            # print("{title}: {count} {maintenance}".format(title=title, count=count, maintenance=maintenance))
            metrics.append([title, count, maintenance])
            tasksCount += count        

        if not len(metrics):
            raise Exception('Не получено данных в ходе выполнения запроса к БД')

    # Google
    gconfig = getConfig(section=section, default={
        'worksheets': 8
    })

    if 'sheetid' not in gconfig or not len(gconfig['sheetid']):
        raise Exception('Не указан id таблицы в Google документах')

    gCur = gs.authorize(service_file=google_cred)
    table = gCur.open_by_key(gconfig['sheetid'])
    tab = getWorksheet(table, '{} {}'.format(timeStart, timeEnd))

    tab.clear()
    tab.resize(len(metrics) + 3, 10)

    try:
        tab.update_value('B1', tasksCount)
        tab.append_table(values=metrics, start='A2', overwrite=True)
    except Exception as error:
        print('')
    
    # Создание вкладки График
    try:
        chart = table.worksheet_by_title(CHART_NAME)
    except Exception as error:
        table.add_worksheet(CHART_NAME)
        chart = table.worksheet_by_title(CHART_NAME)

    # Очистка данных вкладки График
    chart.clear()
    for ch in chart.get_charts():
        gs.Chart.delete(ch)

    # Удаление вкладок выходящих за лимит отчета + получение данных для графика
    chart_len = len(table.worksheets())
    for tab in table.worksheets():
        if tab.title != CHART_NAME:
            cell_number_str = str((chart_len - tab.index + 1))
            start_date, end_date = tab.title.split(" ")
            chart.update_value('A'+ cell_number_str, start_date)
            chart.update_value('B'+ cell_number_str, end_date)
            chart.update_value('C'+ cell_number_str, tab.cell('B1').value)
        if (tab.index > int(gconfig['worksheets']) and tab.title != CHART_NAME):
            table.del_worksheet(tab)
            print('Удаление устарешвей вкладки "{}"'.format(tab.title))

    # Создание графика
    column_chart = chart.add_chart(('B1', 'B9'), [('C1', 'C9')],title = 'Количество заявок по неделям',anchor_cell='A1')

except Exception as error:
    print(error)
finally:
    if pgCon:
        pgCon.close()
    fsql.close()