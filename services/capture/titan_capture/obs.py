"""Re-export OBS websocket client (implementation in titan_core)."""

from titan_core.obs_ws import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    OP_IDENTIFIED,
    OP_REQUEST,
    OP_REQUEST_RESPONSE,
    ObsClient,
    ObsRecordStatus,
    make_obs_client,
    obs_auth_string,
)

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "OP_IDENTIFIED",
    "OP_REQUEST",
    "OP_REQUEST_RESPONSE",
    "ObsClient",
    "ObsRecordStatus",
    "make_obs_client",
    "obs_auth_string",
]
