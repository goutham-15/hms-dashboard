from __future__ import annotations

from typing import Any, Optional

import boto3

from app.utils.config import settings
from app.utils.logger import get_logger


logger = get_logger(name="aws_client")


class AWSClient:
    """
    Centralized boto3 session/client factory.

    Credential resolution order:
    1) Explicit arguments to AWSClient(...)
    2) config.yaml via app.utils.config.settings (aws.access_key/aws.secret_key)
    3) Standard boto3 resolution chain (env vars, shared config, IMDS, etc.)
    """

    def __init__(
        self,
        *,
        region: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        session_token: Optional[str] = None,
        profile: Optional[str] = None,
    ) -> None:
        resolved_region = (region or settings.aws.bedrock.region or "").strip() or None

        cfg_access = (settings.aws.access_key or "").strip()
        cfg_secret = (settings.aws.secret_key or "").strip()

        resolved_access = (access_key or cfg_access).strip() if (access_key or cfg_access) else ""
        resolved_secret = (secret_key or cfg_secret).strip() if (secret_key or cfg_secret) else ""
        resolved_token = (session_token or "").strip() or None

        self.region = resolved_region
        self.profile = (profile or "").strip() or None
        self._clients: dict[str, Any] = {}

        if self.profile:
            logger.info("Initializing boto3 session using AWS profile=%s region=%s", self.profile, self.region)
            self._session = boto3.Session(profile_name=self.profile, region_name=self.region)
        elif resolved_access and resolved_secret:
            logger.info("Initializing boto3 session using explicit credentials region=%s", self.region)
            self._session = boto3.Session(
                aws_access_key_id=resolved_access,
                aws_secret_access_key=resolved_secret,
                aws_session_token=resolved_token,
                region_name=self.region,
            )
        else:
            logger.info("Initializing boto3 session using default credential chain region=%s", self.region)
            self._session = boto3.Session(region_name=self.region)

    def client(self, service_name: str, **kwargs: Any) -> Any:
        """
        Create a boto3 client. For default (no kwargs) clients, the instance is cached.
        """
        if not kwargs:
            cached = self._clients.get(service_name)
            if cached is not None:
                return cached

        if "region_name" not in kwargs and self.region:
            kwargs["region_name"] = self.region

        client = self._session.client(service_name, **kwargs)

        if not kwargs:
            self._clients[service_name] = client
        return client

    def bedrock_runtime(self, **kwargs: Any) -> Any:
        return self.client("bedrock-runtime", **kwargs)
