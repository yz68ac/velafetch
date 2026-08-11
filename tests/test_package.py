"""Package metadata tests."""

from velafetch import __version__


def test_version_is_semantic() -> None:
    major, minor, patch = __version__.split(".")

    assert major.isdigit()
    assert minor.isdigit()
    assert patch.isdigit()
    assert __version__ == "0.2.0"
