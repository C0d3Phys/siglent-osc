import pytest

from osc_app.core.recent_files import (
    dedupe_paths,
    filter_existing_paths,
    push_recent_file,
    recent_file_label,
)


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


def test_push_uses_key_to_detect_the_same_file() -> None:
    existing = [r"C:\Users\ING_CE~1\a.csv", r"C:\b.csv"]

    result = push_recent_file(
        existing,
        r"C:\Users\ING_CESAR_TAPIA\a.csv",
        key=lambda path: path.replace("ING_CE~1", "ING_CESAR_TAPIA"),
    )

    assert result == [r"C:\Users\ING_CESAR_TAPIA\a.csv", r"C:\b.csv"]


def test_dedupe_keeps_first_occurrence() -> None:
    assert dedupe_paths(["a", "A", "b"], key=str.lower) == ["a", "b"]


def test_label_shows_name_and_short_folder() -> None:
    assert recent_file_label(r"E:\splg0001.slg") == "splg0001.slg   —   E:\\"
    assert (
        recent_file_label(r"C:\Users\cesar\Desktop\OSC APP\examples\4ch.csv")
        == r"4ch.csv   —   …\OSC APP\examples"
    )
    assert recent_file_label("/tmp/a.csv") == "a.csv   —   /tmp"
