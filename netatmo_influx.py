#!/usr/bin/env python3
# encoding=utf-8

import signal
import lnetatmo
import argparse
import configparser
from time import sleep
from os import environ
from pathlib import Path
from influxdb import InfluxDBClient


def parse_config(config_file=None):
    _config = configparser.ConfigParser(interpolation=None)

    if config_file is None:
        config_file = Path('./config')

    if config_file.exists():
        _config.read(config_file)

    return _config


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', dest='config', type=str, nargs=1, required=False)

    return parser.parse_args()


def shutdown(_signal):
    global running
    running = False


if __name__ == "__main__":
    running = True
    interval = None
    influx_host = None
    influx_port = None
    influx_db = None
    influx_ssl = None
    influx_username = None
    influx_password = None
    args = parse_args()
    config = parse_config(args.config)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    if "global" in config:
        interval = int(config["global"]["interval"])

    if "netatmo" in config:
        client_id = config["netatmo"]["client_id"]
        client_secret = config["netatmo"]["client_secret"]
        netatmo_username = config["netatmo"]["netatmo_username"]
        netatmo_password = config["netatmo"]["netatmo_password"]

    if "influx" in config:
        influx_host = config["influx"]["influx_host"]
        influx_port = config["influx"]["influx_port"]
        influx_db = config["influx"]["influx_db"]
        influx_ssl = config["influx"]["influx_ssl"]
        influx_username = config["influx"]["influx_username"]
        influx_password = config["influx"]["influx_password"]

    if environ.get("NETATMO_CLIENT_ID"):
        client_id = environ.get("NETATMO_CLIENT_ID")
    if environ.get("NETATMO_CLIENT_SECRET"):
        client_secret = environ.get("NETATMO_CLIENT_SECRET")
    if environ.get("NETATMO_USERNAME"):
        netatmo_username = environ.get("NETATMO_USERNAME")
    if environ.get("NETATMO_PASSWORD"):
        netatmo_password = environ.get("NETATMO_PASSWORD")

    if environ.get("INFLUX_HOST"):
        influx_host = environ.get("INFLUX_HOST")
    elif influx_host is None:
        influx_host = "localhost"
    if environ.get("INFLUX_PORT"):
        influx_port = environ.get("INFLUX_PORT")
    elif influx_port is None:
        influx_port = 8086
    if environ.get("INFLUX_DB"):
        influx_db = environ.get("INFLUX_DB")
    elif influx_db is None:
        influx_db = "grafana"
    if environ.get("INFLUX_SSL"):
        if environ.get("INFLUX_SSL") == "True":
            influx_ssl = True
        else:
            influx_ssl = False
    elif influx_ssl is None:
        influx_ssl = False
    if environ.get("INFLUX_USERNAME"):
        influx_username = environ.get("INFLUX_USERNAME")
    if environ.get("INFLUX_PASSWORD"):
        influx_password = environ.get("INFLUX_PASSWORD")
    if interval is None:
        interval = 300  # interval in seconds; default are 5 Minutes
    elif environ.get("INTERVAL"):
        interval = int(environ.get("INTERVAL"))

    while running:
        try:
            authorization = lnetatmo.ClientAuth(
                clientId=client_id,
                clientSecret=client_secret,
                username=netatmo_username,
                password=netatmo_password,
                scope="read_station",
            )

            weatherData = lnetatmo.WeatherStationData(authorization)
            client = InfluxDBClient(
                host=influx_host,
                port=influx_port,
                username=influx_username,
                password=influx_password,
                database=influx_db,
                ssl=influx_ssl
            )

            for station in weatherData.stations:
                station_data = []
                module_data = []
                station = weatherData.stationById(station)
                station_name = station["station_name"]
                altitude = station["place"]["altitude"]
                country = station["place"]["country"]
                timezone = station["place"]["timezone"]
                longitude = station["place"]["location"][0]
                latitude = station["place"]["location"][1]
                for module, moduleData in weatherData.lastData(station=station_name, exclude=3600).items():
                    for measurement in ["altitude", "country", "longitude", "latitude", "timezone"]:
                        value = eval(measurement)
                        if type(value) == int:
                            value = float(value)
                        station_data.append(
                            {
                                "measurement": measurement,
                                "tags": {"station": station_name, "module": module},
                                "time": moduleData["When"],
                                "fields": {"value": value},
                            }
                        )

                    for sensor, value in moduleData.items():
                        if sensor.lower() != "when":
                            if type(value) == int:
                                value = float(value)
                            module_data.append(
                                {
                                    "measurement": sensor.lower(),
                                    "tags": {"station": station_name, "module": module},
                                    "time": moduleData["When"],
                                    "fields": {"value": value},
                                }
                            )

                client.write_points(station_data, time_precision="s", database=influx_db)
                client.write_points(module_data, time_precision="s", database=influx_db)
        except NameError:
            print("No credentials supplied. No Netatmo Account available.")
            exit(1)

        sleep(interval)
