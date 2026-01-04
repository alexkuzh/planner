from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "planner"

    env: str = "local"
    debug: bool = True

    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "planner"
    db_user: str = "planner"
    db_password: str = "planner"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
