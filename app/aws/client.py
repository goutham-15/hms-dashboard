from __future__ import annotations

from typing import Any, Optional

import boto3
from langchain_aws.chat_models import ChatBedrock

from app.utils.config import settings
from app.utils.logger import get_logger


logger = get_logger(name="aws_client")


class AWSClient:
    """
    Minimal AWS Bedrock client built on boto3 and project settings.
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
        self.region = (region or settings.aws.bedrock.region or "").strip() or None

        cfg_access = (settings.aws.access_key or "").strip()
        cfg_secret = (settings.aws.secret_key or "").strip()

        ak = (access_key or cfg_access).strip() if (access_key or cfg_access) else ""
        sk = (secret_key or cfg_secret).strip() if (secret_key or cfg_secret) else ""
        token = (session_token or "").strip() or None

        self._session: boto3.Session
        if profile:
            logger.info("Using AWS profile=%s region=%s", profile, self.region)
            self._session = boto3.Session(profile_name=profile, region_name=self.region)
        elif ak and sk:
            logger.info("Using explicit AWS credentials region=%s", self.region)
            self._session = boto3.Session(
                aws_access_key_id=ak,
                aws_secret_access_key=sk,
                aws_session_token=token,
                region_name=self.region,
            )
        else:
            logger.info("Using default AWS credential chain region=%s", self.region)
            self._session = boto3.Session(region_name=self.region)

        self._bedrock_runtime = self._session.client(
            "bedrock-runtime",
            region_name=self.region,
        )

    def bedrock_runtime(self) -> Any:
        return self._bedrock_runtime

    def bedrock_chat(self, *, model_kwargs: Optional[dict[str, Any]] = None) -> ChatBedrock:
        return ChatBedrock(
            client=self._bedrock_runtime,
            model_id=settings.aws.bedrock.model_id,
            model_kwargs=model_kwargs or {"temperature": 0.0},
        )