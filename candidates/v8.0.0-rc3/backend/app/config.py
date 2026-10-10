from functools import lru_cache
import re
from pydantic_settings import BaseSettings, SettingsConfigDict

# Product limit shared by registration and the account payload. It cannot be
# increased by a deployment environment variable or a client request.
MAX_LEAGUES_PER_USER = 6

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    FCC_GCP_PROJECT: str = ''
    FCC_FIRESTORE_DATABASE: str = '(default)'
    FCC_FIREBASE_API_KEY: str = ''
    FCC_GOOGLE_CLIENT_ID: str = ''
    FCC_ROLE: str = 'api'
    FCC_PUBLIC_ORIGIN: str = 'https://fcc-api-322688211348.southamerica-east1.run.app'
    FCC_WEB_ORIGINS: str = ''
    FCC_SYNC_MIN_SECONDS: int = 300
    FCC_COOKIE_SECURE: bool = True
    FCC_TRUST_PROXY_HEADERS: bool = False

    def origins(self):
        return list(dict.fromkeys([self.FCC_PUBLIC_ORIGIN.rstrip('/'), 'https://appassets.androidplatform.net'] +
                                 [x.strip().rstrip('/') for x in self.FCC_WEB_ORIGINS.split(',') if x.strip()]))

    def google_enabled(self):
        return bool(self.FCC_GCP_PROJECT and self.FCC_FIREBASE_API_KEY and
                    re.fullmatch(r'[0-9]+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com', self.FCC_GOOGLE_CLIENT_ID))

@lru_cache
def settings():
    return Settings()
