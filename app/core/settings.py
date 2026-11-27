from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    SECRET_KEY: str
    ALGORITHM: str 
    ACCESS_TOKEN_EXPIRE_MINUTES: int 
    REFRESH_TOKEN_EXPIRE_DAYS: int
    
    GROQ_API_KEY:str
    
    DATABASE_URL: str
    CHECKPOINT_DATABASE_URL: str
    DIRECT_URL: str
    
    
    RESEND_API_KEY: str
    FROM_EMAIL: str
        
    BACKEND_URL:str
    FRONTEND_URL: str | None = None
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    
    

    

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings() 

