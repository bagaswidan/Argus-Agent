"""Test Branding — Argus."""
from __future__ import annotations

import pytest

from argus.branding import (
    CONSTITUTION,
    PIPELINE,
    VISION,
    eye_only,
    logo,
    render_logo_jpeg,
    wordmark_only,
)


class TestBranding:
    def test_vision_has_5_items(self):
        assert len(VISION) == 5

    def test_constitution_has_8_principles(self):
        assert len(CONSTITUTION) == 8

    def test_pipeline_has_key_stages(self):
        assert "Brain" in PIPELINE
        assert "Capability" in PIPELINE
        assert "Security" in PIPELINE
        assert "Reflection" in PIPELINE
        assert "Response" in PIPELINE

    def test_eye_only(self):
        art = eye_only()
        assert "####" in art
        assert len(art.split("\n")) >= 5

    def test_wordmark_only(self):
        wm = wordmark_only()
        # figlet slant renders ARGUS as stylized block letters
        assert "___" in wm
        assert len(wm.split("\n")) >= 4

    def test_logo_contains_all(self):
        full = logo()
        assert "VISION" in full
        assert "CONSTITUTION" in full
        assert "PIPELINE" in full
        assert "Truth Before Fluency" in full
        assert "Never Guess" in full

    def test_logo_mentions_blueprint_concepts(self):
        full = logo()
        assert "goal, bukan sekadar prompt" in full
        assert "Small by Default" in full

    def test_render_logo_jpeg(self, tmp_path):
        out = tmp_path / "logo.jpg"
        path = render_logo_jpeg(str(out), width=600)
        assert out.exists()
        assert out.stat().st_size > 10_000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
