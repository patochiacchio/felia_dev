# app/store.py (reemplazo completo)
from typing import Dict, Any, Set
from dataclasses import dataclass, field

@dataclass
class SessionState:
    greeted: bool = False
    rounds: int = 0
    asked_questions: Set[str] = field(default_factory=set)
    asked_norms: Set[str] = field(default_factory=set)
    answered_slots: Dict[str, Any] = field(default_factory=dict)

class MemoryStore:
    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState()
        return self._sessions[session_id]

    def reset(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id]

store = MemoryStore()
