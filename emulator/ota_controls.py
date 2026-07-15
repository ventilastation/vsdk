"""Stable desktop OTA command helpers with no GUI or network dependencies."""


OTA_SERVER_URL = "http://ventilastation-base.local:5653"


def ota_start_command():
    return "ota_start " + OTA_SERVER_URL
