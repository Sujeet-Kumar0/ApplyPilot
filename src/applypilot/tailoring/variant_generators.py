"""Variant generators for resume bullet tailoring.

Provides LLM-powered variant generation with strict metrics preservation.
Each generator follows a specific format (CAR, WHO, Technical, Product)
and includes fallback to original text on failure.
"""

import logging
import re

log = logging.getLogger(__name__)

# Base instruction for all prompts to preserve metrics
_METRICS_PRESERVATION = (
    "Preserve all numbers and metrics exactly. Do not change, round, or fabricate any numerical values."
)


def generate_car_variant(text: str, client, job_context: dict = None) -> str:
    """Generate Challenge-Action-Result variant.

    Emphasizes the CAR structure: Context/Challenge, Action taken, Result achieved.
    Best for demonstrating problem-solving and measurable outcomes.

    Args:
        text: Original bullet text
        client: LLM client with ask() method
        job_context: Optional job context for targeting

    Returns:
        Rewritten bullet in CAR format, or original text on failure
    """
    job_info = f" for {job_context.get('title', 'the target role')}" if job_context else ""

    prompt = (
        f"Rewrite this resume bullet using Challenge-Action-Result (CAR) format.\n\n"
        f"Structure:\n"
        f"- Challenge: The problem or situation faced\n"
        f"- Action: What you specifically did (include technologies/mechanisms)\n"
        f"- Result: The measurable outcome\n\n"
        f"Requirements:\n"
        f"- Keep to one concise line\n"
        f"- Start with a strong action verb\n"
        f"- Include specific technologies where relevant\n"
        f"- {_METRICS_PRESERVATION}\n\n"
        f"Original: {text}\n"
        f"Target Job{job_info}\n\n"
        f"Rewritten bullet:"
    )

    try:
        return client.ask(prompt, temperature=0.7)
    except Exception as exc:
        log.warning("CAR variant generation failed: %s. Returning original.", exc)
        return text


def generate_who_variant(text: str, client, job_context: dict = None) -> str:
    """Generate What-How-Outcome variant.

    Emphasizes the WHO structure: What was done, How it was done, Outcome achieved.
    Best for product management and leadership roles.

    Args:
        text: Original bullet text
        client: LLM client with ask() method
        job_context: Optional job context for targeting

    Returns:
        Rewritten bullet in WHO format, or original text on failure
    """
    job_info = f" for {job_context.get('title', 'the target role')}" if job_context else ""

    prompt = (
        f"Rewrite this resume bullet using What-How-Outcome (WHO) format.\n\n"
        f"Structure:\n"
        f"- What: The achievement or deliverable\n"
        f"- How: The method, approach, or leadership applied\n"
        f"- Outcome: The business result or impact\n\n"
        f"Requirements:\n"
        f"- Keep to one concise line\n"
        f"- Emphasize scope and strategic impact\n"
        f"- Include stakeholder or cross-functional elements where relevant\n"
        f"- {_METRICS_PRESERVATION}\n\n"
        f"Original: {text}\n"
        f"Target Job{job_info}\n\n"
        f"Rewritten bullet:"
    )

    try:
        return client.ask(prompt, temperature=0.7)
    except Exception as exc:
        log.warning("WHO variant generation failed: %s. Returning original.", exc)
        return text


def generate_technical_variant(text: str, client, job_context: dict = None) -> str:
    """Generate technically-focused variant.

    Emphasizes specific technologies, architectures, algorithms, and technical depth.
    Best for engineering and technical roles.

    Args:
        text: Original bullet text
        client: LLM client with ask() method
        job_context: Optional job context for targeting

    Returns:
        Rewritten bullet emphasizing technical depth, or original text on failure
    """
    job_info = f" for {job_context.get('title', 'the target role')}" if job_context else ""

    prompt = (
        f"Rewrite this resume bullet to emphasize technical depth and implementation details.\n\n"
        f"Focus on:\n"
        f"- Specific technologies, frameworks, and tools used\n"
        f"- System architecture and design decisions\n"
        f"- Algorithms, data structures, or technical approaches\n"
        f"- Scale, performance, or infrastructure details\n\n"
        f"Requirements:\n"
        f"- Keep to one concise line\n"
        f"- Lead with the technical mechanism\n"
        f"- Include concrete technical artifacts (APIs, pipelines, models)\n"
        f"- {_METRICS_PRESERVATION}\n\n"
        f"Original: {text}\n"
        f"Target Job{job_info}\n\n"
        f"Rewritten bullet:"
    )

    try:
        return client.ask(prompt, temperature=0.7)
    except Exception as exc:
        log.warning("Technical variant generation failed: %s. Returning original.", exc)
        return text


def generate_product_variant(text: str, client, job_context: dict = None) -> str:
    """Generate product-impact-focused variant.

    Emphasizes business metrics, user impact, revenue/growth, and strategic outcomes.
    Best for product management and business-focused roles.

    Args:
        text: Original bullet text
        client: LLM client with ask() method
        job_context: Optional job context for targeting

    Returns:
        Rewritten bullet emphasizing product impact, or original text on failure
    """
    job_info = f" for {job_context.get('title', 'the target role')}" if job_context else ""

    prompt = (
        f"Rewrite this resume bullet to emphasize product impact and business outcomes.\n\n"
        f"Focus on:\n"
        f"- Business metrics (revenue, growth, efficiency)\n"
        f"- User impact and customer outcomes\n"
        f"- Strategic importance and scope\n"
        f"- Cross-functional leadership and stakeholder alignment\n\n"
        f"Requirements:\n"
        f"- Keep to one concise line\n"
        f"- Lead with the business outcome or user impact\n"
        f"- Quantify results where possible\n"
        f"- {_METRICS_PRESERVATION}\n\n"
        f"Original: {text}\n"
        f"Target Job{job_info}\n\n"
        f"Rewritten bullet:"
    )

    try:
        return client.ask(prompt, temperature=0.7)
    except Exception as exc:
        log.warning("Product variant generation failed: %s. Returning original.", exc)
        return text


def _extract_numbers(text: str) -> set[str]:
    """Extract all numeric values from text as strings."""
    # Match integers, decimals, percentages, currency
    pattern = r"\d+(?:\.\d+)?(?:%|\s*(?:USD|EUR|GBP|\$|€|£))?"
    return set(re.findall(pattern, text))


def validate_variant_metrics(original: str, variant: str, registry: dict) -> str:
    """Validate that variant metrics are verified against registry.

    Checks if the variant contains any metrics not present in the original
    or not verified in the registry. Returns original text if hallucinated
    metrics are detected.

    Args:
        original: Original bullet text with verified metrics
        variant: LLM-generated variant to validate
        registry: MetricsRegistry or dict mapping metric strings to verification status

    Returns:
        Variant if all metrics are verified, otherwise original text
    """
    # Extract numbers from both texts
    original_nums = _extract_numbers(original)
    variant_nums = _extract_numbers(variant)

    # Check for new numbers in variant not in original
    new_numbers = variant_nums - original_nums

    if not new_numbers:
        # No new numbers, variant is safe
        return variant

    # Check if new numbers are in registry
    if registry:
        # Handle both MetricsRegistry objects and dicts
        if hasattr(registry, "is_verified"):
            # MetricsRegistry object
            for num in new_numbers:
                if not registry.is_verified(num):
                    log.warning("Rejecting variant with unverified metric '%s' not in registry", num)
                    return original
        elif isinstance(registry, dict):
            # Dict of verified metrics
            for num in new_numbers:
                if num not in registry:
                    log.warning("Rejecting variant with unverified metric '%s' not in registry", num)
                    return original
    else:
        # No registry provided, reject if any new numbers
        log.warning("Rejecting variant with new metrics (no registry): %s", new_numbers)
        return original

    # All new numbers are verified
    return variant
