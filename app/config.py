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
    oceandrivers_stations_url: str = "https://api.oceandrivers.com/v1.0/getStations/"
    oceandrivers_meteo_url: str = "https://api.oceandrivers.com/v1.0/getMeteo"

    opensensemap_max_distance_m: int = 10000
    oceandrivers_max_station_km: float = 100.0

    log_level: str = "INFO"
    cors_allow_origins: str = ""  # comma-separated list, empty = no CORS


settings = Settings()
