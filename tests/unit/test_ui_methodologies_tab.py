"""Tests for Methodologies UI page."""

from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


def _get_app_path():
    # Resolve to repo root / ui / pages / 07_methodologies.py
    return str(
        Path(__file__).resolve().parents[2] / "ui" / "pages" / "07_methodologies.py"
    )


def test_page_renders():
    app_path = _get_app_path()
    with (
        patch(
            "backend.services.methodology_ranking_service.rank_by_methodology",
            return_value=[],
        ),
        patch(
            "backend.services.methodology_ranking_service.rank_combined",
            return_value=[],
        ),
    ):
        at = AppTest.from_file(app_path, default_timeout=30)
        at.run()
        assert not at.exception


def test_tab_single_renders_selector():
    app_path = _get_app_path()
    with (
        patch(
            "backend.services.methodology_ranking_service.rank_by_methodology",
            return_value=[],
        ),
        patch(
            "backend.services.methodology_ranking_service.rank_combined",
            return_value=[],
        ),
    ):
        at = AppTest.from_file(app_path, default_timeout=30)
        at.run()
        assert not at.exception
        assert len(at.selectbox) >= 1


def test_tab_combine_renders_multiselect():
    app_path = _get_app_path()
    with (
        patch(
            "backend.services.methodology_ranking_service.rank_by_methodology",
            return_value=[],
        ),
        patch(
            "backend.services.methodology_ranking_service.rank_combined",
            return_value=[],
        ),
    ):
        at = AppTest.from_file(app_path, default_timeout=30)
        at.run()
        assert not at.exception
        assert len(at.multiselect) >= 1


def test_strategy_default_and():
    app_path = _get_app_path()
    with (
        patch(
            "backend.services.methodology_ranking_service.rank_by_methodology",
            return_value=[],
        ),
        patch(
            "backend.services.methodology_ranking_service.rank_combined",
            return_value=[],
        ),
    ):
        at = AppTest.from_file(app_path, default_timeout=30)
        at.run()
        assert not at.exception
        assert len(at.radio) >= 1


def test_methodologies_page_is_registered_in_navigation():
    """AUDIT-002: 07_methodologies must be part of st.navigation."""
    source = (Path(__file__).resolve().parents[2] / "ui" / "app.py").read_text(
        encoding="utf-8"
    )
    assert 'st.Page("pages/07_methodologies.py", title="Methodologies")' in source
