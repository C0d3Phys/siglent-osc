from osc_app.core.guided_tests import GUIDED_TESTS


def test_guided_tests_have_required_content() -> None:
    assert len(GUIDED_TESTS) >= 6
    assert all(test.name and test.setup and test.checks and test.warning for test in GUIDED_TESTS)
