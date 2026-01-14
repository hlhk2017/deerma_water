"""Constants for Deerma Water Purifier integration."""
from __future__ import annotations

DOMAIN = "deerma_water"

# API endpoints
API_BASE_URL = "https://iot.deerma.com"
API_SESSION = "/api/app/session/"
API_CAPTCHA = "/api/app/captcha"
API_DEVICE_LIST = "/api/app/devices/"
API_DEVICE_STATUS = "/api/app/device/status"

# App ID from HAR file
APP_ID = "9c3b124649fa11e98b6e02461a5b364e"

# MQTT topics (will be determined from device info)
MQTT_TOPIC_PREFIX = "deerma/device/"

# Device attributes
ATTR_TOTAL_WATER = "total_water"
ATTR_TAP_WATER_TDS = "tap_water_tds"
ATTR_PURIFIED_TDS = "purified_tds"
ATTR_AQP_FILTER_LIFE = "aqp_filter_life"
ATTR_PC5IN1_FILTER_LIFE = "pc5in1_filter_life"
ATTR_TEMPERATURE_SETTING = "temperature_setting"
ATTR_WATER_VOLUME_SETTING = "water_volume_setting"
ATTR_AVG_TDS = "average_tds"
