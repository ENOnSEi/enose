from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/enose_db"
    APP_NAME: str = "ENose API"
    DEBUG: bool = False
    SERIAL_PORT: str = "/dev/ttyACM0"
    SERIAL_BAUD: int = 9600
    # Orden debe coincidir con el orden de valores que envía el Arduino
    SENSOR_NAMES: list[str] = ["tgs2620", "tgs2611", "tgs2602", "tgs2600"]
    SENSOR_PINS: list[str] = ["A3", "A2", "A1", "A0"]
    OBSERVER_WINDOW: int = 60
    OBSERVER_SLOPE_THRESHOLD: float = 1.0
    OBSERVER_POLL_INTERVAL: float = 1.0
    OBSERVER_MIN_MEDICION_SECONDS: float = 30.0


settings = Settings()
