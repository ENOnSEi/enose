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
    # Ventana de regresión en segundos (la dinámica de los TGS es de segundos)
    OBSERVER_WINDOW_SECONDS: float = 4.0
    # Umbral central de pendiente (u/s), pequeño positivo. Calibrado con datasets/
    # reales (rango factible ~6.2-8.4 u/s, ver tools/calibrate.py)
    OBSERVER_SLOPE_THRESHOLD: float = 7.5
    # Ancho de la banda muerta (histéresis) como fracción del umbral
    OBSERVER_HYSTERESIS: float = 0.15
    # Tiempo que la condición debe sostenerse antes de confirmar (debounce)
    OBSERVER_CONFIRM_SECONDS: float = 1.0
    # Política multi-sensor: "all" | "any" | "majority"
    OBSERVER_POLICY: str = "all"
    # Nº de lecturas recientes que se traen de la BD para cubrir la ventana
    OBSERVER_FETCH_LIMIT: int = 300
    OBSERVER_POLL_INTERVAL: float = 1.0
    OBSERVER_MIN_MEDICION_SECONDS: float = 30.0


settings = Settings()
