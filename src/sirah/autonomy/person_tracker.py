"""PersonTracker — recognize and differentiate people by face embedding."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from time import monotonic

__all__ = ["PersonTracker", "PersonProfile"]

SIMILARITY_THRESHOLD = 0.75


@dataclass
class PersonProfile:
    face_embedding: tuple[float, ...]
    name: str
    first_seen: float = field(default_factory=monotonic)
    last_seen: float = field(default_factory=monotonic)
    visit_count: int = 1
    relationship: str = "stranger"
    preferred_topics: tuple[str, ...] = ()

    def touch(self) -> None:
        self.last_seen = monotonic()
        self.visit_count += 1


class PersonTracker:
    def __init__(self, owner_embedding: tuple[float, ...] | None = None) -> None:
        self._known: list[PersonProfile] = []
        self._owner_embedding = owner_embedding
        self._next_visitor_id = 1

    def identify(self, embedding: tuple[float, ...]) -> PersonProfile | None:
        if not embedding:
            return None

        if self._owner_embedding is not None and self._cosine_similarity(
            embedding, self._owner_embedding
        ) > SIMILARITY_THRESHOLD:
            for p in self._known:
                if p.relationship == "owner":
                    p.touch()
                    return p

        best_sim = 0.0
        best_person: PersonProfile | None = None
        for p in self._known:
            sim = self._cosine_similarity(embedding, p.face_embedding)
            if sim > best_sim:
                best_sim = sim
                best_person = p

        if best_person is not None and best_sim > SIMILARITY_THRESHOLD:
            best_person.touch()
            return best_person

        return None

    def register(
        self, embedding: tuple[float, ...], name: str = "", relationship: str = "stranger"
    ) -> PersonProfile:
        if self._owner_embedding is not None and self._cosine_similarity(
            embedding, self._owner_embedding
        ) > SIMILARITY_THRESHOLD:
            name = name or "dueño"
            relationship = "owner"

        if not name:
            name = f"visita_{self._next_visitor_id}"
            self._next_visitor_id += 1

        profile = PersonProfile(
            face_embedding=embedding,
            name=name,
            relationship=relationship,
        )
        self._known.append(profile)
        return profile

    def identify_or_register(self, embedding: tuple[float, ...]) -> PersonProfile:
        known = self.identify(embedding)
        if known is not None:
            return known
        return self.register(embedding)

    def forget(self, name: str) -> None:
        self._known = [p for p in self._known if p.name != name]

    def list_known(self) -> tuple[PersonProfile, ...]:
        return tuple(self._known)

    @property
    def known_count(self) -> int:
        return len(self._known)

    @staticmethod
    def _cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        if len(a) != len(b) or len(a) == 0:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def make_dummy_embedding(seed: int = 0) -> tuple[float, ...]:
        import hashlib

        h = hashlib.sha256(str(seed).encode()).digest()
        values = []
        for i in range(128):
            byte_val = h[i % len(h)]
            values.append((byte_val / 255.0) * 2.0 - 1.0)
        return tuple(values)
