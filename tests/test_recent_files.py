import pytest

from osc_app.core.recent_files import filter_existing_paths, push_recent_file


def test_push_adds_new_path_first() -> None:
    result = push_recent_file([], "/tmp/a.csv")

    assert result == ["/tmp/a.csv"]


def test_push_moves_existing_path_to_front_without_duplicating() -> None:
    existing = ["/tmp/a.csv", "/tmp/b.csv", "/tmp/c.csv"]

    result = push_recent_file(existing, "/tmp/b.csv")

    assert result == ["/tmp/b.csv", "/tmp/a.csv", "/tmp/c.csv"]


def test_push_respects_limit() -> None:
    existing = ["/tmp/a.csv", "/tmp/b.csv"]

    result = push_recent_file(existing, "/tmp/c.csv", limit=2)

    assert result == ["/tmp/c.csv", "/tmp/a.csv"]


def test_push_does_not_mutate_input() -> None:
    existing = ["/tmp/a.csv"]

    push_recent_file(existing, "/tmp/b.csv")

    assert existing == ["/tmp/a.csv"]


def test_push_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError):
        push_recent_file([], "/tmp/a.csv", limit=0)


def test_filter_existing_paths_keeps_order_and_drops_missing() -> None:
    paths = ["/tmp/a.csv", "/tmp/missing.csv", "/tmp/b.csv"]

    result = filter_existing_paths(paths, exists=lambda p: p != "/tmp/missing.csv")

    assert result == ["/tmp/a.csv", "/tmp/b.csv"]
