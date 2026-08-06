"""Test PersonTracker."""

from __future__ import annotations

from sirah.autonomy.person_tracker import PersonTracker


def test_person_tracker_empty() -> None:
    pt = PersonTracker()
    assert pt.known_count == 0
    assert pt.identify(()) is None


def test_register_new_person() -> None:
    pt = PersonTracker()
    emb = PersonTracker.make_dummy_embedding(1)
    profile = pt.register(emb, name="Ana")
    assert profile.name == "Ana"
    assert profile.visit_count == 1
    assert pt.known_count == 1


def test_identify_known_person() -> None:
    pt = PersonTracker()
    emb = PersonTracker.make_dummy_embedding(42)
    pt.register(emb, name="Juan")
    result = pt.identify(emb)
    assert result is not None
    assert result.name == "Juan"
    assert result.visit_count == 2


def test_identify_unknown_person() -> None:
    pt = PersonTracker()
    emb1 = PersonTracker.make_dummy_embedding(1)
    emb2 = PersonTracker.make_dummy_embedding(999)
    pt.register(emb1, name="Ana")
    result = pt.identify(emb2)
    assert result is None


def test_identify_or_register_new() -> None:
    pt = PersonTracker()
    emb = PersonTracker.make_dummy_embedding(7)
    profile = pt.identify_or_register(emb)
    assert profile.visit_count == 1
    assert "visita" in profile.name


def test_identify_or_register_returning() -> None:
    pt = PersonTracker()
    emb = PersonTracker.make_dummy_embedding(5)
    p1 = pt.identify_or_register(emb)
    p2 = pt.identify_or_register(emb)
    assert p1.name == p2.name
    assert p2.visit_count == 2


def test_owner_recognition() -> None:
    owner_emb = PersonTracker.make_dummy_embedding(0)
    pt = PersonTracker(owner_embedding=owner_emb)
    profile = pt.identify_or_register(owner_emb)
    assert profile.relationship == "owner"
    assert profile.name == "dueño"


def test_forget_person() -> None:
    pt = PersonTracker()
    emb = PersonTracker.make_dummy_embedding(3)
    pt.register(emb, name="Elena")
    assert pt.known_count == 1
    pt.forget("Elena")
    assert pt.known_count == 0


def test_list_known() -> None:
    pt = PersonTracker()
    pt.register(PersonTracker.make_dummy_embedding(1), "A")
    pt.register(PersonTracker.make_dummy_embedding(2), "B")
    assert len(pt.list_known()) == 2


def test_cosine_similarity_identical() -> None:
    emb = tuple(float(i) for i in range(128))
    sim = PersonTracker._cosine_similarity(emb, emb)
    assert abs(sim - 1.0) < 0.001


def test_cosine_similarity_orthogonal() -> None:
    a = (1.0,) + (0.0,) * 127
    b = (0.0, 1.0) + (0.0,) * 126
    sim = PersonTracker._cosine_similarity(a, b)
    assert abs(sim - 0.0) < 0.001


def test_cosine_similarity_empty() -> None:
    assert PersonTracker._cosine_similarity((), ()) == 0.0


def test_dummy_embedding_different_seeds() -> None:
    e1 = PersonTracker.make_dummy_embedding(1)
    e2 = PersonTracker.make_dummy_embedding(2)
    assert e1 != e2
    assert len(e1) == 128
    assert len(e2) == 128
