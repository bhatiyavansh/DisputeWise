"""Part E -- grounded response generation orchestration.

Wires prompt.py + an LLMProvider together and validates the raw provider
output against a strict schema before anything downstream touches it. A
provider returning malformed structure is a hard error here (LLMOutputError)
-- it is never silently coerced or partially accepted, and it is NEVER
treated as a verified/grounded response (that's verifier.py's job, run
separately and always, in service.py).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from app.evidence_intel import versions as v
from app.evidence_intel.llm_provider import LLMGenerationError, LLMProvider
from app.evidence_intel.packet import EvidencePacket
from app.evidence_intel.prompt import RESPONSE_JSON_SCHEMA, SYSTEM_PROMPT, TOOL_NAME, build_user_prompt
from app.evidence_intel.retrieval import RetrievalResult


class LLMOutputError(RuntimeError):
    """No usable draft was produced.

    Deliberately the single type callers handle: every failure below it means
    "there is no draft", and the response_state contract treats them
    identically (DRAFT_BLOCKED) -- that behavior is unchanged.
    """


class ProviderUnavailableError(LLMOutputError):
    """The provider could not be reached, refused, or returned no usable
    structured output at all (network failure, rate limit, upstream outage,
    missing/malformed tool call).

    A SUBCLASS of LLMOutputError purely so it can be reported more precisely
    to an operator -- every existing `except LLMOutputError` and
    `pytest.raises(LLMOutputError)` still catches it, and the response_state
    it produces is unchanged. This is an additive distinction, not a change
    to the Phase 4 state machine: it exists so the UI can say "AI generation
    is temporarily unavailable" instead of implying the verifier rejected a
    draft that was never written.
    """


class InvalidOutputError(LLMOutputError):
    """The provider returned structured output that failed schema validation.

    Distinct from ProviderUnavailableError because the provider *worked* --
    it just produced something that does not conform. Also a subclass, for
    the same backward-compatibility reason.
    """


class GeneratedClaim(BaseModel):
    claim_id: str
    text: str
    claim_type: str = Field(pattern="|".join(v.CLAIM_TYPES))
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class GeneratedDraft(BaseModel):
    summary: str
    claims: list[GeneratedClaim]
    missing_evidence: list[str] = Field(default_factory=list)
    response_body: str

    prompt_version: str = v.PROMPT_VERSION
    response_schema_version: str = v.RESPONSE_SCHEMA_VERSION


def generate_draft(
    packet: EvidencePacket,
    retrieval_results: list[RetrievalResult],
    provider: LLMProvider,
) -> GeneratedDraft:
    user_prompt = build_user_prompt(packet, retrieval_results)

    try:
        raw = provider.complete_structured(
            system=SYSTEM_PROMPT,
            user=user_prompt,
            schema=RESPONSE_JSON_SCHEMA,
            tool_name=TOOL_NAME,
        )
    except LLMGenerationError as exc:
        raise ProviderUnavailableError(f"provider '{provider.name}' failed to generate: {exc}") from exc

    try:
        return GeneratedDraft.model_validate(raw)
    except ValidationError as exc:
        raise InvalidOutputError(
            f"provider '{provider.name}' returned output that failed schema validation: {exc}"
        ) from exc
