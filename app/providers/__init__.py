from app.providers.base import WeatherProvider
from app.providers.oceandrivers import OceanDriversProvider
from app.providers.open_meteo import OpenMeteoProvider
from app.providers.opensensemap import OpenSenseMapProvider
from app.providers.seven_timer import SevenTimerProvider
from app.providers.wttr import WttrProvider

DEFAULT_PROVIDERS: list[WeatherProvider] = [
    OpenMeteoProvider(),
    WttrProvider(),
    OpenSenseMapProvider(),
    OceanDriversProvider(),
    SevenTimerProvider(),
]

__all__ = [
    "WeatherProvider",
    "OpenMeteoProvider",
    "WttrProvider",
    "OpenSenseMapProvider",
    "OceanDriversProvider",
    "SevenTimerProvider",
    "DEFAULT_PROVIDERS",
]
