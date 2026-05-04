from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    request_timeout_seconds: float = 8.0

    geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    wttr_url: str = "https://goweather.xyz/weather"
    opensensemap_url: str = "https://api.opensensemap.org/boxes"
    seven_timer_url: str = "https://www.7timer.info/bin/api.pl"
    oceandrivers_stations_url: str = "https://api.oceandrivers.com/v1.0/getStations/"
    oceandrivers_meteo_url: str = "https://api.oceandrivers.com/v1.0/getMeteo"

    opensensemap_max_distance_m: int = 10000
    oceandrivers_max_station_km: float = 100.0


settings = Settings()
