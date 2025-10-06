from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Identificador de sesión del cliente")
    message: str = Field(..., description="Texto enviado por el cliente")

class Item(BaseModel):
    name: str
    default_code: str
    price: float
    has_stock: bool

class ChatResponse(BaseModel):
    reply: str
    items: Optional[List[Item]] = None
    state: Dict[str, Any]

class SearchPlan(BaseModel):
    q: str
    must: List[str]
    not_: List[str] = Field(alias="not")
    units: Dict[str, Any]
    decision: str  # "ask" | "search"
    questions: List[str] = []
    variants: List[str] = []   # NUEVO: variantes dinámicas de consulta (10–30)

class SearchRequest(BaseModel):
    q: str
    must: List[str] = []
    not_: List[str] = Field(default_factory=list, alias="not")
    units: Dict[str, Any] = {}
    variants: List[str] = []   # NUEVO

class SearchResponse(BaseModel):
    items: List[Item] = []
