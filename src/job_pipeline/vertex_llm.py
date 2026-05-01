"""Vertex AI flavor of applypilot's LLMClient.

Subclasses ``applypilot.llm.LLMClient`` to:
  - Authenticate via a Google Cloud service account (1-hour OAuth tokens)
  - Refresh tokens on demand (each call reads ``self.api_key``, which we
    expose as a property that refreshes when expired)
  - Route to Vertex's OpenAI-compatible Gemini endpoint
  - Auto-prefix the model name with ``google/`` (Vertex requires it; the
    consumer Gemini API rejects it — that asymmetry is exactly what bit us)

Wired up via ``patches.apply_patches()`` when VERTEX_SA_KEY + VERTEX_PROJECT
+ VERTEX_LOCATION are present in the environment.
"""
from __future__ import annotations

from pathlib import Path

from applypilot.llm import LLMClient
from google.auth.transport.requests import Request
from google.oauth2 import service_account


_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


class VertexLLMClient(LLMClient):
    """LLMClient backed by Vertex AI service-account auth."""

    def __init__(
        self,
        sa_key_path: str,
        project: str,
        location: str,
        model: str,
    ) -> None:
        # Load credentials BEFORE super().__init__ so the api_key property
        # has self._creds available when the parent assigns self.api_key.
        path = Path(sa_key_path).expanduser()
        self._creds = service_account.Credentials.from_service_account_file(
            str(path), scopes=_SCOPES,
        )
        self._google_request = Request()

        # Vertex requires provider-prefixed model names; consumer Gemini rejects them.
        if "/" not in model:
            model = f"google/{model}"

        base_url = (
            f"https://{location}-aiplatform.googleapis.com/v1beta1/"
            f"projects/{project}/locations/{location}/endpoints/openapi"
        )
        # Parent stores api_key as instance attr; we shadow it with a property below.
        super().__init__(base_url, model, "")
        # No native-Gemini fallback — Vertex serves OpenAI-compat directly.
        self._is_gemini = False

    @property
    def api_key(self) -> str:
        """Always return a non-expired bearer token."""
        if not self._creds.valid:
            self._creds.refresh(self._google_request)
        return self._creds.token

    @api_key.setter
    def api_key(self, _value: str) -> None:
        # Parent's __init__ calls `self.api_key = api_key`; ignore since we
        # source the token from self._creds dynamically.
        pass
