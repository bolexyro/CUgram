from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8")

    client_secrets_path: str
    service_account_key_path: str
    fastapi_session_secret_key: str
    jwt_signing_secret_key: str
    dsa_bot_token: str
    student_bot_token: str
    server_url_base: str
    official_emails: list[str]
    scopes: list[str]


settings = Settings()

if __name__ == "__main__":
    print(settings.model_dump_json(indent=9))
