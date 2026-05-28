"""Secret resolution: env vars or AWS Secrets Manager / SSM Parameter Store."""
from __future__ import annotations

import os
from typing import Protocol


class SecretProvider(Protocol):
    """Resolves a secret reference to its plaintext value."""

    def get(self, ref: str) -> str:
        """Return the secret value for the given reference."""
        ...


class EnvSecretProvider:
    """Reads secrets from environment variables (the no-dependency default)."""

    def get(self, ref: str) -> str:
        """Return the environment variable named by ref."""
        return os.environ[ref]


class AwsSecretProvider:
    """Reads secrets from AWS Secrets Manager or SSM Parameter Store.

    Reference format: 'ssm:/path/name' for Parameter Store, 'secretsmanager:name'
    (or a bare name) for Secrets Manager. boto3 is imported lazily so the
    dependency is only required when this provider is actually used.
    """

    def get(self, ref: str) -> str:
        """Resolve ref from SSM (ssm:...) or Secrets Manager (default)."""
        import boto3  # lazy: only needed on the AWS path

        kind, sep, name = ref.partition(":")
        if sep and kind == "ssm":
            result = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)
            return str(result["Parameter"]["Value"])
        secret_id = name if sep and kind == "secretsmanager" else ref
        result = boto3.client("secretsmanager").get_secret_value(SecretId=secret_id)
        return str(result["SecretString"])
