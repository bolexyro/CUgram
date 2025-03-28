from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    auth_url_base: str
    client_secrets_path: str
    dsa_bot_server_secret_token: str
    dsa_bot_token: str
    dsa_bot_url_base: str
    dsa_email: str
    fastapi_auth_secret_key: str
    service_account_key_path: str
    student_bot_server_secret_token: str
    student_bot_token: str
    student_bot_url_base: str
    official_emails: list[str]
    scopes: list[str]
    jwt_signing_secret_key: str

    @model_validator(mode="before")
    @classmethod
    def _parse_official_emails(cls, data):
        data["official_emails"] = data["official_emails"].split(",")
        data["scopes"] = data["scopes"].split(",")
        return data


settings = Settings()

if __name__ == "__main__":
    print(settings.model_dump_json(indent=9))
