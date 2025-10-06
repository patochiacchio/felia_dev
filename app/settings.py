from pydantic import BaseModel
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    # OpenAI
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    # Compatibilidad con ambos nombres
    model_name: str = (
        os.getenv("MODEL_NAME")
        or os.getenv("OPENAI_MODEL")
        or "gpt-4o"
    )

    # Catálogo local
    catalog_path: str = os.getenv("CATALOG_PATH", "./catalog.json")
    max_return: int = int(os.getenv("MAX_RETURN", "4"))
    min_return: int = int(os.getenv("MIN_RETURN", "2"))

    # Flujo
    min_pre_questions_before_search: int = int(os.getenv("MIN_PRE_QUESTIONS_BEFORE_SEARCH", "1"))
    postsearch_ask_if_results_gt: int = int(os.getenv("POSTSEARCH_ASK_IF_RESULTS_GT", "3"))

settings = Settings()
