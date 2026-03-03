from app.models import CandidateChunk
from rankers.base import BaseRanker


class IdentityRanker(BaseRanker):
    @property
    def name(self) -> str:
        return "none"

    def rank(self, query: str, candidates: list[CandidateChunk], top_n: int) -> list[CandidateChunk]:
        return candidates[:top_n]
