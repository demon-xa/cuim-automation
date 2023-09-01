#!/usr/bin/python

from pyzabbix import ZabbixAPI
from collections import Counter
import json
from atlassian import Confluence
import re
import csv
import time

#open config file
with open("config.json") as input_cfg:
    config = json.load(input_cfg)

#Zabbix connect
one_mounth_unix_time = 2629743  # 1 месяц (30.44 дней)
last_mounth_unix_time = int(time.time()) - one_mounth_unix_time
ATTACHMENT_FILE = "host_version.csv"
ACCESS_TOKEN = config["zabbix_access_key"]
zapi = ZabbixAPI(config["zabbix_url"])
zapi.login(api_token=ACCESS_TOKEN)

#Get list version and dict
full_inv_dict = {}
list_versions = []

# Get host info. Then check every host at last mounth update.
for item in zapi.host.get(output="extend", selectInventory=True):
    try:
        host = item['host']
        soft_version = re.sub('lob\.|dec\.|kop\.','',item["inventory"]["software_app_e"])
        for var in zapi.item.get(output="extend", hostids=item["hostid"], search={"name": "api_version"}):
            if int(var["lastclock"]) > last_mounth_unix_time:
                list_versions.append(soft_version)
        full_inv_dict[host] = soft_version
    except:
        continue

with open(ATTACHMENT_FILE, 'w') as output:
    writer = csv.writer(output, delimiter=';',)
    for key, value in full_inv_dict.items():
        writer.writerow([key, value])

# Make calculation and remove empty
sum_version = dict(Counter(list_versions))
try:
  del sum_version[""]
except KeyError:
  pass

# section confluence
confluence_url = config["confluence_url"]
confluence_user = config["user"]
confluence_pass = config["password"]
confluence_space = config["space"]
confluence_page = config["page"]

# Check connection and namespace and page
try:
    confluence = Confluence(url=confluence_url,username=confluence_user,password=confluence_pass)
except Exception as e:
    print("Не могу соединится с confluence по адресу: " + confluence_url)
    print(e)
page_ID=confluence.get_page_id(confluence_space, confluence_page)
if page_ID is None:
    print("Страница не найдена: " + confluence_page + " в пространстве " + confluence_space)
    exit()
else:
    print ("Найдена страница : " + confluence_page + " page_ID: " + str(page_ID) )

# add content
chart_heading = "Количество терминалов"
bodyPart_1 = ""
bodyPart_2 = "" 
bodyPart_3 = ""
bodyPart_1 = bodyPart_1 + '  <p><a href="http://conf.grav.su/download/attachments/59016085/'+ ATTACHMENT_FILE + '">' + ATTACHMENT_FILE + '</a></p>'
bodyPart_1 = bodyPart_1 + "<ac:structured-macro ac:name=\"chart\" ac:schema-version=\"1\" ac:macro-id=\"03427ec1-7dcf-4b60-a195-3c0b80e63ae7\">"
bodyPart_1 = bodyPart_1 + "  <ac:parameter ac:name=\"timeSeries\">false</ac:parameter>"
bodyPart_1 = bodyPart_1 + "  <ac:parameter ac:name=\"orientation\">vertical</ac:parameter>"
bodyPart_1 = bodyPart_1 + "  <ac:parameter ac:name=\"dataDisplay\">after</ac:parameter>"
bodyPart_1 = bodyPart_1 + "  <ac:parameter ac:name=\"showShapes\">false</ac:parameter>"
bodyPart_1 = bodyPart_1 + "  <ac:parameter ac:name=\"dateFormat\">yyyy/MM/dd</ac:parameter>"
bodyPart_1 = bodyPart_1 + "  <ac:parameter ac:name=\"timePeriod\">Second</ac:parameter>"
bodyPart_1 = bodyPart_1 + "  <ac:parameter ac:name=\"width\">1000</ac:parameter>"
bodyPart_1 = bodyPart_1 + "  <ac:parameter ac:name=\"dataOrientation\">vertical</ac:parameter>"
bodyPart_1 = bodyPart_1 + "  <ac:parameter ac:name=\"title\">" + chart_heading + "</ac:parameter>"
bodyPart_1 = bodyPart_1 + "  <ac:parameter ac:name=\"type\">bar</ac:parameter>"
bodyPart_1 = bodyPart_1 + "  <ac:rich-text-body>"
bodyPart_1 = bodyPart_1 + "      <table class=\"wrapped\">"
bodyPart_1 = bodyPart_1 + "          <colgroup><col /><col /><col /></colgroup>"
bodyPart_1 = bodyPart_1 + "      <tbody><tr><th>Версия прошивки</th><th>" + chart_heading + "</th></tr>"
for k,v in sum_version.items(): 
    bodyPart_2 = bodyPart_2 + "\n                 <tr><td><div class=\"content-wrapper\"><p>" + str(k) + "</p></div></td><td>" + str(v) + "</td></tr>"

bodyPart_3 = "      </tbody></table></ac:rich-text-body></ac:structured-macro>"

data = bodyPart_1 + bodyPart_2 + bodyPart_3

# try write data
try:
    # write chart
    status=confluence.update_page(page_ID, confluence_page, data, parent_id=None, type='page', representation='storage', minor_edit=False)
    # remove old attachment
    confluence.delete_attachment(page_id=page_ID,filename=ATTACHMENT_FILE)
    # add attachment
    attach=confluence.attach_file(ATTACHMENT_FILE,page_id=page_ID, space=confluence_space)
except Exception as e:
    print("Я не могу обновить страницу page_ID " + str(page_ID))
    print("Убедитесь что страница существует")
 
