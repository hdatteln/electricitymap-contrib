#!/usr/bin/python3
# -*- coding: utf-8 -*-

import arrow
from bs4 import BeautifulSoup
import re
import dateutil
import requests
import json

# RU-1: European and Uralian Market Zone (Zone 1)
# RU-2: Siberian Market Zone (Zone 2)
# RU-AS: Russian Far East


BASE_EXCHANGE_URL = 'http://br.so-ups.ru/webapi/api/flowDiagramm/GetData?'

MAP_GENERATION = {
    'P_AES': 'nuclear',
    'P_GES': 'hydro',
    'P_GRES': 'unknown',
    'P_TES': 'unknown',
    'P_BS': 'unknown',
    'P_REN': 'solar'
}

exchange_ids = {'RU-AS->CN': 764,
                'RU->MN': 276,
                'RU-2->MN': 276,
                'RU->KZ': 785,
                'RU-1->KZ': 2394,
                'RU-2->KZ': 344,
                'RU-2->RU-1': 139,
                'RU->GE': 752,
                'RU-1->GE': 752,
                'AZ->RU': 598,
                'AZ->RU-1': 598,
                'BY->RU': 321,
                'BY->RU-1': 321,
                'RU->FI': 187,
                'RU-1->FI': 187,
                'RU-KGD->LT': 212,
                'RU-1->UA-CR': 5688,
                'UA->RU-1': 880}

# Each exchange is contained in a div tag with a "data-id" attribute that is unique.


tz = 'Europe/Moscow'


def fetch_production(zone_key='RU', session=None, target_datetime=None, logger=None) -> list:
    """Requests the last known production mix (in MW) of a given country."""
    if target_datetime:
        raise NotImplementedError('This parser is not yet able to parse past dates')

    r = session or requests.session()
    today = arrow.now(tz=tz).format('YYYY.MM.DD')

    if zone_key == 'RU':
        url = 'http://br.so-ups.ru/webapi/api/CommonInfo/PowerGeneration?priceZone[]=-1&startDate={date}&endDate={date}'.format(
            date=today)
    elif zone_key == 'RU-1':
        url = 'http://br.so-ups.ru/webapi/api/CommonInfo/PowerGeneration?priceZone[]=1&startDate={date}&endDate={date}'.format(
            date=today)
    elif zone_key == 'RU-2':
        url = 'http://br.so-ups.ru/webapi/api/CommonInfo/PowerGeneration?priceZone[]=2&startDate={date}&endDate={date}'.format(
            date=today)
    else:
        raise NotImplementedError('This parser is not able to parse given zone')

    response = r.get(url)
    json_content = json.loads(response.text)
    dataset = json_content[0]['m_Item2']

    data = []
    for datapoint in dataset:
        row = {
            'zoneKey': zone_key,
            'production': {},
            'storage': {},
            'source': 'so-ups.ru'
            }

        for k, production_type in MAP_GENERATION.items():
            if k in datapoint:
                gen_value = float(datapoint[k]) if datapoint[k] else 0.0
                row['production'][production_type] = row['production'].get(production_type,
                                                                        0.0) + gen_value
            else:
                row['production']['unknown'] = row['production'].get('unknown', 0.0) + gen_value

        # Date
        hour = '%02d' % int(datapoint['INTERVAL'])
        date = arrow.get('%s %s' % (today, hour), 'YYYY.MM.DD HH')

        row['datetime'] = date.replace(tzinfo=dateutil.tz.gettz(tz)).datetime

        current_dt = arrow.now(tz).datetime

        # Drop datapoints in the future
        if row['datetime'] > current_dt:
            continue

        # Default values
        row['production']['biomass'] = None
        row['production']['geothermal'] = None

        data.append(row)

    return data


def response_checker(json_content) -> bool:
    flow_values = json_content['Flows']

    if not flow_values:
        return False

    non_zero = False
    for item in flow_values:
        if item['Id'] in list(exchange_ids.values()):
            if item['NumValue'] == 0.0:
                continue
            else:
                non_zero = True
                break

    return non_zero


def fetch_exchange(zone_key1, zone_key2, session=None, target_datetime=None, logger=None) -> list:
    """Requests the last known power exchange (in MW) between two zones."""
    if target_datetime:
        today = arrow.get(target_datetime, 'YYYYMMDD')
    else:
        today = arrow.utcnow()

    date = today.format('YYYY-MM-DD')
    r = session or requests.session()
    DATE = 'Date={}'.format(date)

    exchange_urls = []
    if target_datetime:
        for hour in range(0,24):
            url = BASE_EXCHANGE_URL + DATE + '&Hour={}'.format(hour)
            exchange_urls.append((url,hour))
    else:
        # Only fetch last 2 hours when not fetching historical data.
        for shift in range(0, 2):
            hour = today.shift(hours=-shift).format('HH')
            url = BASE_EXCHANGE_URL + DATE + '&Hour={}'.format(hour)
            exchange_urls.append((url, int(hour)))

    datapoints = []
    for url, hour in exchange_urls:
        response = r.get(url)
        json_content = json.loads(response.text)

        if response_checker(json_content):
            datapoints.append((json_content['Flows'], hour))
        else:
            # data not yet available for this hour
            continue

    sortedcodes = '->'.join(sorted([zone_key1, zone_key2]))
    reversesortedcodes = '->'.join(sorted([zone_key1, zone_key2], reverse=True))

    if sortedcodes in exchange_ids.keys():
        exchange_id = exchange_ids[sortedcodes]
        direction = 1
    elif reversesortedcodes in exchange_ids.keys():
        exchange_id = exchange_ids[reversesortedcodes]
        direction = -1
    else:
        raise NotImplementedError('This exchange pair is not implemented.')

    data = []
    for datapoint, hour in datapoints:
        try:
            exchange = [item for item in datapoint if item['Id'] == exchange_id][0]
            flow = exchange.get('NumValue') * direction
        except KeyError:
            # flow is unknown or not available
            flow = None

        dt = today.replace(hour=hour).floor('hour').datetime

        exchange = {
            'sortedZoneKeys': sortedcodes,
            'datetime': dt,
            'netFlow': flow,
            'source': 'so-ups.ru'
        }

        data.append(exchange)

    return data


if __name__ == '__main__':
    print('fetch_production() ->')
    print(fetch_production())
    print('fetch_production(RU-1) ->')
    print(fetch_production('RU-1'))
    print('fetch_production(RU-2) ->')
    print(fetch_production('RU-2'))
    print('fetch_exchange(CN, RU-AS) ->')
    print(fetch_exchange('CN', 'RU-AS'))
    print('fetch_exchange(MN, RU) ->')
    print(fetch_exchange('MN', 'RU'))
    print('fetch_exchange(MN, RU-2) ->')
    print(fetch_exchange('MN', 'RU-2'))
    print('fetch_exchange(KZ, RU) ->')
    print(fetch_exchange('KZ', 'RU'))
    print('fetch_exchange(KZ, RU-1) ->')
    print(fetch_exchange('KZ', 'RU-1'))
    print('fetch_exchange(KZ, RU-2) ->')
    print(fetch_exchange('KZ', 'RU-2'))
    print('fetch_exchange(GE, RU) ->')
    print(fetch_exchange('GE', 'RU'))
    print('fetch_exchange(GE, RU-1) ->')
    print(fetch_exchange('GE', 'RU-1'))
    print('fetch_exchange(AZ, RU) ->')
    print(fetch_exchange('AZ', 'RU'))
    print('fetch_exchange(AZ, RU-1) ->')
    print(fetch_exchange('AZ', 'RU-1'))
    print('fetch_exchange(BY, RU) ->')
    print(fetch_exchange('BY', 'RU'))
    print('fetch_exchange(BY, RU-1) ->')
    print(fetch_exchange('BY', 'RU-1'))
    print('fetch_exchange(RU-1, UA-CR) ->')
    print(fetch_exchange('RU-1', 'UA-CR'))
    print('fetch_exchange(RU-1, UA) ->')
    print(fetch_exchange('RU-1', 'UA'))
    print('fetch_exchange(RU-1, RU-2) ->')
    print(fetch_exchange('RU-1', 'RU-2'))
