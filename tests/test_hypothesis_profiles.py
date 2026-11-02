from hypothesis import settings


def test_hypothesis_profiles_set_the_example_counts():
    assert settings.get_profile("dev").max_examples == 100
    assert settings.get_profile("ci").max_examples == 500
    assert settings.get_profile("nightly").max_examples == 5000
