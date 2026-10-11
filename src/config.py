from pydantic import AnyHttpUrl, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    provider: str
    model: str
    max_tokens: PositiveInt
    gemini_api_key: SecretStr
    mcp_url: AnyHttpUrl
