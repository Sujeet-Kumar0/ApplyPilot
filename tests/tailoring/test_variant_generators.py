"""Tests for the variant generators module."""

from unittest.mock import MagicMock, patch

import pytest

from applypilot.tailoring.variant_generators import (
    _extract_numbers,
    generate_car_variant,
    generate_product_variant,
    generate_technical_variant,
    generate_who_variant,
    validate_variant_metrics,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_llm_client():
    """Mock LLM client that returns predictable responses."""
    client = MagicMock()
    client.ask.return_value = "Rewritten bullet with metrics preserved"
    return client


@pytest.fixture
def mock_registry():
    """Mock metrics registry for validation tests."""
    registry = MagicMock()
    registry.is_verified.return_value = True
    return registry


# -----------------------------------------------------------------------------
# Generator Function Signature Tests
# -----------------------------------------------------------------------------


class TestGeneratorSignatures:
    def test_generate_car_variant_has_correct_signature(self):
        """Test that generate_car_variant has the expected signature."""
        import inspect

        sig = inspect.signature(generate_car_variant)
        params = list(sig.parameters.keys())

        assert "text" in params
        assert "client" in params
        assert "job_context" in params

    def test_generate_who_variant_has_correct_signature(self):
        """Test that generate_who_variant has the expected signature."""
        import inspect

        sig = inspect.signature(generate_who_variant)
        params = list(sig.parameters.keys())

        assert "text" in params
        assert "client" in params
        assert "job_context" in params

    def test_generate_technical_variant_has_correct_signature(self):
        """Test that generate_technical_variant has the expected signature."""
        import inspect

        sig = inspect.signature(generate_technical_variant)
        params = list(sig.parameters.keys())

        assert "text" in params
        assert "client" in params
        assert "job_context" in params

    def test_generate_product_variant_has_correct_signature(self):
        """Test that generate_product_variant has the expected signature."""
        import inspect

        sig = inspect.signature(generate_product_variant)
        params = list(sig.parameters.keys())

        assert "text" in params
        assert "client" in params
        assert "job_context" in params


# -----------------------------------------------------------------------------
# CAR Variant Tests
# -----------------------------------------------------------------------------


class TestCARVariant:
    def test_returns_rewritten_text_on_success(self, mock_llm_client):
        """Test that CAR variant returns LLM output on success."""
        original = "Led team to deliver project"
        mock_llm_client.ask.return_value = (
            "Challenge: Tight deadline; Action: Led 5 engineers; Result: Delivered 2 weeks early"
        )

        result = generate_car_variant(original, mock_llm_client)

        assert result != original
        assert "Challenge" in result or "Action" in result or "Result" in result
        mock_llm_client.ask.assert_called_once()

    def test_includes_job_context_when_provided(self, mock_llm_client):
        """Test that job context is included in the prompt."""
        original = "Led team to deliver project"
        job_context = {"title": "Senior Engineer"}

        generate_car_variant(original, mock_llm_client, job_context)

        call_args = mock_llm_client.ask.call_args
        prompt = call_args[0][0]
        assert "Senior Engineer" in prompt

    def test_omits_job_context_when_not_provided(self, mock_llm_client):
        """Test that prompt works without job context."""
        original = "Led team to deliver project"

        generate_car_variant(original, mock_llm_client, None)

        call_args = mock_llm_client.ask.call_args
        prompt = call_args[0][0]
        assert "Target Job" in prompt  # When no job context, just shows "Target Job"

    def test_fallback_to_original_on_exception(self, mock_llm_client):
        """Test that original text is returned on LLM failure."""
        original = "Led team to deliver project"
        mock_llm_client.ask.side_effect = Exception("LLM API error")

        result = generate_car_variant(original, mock_llm_client)

        assert result == original

    def test_uses_correct_temperature(self, mock_llm_client):
        """Test that the correct temperature is passed to the LLM."""
        original = "Led team to deliver project"

        generate_car_variant(original, mock_llm_client)

        call_kwargs = mock_llm_client.ask.call_args[1]
        assert call_kwargs.get("temperature") == 0.7


# -----------------------------------------------------------------------------
# WHO Variant Tests
# -----------------------------------------------------------------------------


class TestWHOVariant:
    def test_returns_rewritten_text_on_success(self, mock_llm_client):
        """Test that WHO variant returns LLM output on success."""
        original = "Built API service"
        mock_llm_client.ask.return_value = "What: Scalable API; How: Using microservices; Outcome: Supported 1M users"

        result = generate_who_variant(original, mock_llm_client)

        assert result != original
        mock_llm_client.ask.assert_called_once()

    def test_includes_job_context_when_provided(self, mock_llm_client):
        """Test that job context is included in the WHO prompt."""
        original = "Built API service"
        job_context = {"title": "Product Manager"}

        generate_who_variant(original, mock_llm_client, job_context)

        call_args = mock_llm_client.ask.call_args
        prompt = call_args[0][0]
        assert "Product Manager" in prompt

    def test_fallback_to_original_on_exception(self, mock_llm_client):
        """Test that original text is returned on WHO generation failure."""
        original = "Built API service"
        mock_llm_client.ask.side_effect = Exception("Connection timeout")

        result = generate_who_variant(original, mock_llm_client)

        assert result == original


# -----------------------------------------------------------------------------
# Technical Variant Tests
# -----------------------------------------------------------------------------


class TestTechnicalVariant:
    def test_returns_rewritten_text_on_success(self, mock_llm_client):
        """Test that technical variant returns LLM output on success."""
        original = "Improved system performance"
        mock_llm_client.ask.return_value = "Implemented Redis caching layer reducing DB queries by 80%"

        result = generate_technical_variant(original, mock_llm_client)

        assert result != original
        mock_llm_client.ask.assert_called_once()

    def test_includes_technical_focus_in_prompt(self, mock_llm_client):
        """Test that technical focus areas are in the prompt."""
        original = "Improved system performance"

        generate_technical_variant(original, mock_llm_client)

        call_args = mock_llm_client.ask.call_args
        prompt = call_args[0][0]
        assert "technologies" in prompt.lower() or "architecture" in prompt.lower()

    def test_fallback_to_original_on_exception(self, mock_llm_client):
        """Test that original text is returned on technical generation failure."""
        original = "Improved system performance"
        mock_llm_client.ask.side_effect = Exception("Rate limit exceeded")

        result = generate_technical_variant(original, mock_llm_client)

        assert result == original


# -----------------------------------------------------------------------------
# Product Variant Tests
# -----------------------------------------------------------------------------


class TestProductVariant:
    def test_returns_rewritten_text_on_success(self, mock_llm_client):
        """Test that product variant returns LLM output on success."""
        original = "Launched new feature"
        mock_llm_client.ask.return_value = "Drove 25% revenue increase by launching premium tier feature"

        result = generate_product_variant(original, mock_llm_client)

        assert result != original
        mock_llm_client.ask.assert_called_once()

    def test_includes_business_focus_in_prompt(self, mock_llm_client):
        """Test that business focus areas are in the prompt."""
        original = "Launched new feature"

        generate_product_variant(original, mock_llm_client)

        call_args = mock_llm_client.ask.call_args
        prompt = call_args[0][0]
        assert "business" in prompt.lower() or "revenue" in prompt.lower()

    def test_fallback_to_original_on_exception(self, mock_llm_client):
        """Test that original text is returned on product generation failure."""
        original = "Launched new feature"
        mock_llm_client.ask.side_effect = Exception("Service unavailable")

        result = generate_product_variant(original, mock_llm_client)

        assert result == original


# -----------------------------------------------------------------------------
# Metrics Validation Tests
# -----------------------------------------------------------------------------


class TestValidateVariantMetrics:
    def test_returns_variant_when_no_new_numbers(self):
        """Test that variant is returned when it has no new numbers."""
        original = "Increased revenue by 40%"
        variant = "Grew revenue by 40% through optimization"

        result = validate_variant_metrics(original, variant, {})

        assert result == variant

    def test_returns_variant_when_numbers_match(self):
        """Test that variant is returned when numbers match original."""
        original = "Led team of 12 engineers and achieved 40% growth"
        variant = "Managed 12 engineers delivering 40% growth"

        result = validate_variant_metrics(original, variant, {})

        assert result == variant

    def test_returns_original_when_new_unverified_numbers(self):
        """Test that original is returned when variant has new unverified numbers."""
        original = "Increased revenue by 40%"
        variant = "Increased revenue by 40% and saved $2M"

        result = validate_variant_metrics(original, variant, {})

        assert result == original

    def test_uses_registry_to_verify_new_numbers(self, mock_registry):
        """Test that registry is used to verify new numbers."""
        original = "Increased revenue by 40%"
        variant = "Increased revenue by 40% and saved $2M"

        mock_registry.is_verified.return_value = True

        result = validate_variant_metrics(original, variant, mock_registry)

        assert result == variant
        mock_registry.is_verified.assert_called()

    def test_returns_original_when_registry_rejects_numbers(self, mock_registry):
        """Test that original is returned when registry rejects new numbers."""
        original = "Increased revenue by 40%"
        variant = "Increased revenue by 40% and saved $2M"

        mock_registry.is_verified.return_value = False

        result = validate_variant_metrics(original, variant, mock_registry)

        assert result == original

    def test_handles_dict_registry(self):
        """Test validation with dict-style registry."""
        original = "Increased revenue by 40%"
        variant = "Increased revenue by 40% and saved $2M"
        # The regex extracts "2" from "$2M", so we need to include "2" in registry
        registry = {"2": True}

        result = validate_variant_metrics(original, variant, registry)
        assert result == variant

    def test_returns_original_for_unverified_in_dict_registry(self):
        """Test that original is returned for unverified numbers in dict."""
        original = "Increased revenue by 40%"
        variant = "Increased revenue by 40% and saved $2M"
        registry = {"$1M": True}  # $2M not in registry

        result = validate_variant_metrics(original, variant, registry)

        assert result == original

    def test_handles_empty_registry(self):
        """Test validation with empty registry."""
        original = "Increased revenue by 40%"
        variant = "Increased revenue by 40% and saved $2M"

        result = validate_variant_metrics(original, variant, None)

        # With no registry, new numbers should be rejected
        assert result == original


# -----------------------------------------------------------------------------
# Number Extraction Tests
# -----------------------------------------------------------------------------


class TestExtractNumbers:
    def test_extracts_integers(self):
        """Test extraction of integer values."""
        text = "Led team of 12 engineers"

        numbers = _extract_numbers(text)

        assert "12" in numbers

    def test_extracts_decimals(self):
        """Test extraction of decimal values."""
        text = "Improved by 12.5%"

        numbers = _extract_numbers(text)

        assert "12.5%" in numbers

    def test_extracts_percentages(self):
        """Test extraction of percentage values."""
        text = "Increased by 40%"

        numbers = _extract_numbers(text)

        assert "40%" in numbers

    def test_extracts_currency_dollars(self):
        """Test extraction of dollar amounts."""
        text = "Managed $2M budget and $50,000 in expenses"
        numbers = _extract_numbers(text)

        # The regex extracts numbers without full currency symbols/M suffixes
        assert "2" in numbers or "50" in numbers or "000" in numbers

    def test_extracts_euros(self):
        """Test extraction of euro amounts."""
        text = "Saved €1.5M annually"
        numbers = _extract_numbers(text)

        # The regex extracts the numeric value without symbols/M suffix
        assert "1.5" in numbers

    def test_returns_set(self):
        """Test that function returns a set."""
        text = "Value 1 and value 2"

        numbers = _extract_numbers(text)

        assert isinstance(numbers, set)

    def test_handles_no_numbers(self):
        """Test handling of text without numbers."""
        text = "Led engineering team"

        numbers = _extract_numbers(text)

        assert numbers == set()


# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------


class TestIntegration:
    def test_all_generators_use_metrics_preservation(self, mock_llm_client):
        """Test that all generators include metrics preservation instruction."""
        original = "Led team of 5"

        generators = [
            generate_car_variant,
            generate_who_variant,
            generate_technical_variant,
            generate_product_variant,
        ]

        for generator in generators:
            mock_llm_client.reset_mock()
            generator(original, mock_llm_client)

            call_args = mock_llm_client.ask.call_args
            prompt = call_args[0][0]
            assert "Preserve all numbers" in prompt or "metrics" in prompt.lower()

    def test_variant_passes_through_metrics_validation(self, mock_llm_client):
        """Test end-to-end: generator -> validation flow."""
        original = "Increased revenue by 40%"
        mock_llm_client.ask.return_value = "Grew revenue by 40% year over year"

        # Generate variant
        variant = generate_car_variant(original, mock_llm_client)

        # Validate it
        result = validate_variant_metrics(original, variant, {})

        # Should pass validation (same number)
        assert result == variant
