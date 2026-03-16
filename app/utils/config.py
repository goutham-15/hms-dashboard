from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource, PydanticBaseSettingsSource
from typing import Tuple, Type
from app.utils.logger import get_logger


logger = get_logger(name="config")


class APIConfig(BaseSettings):
    host: str = Field(default="localhost")
    port: int = Field(default=8000)


class DatabaseConfig(BaseSettings):
    type: str = Field(default="sqlite")  # "sqlite" or "mssql"
    host: str = Field(default="localhost")
    port: int = Field(default=1433)
    user: str = Field(default="sa")
    password: str = Field(default="password")
    db: str = Field(default="db")
    driver: str = Field(default="ODBC Driver 17 for SQL Server")
    sqlite_path: str = Field(default="hms_data.db")
    
    @property
    def url(self) -> str:
        if self.type == "sqlite":
            # SQLite URL for local testing
            return f"sqlite:///{self.sqlite_path}"
        else:
            # SQL Server URL for pyodbc
            params = f"DRIVER={{{self.driver}}};SERVER={self.host},{self.port};DATABASE={self.db};UID={self.user};PWD={self.password};TrustServerCertificate=yes"
            import urllib
            encoded_params = urllib.parse.quote_plus(params)
            return f"mssql+pyodbc:///?odbc_connect={encoded_params}"


class BedrockConfig(BaseSettings):
    region: str = Field(default="us-east-1")
    model_id: str = Field(default="meta.llama3-2-3b-instruct-v1:0")


class AWSConfig(BaseSettings):
    access_key: str = Field(default="")
    secret_key: str = Field(default="")
    bedrock: BedrockConfig = Field(default_factory=BedrockConfig)


class VectorDBConfig(BaseSettings):
    persist_directory: str = Field(default="vector_store")
    collection_name: str = Field(default="hms_single_file")
    flush_after_extraction: bool = Field(default=False)


class RedisConfig(BaseSettings):
    host: str = Field(default="localhost")
    port: int = Field(default=6379)
    db: int = Field(default=0)
    ttl: int = Field(default=3600)


class CORSConfig(BaseSettings):
    allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    allow_credentials: bool = Field(default=False)
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        yaml_file=Path(__file__).parent.parent.parent / "config.yaml",
        extra="ignore"
    )
    
    api: APIConfig = Field(default_factory=APIConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    aws: AWSConfig = Field(default_factory=AWSConfig)
    vector_db: VectorDBConfig = Field(default_factory=VectorDBConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    cors: CORSConfig = Field(default_factory=CORSConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """
        Customize the order of settings sources.
        Priority: init > YAML > env > dotenv > file_secret
        """
        return (
            init_settings,
            YamlConfigSettingsSource(settings_cls),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )


try:
    logger.info("Loading configuration using YamlConfigSettingsSource")
    settings = Settings()
    logger.info("Configuration loaded successfully")
except Exception as e:
    logger.error(f"Failed to load configuration: {e}")
    raise
