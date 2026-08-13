import pytest

from copilot.domain.profile import ProfileError, load_profile


def test_load_example_profile(tmp_path):
    example = open("profile.example.yaml", encoding="utf-8").read()
    path = tmp_path / "profile.yaml"
    path.write_text(example, encoding="utf-8")
    profile = load_profile(path)
    assert profile.all_fact_ids() >= {"exp-001", "exp-002", "proj-001", "edu-001"}
    assert "python" in profile.known_technologies()
    rendered = profile.render_for_prompt()
    assert "[exp-001]" in rendered
    assert "NUNCA elevar" in rendered


def test_missing_profile_raises(tmp_path):
    with pytest.raises(ProfileError):
        load_profile(tmp_path / "nao-existe.yaml")


def test_duplicate_ids_rejected(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        """
experiences:
  - {id: exp-001, company: A, role: Dev}
  - {id: exp-001, company: B, role: Dev}
""",
        encoding="utf-8",
    )
    with pytest.raises(ProfileError):
        load_profile(path)


def test_render_is_stable_for_prompt_cache(sample_profile):
    assert sample_profile.render_for_prompt() == sample_profile.render_for_prompt()
