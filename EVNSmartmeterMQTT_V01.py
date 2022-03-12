import serial
import time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from binascii import unhexlify
import sys
import string
from gurux_dlms.GXDLMSTranslator import GXDLMSTranslator
from bs4 import BeautifulSoup
from Cryptodome.Cipher import AES
from time import sleep
from gurux_dlms.TranslatorOutputType import TranslatorOutputType

import json
import os
import getopt

try:
	configFile = open(os.path.dirname(os.path.realpath(__file__)) + '/config.json')
	config = json.load(configFile)
except:
	print("config.json file not found!")
	sys.exit(1)

verbose = 0
try:
    opts, args = getopt.getopt(sys.argv[1:],"v")
except getopt.GetoptError:
    print('test.py [-v]')
    sys.exit(2)
for opt, arg in opts:
    if opt == '-v':
        verbose = 1

# config Kontrolle
neededConfig = ['port', 'baudrate', 'printValue', 'useMQTT', 'evn_schluessel']
for conf in neededConfig:
    if conf not in config:
        print(conf + ' missing in config file!')
        sys.exit(3)

MQTTneededConfig = ['MQTTBroker', 'MQTTuser', 'MQTTpasswort', 'MQTTport']
if config['useMQTT']:
    for conf in neededConfig:
        if conf not in config:
            print(conf + ' missing in config file!')
            sys.exit(3)


# Holt Daten von serieller Schnittstelle
def recv(serialIncoming):
    while True:
        data = serialIncoming.read_all()
        if data == '':
            continue
        else:
            break
        sleep(0.5)
    return data

# Konvertiert Signed Ints
def s16(value):
    val = int(value, 16)
    return -(val & 0x8000) | (val & 0x7fff)

def s8(value):
    val = int(value, 16)
    return -(val & 0x80) | (val & 0x7f)

# DLMS Blue Book Page 52
# https://www.dlms.com/files/Blue_Book_Edition_13-Excerpt.pdf
units = {
            27: "W", # 0x1b
            30: "Wh", # 0x1e
            33: "A", #0x21
            35: "V", #0x23
            255: "" # 0xff: no unit, unitless
}


#MQTT Init
if config['useMQTT']:
    import paho.mqtt.client as mqtt
    try:
        client = mqtt.Client("SmartMeter")
        client.username_pw_set(config['mqttuser'], config['mqttpasswort'])
        client.connect(config['mqttBroker'], config['mqttport'])
    except:
        print("Die Ip Adresse des Brokers ist falsch!")
        sys.exit()

    
tr = GXDLMSTranslator(TranslatorOutputType.SIMPLE_XML)
serIn = serial.Serial( port=config['port'],
         baudrate=config['baudrate'],
         bytesize=serial.EIGHTBITS,
         parity=serial.PARITY_NONE,
         stopbits=serial.STOPBITS_ONE
)

if serIn.isOpen() == True:
    print("Port is already in use!")
    sys.exit(3)

while 1:
    sleep(4.7)
    daten = recv(serIn)
    if daten != '':
        daten = daten.hex()
    if (len(daten) < 560):
        if verbose:
            print("Only " + str(len(daten)) + " bytes received... waiting")
        continue
    if daten == '' or daten[0:8] != "68010168":
        if verbose:
            print ("Invalid Start Bytes... waiting")
        continue
    systemTitel = daten[22:38]
    frameCounter = daten[44:52]
    frame = daten[52:560]

    frame = unhexlify(frame)
    encryption_key = unhexlify(config['evn_schluessel'])
    init_vector = unhexlify(systemTitel + frameCounter)
    cipher = AES.new(encryption_key, AES.MODE_GCM, nonce=init_vector)
    apdu = cipher.decrypt(frame).hex()    

    try:
        xml = tr.pduToXml(apdu,)
        soup = BeautifulSoup(xml, 'lxml')
        results_32 = soup.find_all('uint32')
        results_16 = soup.find_all('uint16')
        results_int16 = soup.find_all('int16')
        results_int8 = soup.find_all('int8')
        results_enum = soup.find_all('enum')

    except BaseException as err:
        print("Fehler: ", format(err))
        continue
       

    try:
        #Wirkenergie A+ in Wattstunden
        WirkenergieP = int(str(results_32[0].get('value')),16)*10**s8(str(results_int8[0].get('value')))
        WirkenergiePUnit = units[int(results_enum[0].get('value'), 16)]

        #Wirkenergie A- in Wattstunden
        WirkenergieN = int(str(results_32[1].get('value')),16)*10**s8(str(results_int8[1].get('value')))
        WirkenergieNUnit = units[int(results_enum[1].get('value'), 16)]
        
        #Momentanleistung P+ in Watt
        MomentanleistungP = int(str(results_32[2].get('value')),16)*10**s8(str(results_int8[2].get('value')))
        MomentanleistungPUnit = units[int(results_enum[2].get('value'), 16)]

        #Momentanleistung P- in Watt
        MomentanleistungN = int(str(results_32[3].get('value')),16)*10**s8(str(results_int8[3].get('value')))
        MomentanleistungNUnit = units[int(results_enum[3].get('value'), 16)]
        
        #Spannung L1
        SpannungL1 = int(str(results_16[0].get('value')),16)*10**s8(str(results_int8[4].get('value')))
        SpannungL1Unit = units[int(results_enum[4].get('value'), 16)]
        
        #Spannung L2
        SpannungL2 = int(str(results_16[1].get('value')),16)*10**s8(str(results_int8[5].get('value')))
        SpannungL2Unit = units[int(results_enum[5].get('value'), 16)]
        
        #Spannung L3
        SpannungL3 = int(str(results_16[2].get('value')),16)*10**s8(str(results_int8[6].get('value')))
        SpannungL3Unit = units[int(results_enum[6].get('value'), 16)]
        
        #Strom L1
        StromL1 = int(str(results_16[3].get('value')),16)*10**s8(str(results_int8[7].get('value')))
        StromL1Unit = units[int(results_enum[7].get('value'), 16)]
        
        #Strom L2
        StromL2 = int(str(results_16[4].get('value')),16)*10**s8(str(results_int8[8].get('value')))
        StromL2Unit = units[int(results_enum[8].get('value'), 16)]
        
        #Strom L3
        StromL3 = int(str(results_16[5].get('value')),16)*10**s8(str(results_int8[9].get('value')))
        StromL3Unit = units[int(results_enum[9].get('value'), 16)]
        
        #Leistungsfaktor
        Leistungsfaktor = s16(str(results_int16[0].get('value')))*10**s8(str(results_int8[10].get('value')))
        LeistungsfaktorUnit = units[int(results_enum[10].get('value'), 16)]
                        
        if config['printValue'] or verbose:
            print('Wirkenergie+: ' + str(WirkenergieP) + WirkenergiePUnit)
            print('Wirkenergie-: ' + str(WirkenergieN) + WirkenergieNUnit)
            print('Momentanleistung+: ' + str(MomentanleistungP) + MomentanleistungPUnit)
            print('Momentanleistung-: ' + str(MomentanleistungN) + MomentanleistungNUnit)
            print('Spannung L1: ' + str(SpannungL1) + SpannungL1Unit)
            print('Spannung L2: ' + str(SpannungL2) + SpannungL2Unit)
            print('Spannung L3: ' + str(SpannungL3) + SpannungL3Unit)
            print('Strom L1: ' + str(StromL1) + StromL1Unit)
            print('Strom L2: ' + str(StromL2) + StromL2Unit)
            print('Strom L3: ' + str(StromL3) + StromL3Unit)
            print('Leistungsfaktor: ' + str(Leistungsfaktor) + LeistungsfaktorUnit)
            print('Momentanleistung: ' + str(MomentanleistungP-MomentanleistungN) + MomentanleistungPUnit)
            print()
            print()
        
        #MQTT
        if config['useMQTT']:
            client.publish("Smartmeter/WirkenergieP",WirkenergieP)
            client.publish("Smartmeter/WirkenergieN",WirkenergieN)
            client.publish("Smartmeter/MomentanleistungP",MomentanleistungP)
            client.publish("Smartmeter/MomentanleistungN",MomentanleistungN)
            client.publish("Smartmeter/Momentanleistung",MomentanleistungP - MomentanleistungN)
            client.publish("Smartmeter/SpannungL1",SpannungL1)
            client.publish("Smartmeter/SpannungL2",SpannungL2)
            client.publish("Smartmeter/SpannungL3",SpannungL3)
            client.publish("Smartmeter/StromL1",StromL1)
            client.publish("Smartmeter/StromL2",StromL2)
            client.publish("Smartmeter/StromL3",StromL3)
            client.publish("Smartmeter/Leistungsfaktor",Leistungsfaktor)
    except BaseException as err:
        print("Fehler: ", format(err))
        continue

