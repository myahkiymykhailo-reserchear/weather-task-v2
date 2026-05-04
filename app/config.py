from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration. Every field can be overridden via WEATHER_<UPPER> env vars.

    Example:
        WEATHER_REQUEST_TIMEOUT_SECONDS=15 uvicorn app.main:app
    """

    model_config = SettingsConfigDict(env_prefix="WEATHER_", extra="ignore")

    request_timeout_seconds: float = 8.0
    total_request_budget_seconds: float = 12.0

    geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    # The originally-listed robertoduessmann/weather-api host (goweather.xyz)
    # has been offline since at least 2026-05 — every path returns 404. wttr.in
    # is the well-maintained alternative in the same "easy weather" family;
    # it accepts city names as the path and returns JSON via ?format=j1.
    wttr_url: str = "https://wttr.in"
    opensensemap_url: str = "https://api.opensensemap.org/boxes"
    seven_timer_url: str = "https://www.7timer.info/bin/api.pl"
    # OceanDrivers is a regional Spanish marine weather service. The /getStations/
    # endpoint guessed at by v0.2 does not exist — the real API serves data via
    # /v1.0/getAemetStation/{stationName}/lastdata/. Effectively a single usable
    # station, AreaPalma (Mallorca), at 39.5604N 2.7417E.
    oceandrivers_url: str = "https://api.oceandrivers.com"
    oceandrivers_station_name: str = "AreaPalma"
    oceandrivers_station_lat: float = 39.5604
    oceandrivers_station_lon: float = 2.7417

    opensensemap_max_distance_m: int = 5000
    oceandrivers_max_station_km: float = 200.0

    log_level: str = "INFO"
    cors_allow_origins: str = ""  # comma-separated list, empty = no CORS


settings = Settings()
