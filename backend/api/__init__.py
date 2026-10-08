"""Value Investing REST API — additive layer for the mobile app.

The API orchestrates the same services the CLI and the Streamlit UI use; it
never reimplements analysis logic and never persists prices. See
``docs/api_design.md`` and roadmap issue #27.

Run locally with::

    uvicorn backend.api.app:app --reload
"""

API_VERSION = "v1"
