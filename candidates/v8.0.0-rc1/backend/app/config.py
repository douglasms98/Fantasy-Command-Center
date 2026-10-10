from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    FCC_GCP_PROJECT: str = ''
    FCC_FIRESTORE_DATABASE: str = '(default)'
    FCC_FIREBASE_API_KEY: str = ''
    FCC_ROLE: str = 'api'
    FCC_PUBLIC_ORIGIN: str = 'https://fcc-api-322688211348.southamerica-east1.run.app'
    FCC_WEB_ORIGINS: str = ''
    FCC_MAX_LEAGUES: int = 30
    FCC_SYNC_MIN_SECONDS: int = 300
    FCC_COOKIE_SECURE: bool = True
    FCC_TRUST_PROXY_HEADERS: bool = False

    def origins(self):
        return list(dict.fromkeys([self.FCC_PUBLIC_ORIGIN.rstrip('/'), 'https://appassets.androidplatform.net'] +
                                 [x.strip().rstrip('/') for x in self.FCC_WEB_ORIGINS.split(',') if x.strip()]))

@lru_cache
def settings():
    return Settings()
