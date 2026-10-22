"""Zetaris federated data layer."""

from app.integrations.zetaris.client import ZetarisClient, ZetarisError, get_zetaris_client

__all__ = ["ZetarisClient", "ZetarisError", "get_zetaris_client"]
