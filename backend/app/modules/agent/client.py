"""Vendor-neutral OpenAI-compatible structured model client."""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from backend.app.modules.agent.crypto import CredentialCipher, CredentialUnavailableError
from backend.app.modules.agent.repository import AgentRepository


class ModelClientError(RuntimeError):
    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        usage_estimated: bool = False,
        cost: Decimal = Decimal("0"),
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.usage_estimated = usage_estimated
        self.cost = cost


@dataclass(frozen=True)
class ModelConfiguration:
    provider_url: str
    model_name: str
    api_key: str
    input_price: Decimal
    output_price: Decimal
    currency: str
    request_timeout: float
    max_iterations: int
    max_output_tokens: int


@dataclass(frozen=True)
class ModelResult:
    content: dict[str, Any]
    input_tokens: int
    output_tokens: int
    usage_estimated: bool
    cost: Decimal


class OpenAICompatibleClient:
    def __init__(
        self,
        repository: AgentRepository,
        cipher: CredentialCipher,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.repository = repository
        self.cipher = cipher
        self.transport = transport

    async def configuration(self, user_id: int) -> ModelConfiguration:
        row = await self.repository.get_config_row(user_id)
        if row is None:
            raise ModelClientError("model_not_configured", "Model configuration is missing")
        try:
            api_key = self.cipher.decrypt(row["encrypted_api_key"])
        except CredentialUnavailableError as exc:
            raise ModelClientError("encryption_unavailable", str(exc)) from exc
        return ModelConfiguration(
            provider_url=row["provider_url"],
            model_name=row["model_name"],
            api_key=api_key,
            input_price=Decimal(row["input_price"]),
            output_price=Decimal(row["output_price"]),
            currency=row["currency"],
            request_timeout=float(row["request_timeout"]),
            max_iterations=int(row["max_iterations"]),
            max_output_tokens=int(row["max_output_tokens"]),
        )

    async def complete(self, user_id: int, messages: list[dict[str, str]]) -> ModelResult:
        config = await self.configuration(user_id)
        url = config.provider_url
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        payload: dict[str, Any] = {
            "model": config.model_name,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "max_tokens": min(config.max_output_tokens, 16000),
            "temperature": 0.2,
        }
        # GLM-5.3 requires thinking enabled; low is its fastest supported effort.
        # Do not send vendor-specific parameters to unrelated compatible models.
        model = config.model_name.lower().rsplit("/", 1)[-1]
        if model in {"glm-5.3", "glm-5.3-flash"}:
            payload.update(thinking={"type": "enabled"}, reasoning_effort="low")
        try:
            async with httpx.AsyncClient(
                timeout=min(config.request_timeout, 240.0),
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {config.api_key}"},
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ModelClientError("model_timeout", "Model request timed out") from exc
        except httpx.RequestError as exc:
            raise ModelClientError(
                "model_connection_failed", "Model service is unavailable"
            ) from exc
        if response.status_code == 401:
            raise ModelClientError("model_unauthorized", "Model provider rejected the credential")
        if response.status_code == 429:
            raise ModelClientError("model_rate_limited", "Model provider rate limit exceeded")
        if response.status_code >= 500:
            raise ModelClientError("model_server_error", "Model provider failed")
        if response.status_code >= 400:
            raise ModelClientError("model_request_rejected", "Model provider rejected the request")
        try:
            body = response.json()
            raw_content = body["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelClientError("invalid_model_response", "Model returned invalid JSON") from exc
        try:
            content = raw_content if isinstance(raw_content, dict) else _parse_json(raw_content)
        except (ValueError, TypeError) as exc:
            input_tokens, output_tokens, estimated = _usage(body, messages, raw_content)
            cost = _cost(input_tokens, output_tokens, config)
            raise ModelClientError(
                "invalid_model_response",
                "Model returned invalid JSON",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                usage_estimated=estimated,
                cost=cost,
            ) from exc
        input_tokens, output_tokens, estimated = _usage(body, messages, content)
        cost = _cost(input_tokens, output_tokens, config)
        return ModelResult(content, input_tokens, output_tokens, estimated, cost)

    async def test_connection(self, user_id: int) -> ModelResult:
        return await self.complete(
            user_id,
            [
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": 'Return exactly {"ok":true}.'},
            ],
        )


def _usage(body: Any, messages: list[dict[str, str]], content: Any) -> tuple[int, int, bool]:
    usage = body.get("usage") if isinstance(body, dict) else None
    estimated = not isinstance(usage, dict)
    if estimated:
        prompt_text = json.dumps(messages, ensure_ascii=False)
        output_text = (
            content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        )
        input_tokens = max(1, (len(prompt_text) + 3) // 4)
        output_tokens = max(1, (len(output_text) + 3) // 4)
    else:
        input_tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)))
        output_tokens = int(usage.get("completion_tokens", usage.get("output_tokens", 0)))
        if input_tokens <= 0 or output_tokens <= 0:
            estimated = True
            input_tokens = max(input_tokens, (len(json.dumps(messages)) + 3) // 4)
            output_tokens = max(output_tokens, (len(str(content)) + 3) // 4)
    return input_tokens, output_tokens, estimated


def _cost(input_tokens: int, output_tokens: int, config: ModelConfiguration) -> Decimal:
    return (
        Decimal(input_tokens) * config.input_price + Decimal(output_tokens) * config.output_price
    ) / Decimal(1_000_000)


def _parse_json(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ValueError("content is not text")
    stripped = value.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1])
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("structured response is not an object")
    return parsed
