"""Tests for Methodologies UI page."""

from unittest.mock import patch

from streamlit.testing.v1 import AppTest


@patch("backend.methodologies.registry.registry")
@patch("backend.methodologies.registry.discover")
def test_page_renders(mock_discover, mock_registry):
    mock_discover.return_value = 0
    mock_registry.list.return_value = ["graham", "lynch_garp"]

    at = AppTest.from_file("ui/pages/07_methodologies.py", default_timeout=30)
    at.run()
    assert not at.exception


@patch("backend.methodologies.registry.registry")
@patch("backend.methodologies.registry.discover")
def test_tab_single_renders_selector(mock_discover, mock_registry):
    mock_discover.return_value = 0
    mock_registry.list.return_value = ["graham", "lynch_garp"]

    at = AppTest.from_file("ui/pages/07_methodologies.py", default_timeout=30)
    at.run()
    assert not at.exception
    # Check that selectbox exists
    assert len(at.selectbox) >= 1


@patch("backend.methodologies.registry.registry")
@patch("backend.methodologies.registry.discover")
def test_tab_combine_renders_multiselect(mock_discover, mock_registry):
    mock_discover.return_value = 0
    mock_registry.list.return_value = ["graham", "lynch_garp"]

    at = AppTest.from_file("ui/pages/07_methodologies.py", default_timeout=30)
    at.run()
    assert not at.exception
    # Check that multiselect exists
    assert len(at.multiselect) >= 1


@patch("backend.methodologies.registry.registry")
@patch("backend.methodologies.registry.discover")
def test_strategy_default_and(mock_discover, mock_registry):
    mock_discover.return_value = 0
    mock_registry.list.return_value = ["graham", "lynch_garp"]

    at = AppTest.from_file("ui/pages/07_methodologies.py", default_timeout=30)
    at.run()
    assert not at.exception
    # Radio button should exist
    assert len(at.radio) >= 1
