"""UBox integration constants: local camera (proxy/relay) + cloud sensors."""
DOMAIN = "ubox"
PLATFORMS = ["camera", "sensor", "image"]

# ---- local camera (proxy / relay) ----
CONF_MODE = "mode"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_UID = "uid"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_RELAY = "relay"
CONF_STREAM = "stream"
CONF_SCAN = "scan_interval"

MODE_PROXY = "proxy"
MODE_RELAY = "relay"
MODE_CLOUD = "cloud"

DEFAULT_PORT = 8089
DEFAULT_RELAY = "162.251.63.134:20001"
DEFAULT_STREAM = 0
DEFAULT_SCAN = 30
DEFAULT_USERNAME = "admin"

# ---- Add-on HTTP auth (8089 Basic, empty = open) ----
CONF_HTTP_USER = "http_username"
CONF_HTTP_PASS = "http_password"

# ---- options: per-device config ----
CONF_DEVICE = "device"
CONF_DEVICES = "devices"
CONF_LIVE = "live"
CONF_RELAY_UID = "relay_uid"
CONF_RELAY_USERNAME = "relay_username"
CONF_RELAY_PASSWORD = "relay_password"
CONF_RELAY_STREAM = "relay_stream"

# ---- cloud sensors (UBox account, portal.ubianet.com) ----
CONF_ACCOUNT = "account"
CONF_REGION = "region"

REGIONS = {
    "cn": "https://portal-cn.ubianet.com",
    "us": "https://portal-us.ubianet.com",
    "uni": "https://portal-uni.ubianet.com",
}
DEFAULT_REGION = "us"
UPDATE_INTERVAL_SEC = 60
CLOUD_LIST_DAYS = 7
MAX_CLOUD_IMAGES = 5
