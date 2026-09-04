from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    xfi_connect_db_path: str = '/opt/XFI_CONNECT/database/vpn_bot.db'
    xfi_connect_server_id: int | None = None
    secret_key: str = 'change-me'
    session_cookie_secure: bool = True
    xui_timeout: float = 20.0
    xui_verify_tls: bool = True

settings = Settings()
