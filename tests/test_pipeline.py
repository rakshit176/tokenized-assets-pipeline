"""Unit and integration tests for the pipeline.

Run:  python -m pytest tests/ -v
"""
from __future__ import annotations

import json
import os
import sys
import asyncio

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSchemaModels:
    """Test Pydantic schema models."""

    def test_cited_value_creation(self):
        from src.schema.models import CitedValue
        cv = CitedValue(value="Securitize", source_url="https://securitize.io", confidence=0.9)
        assert cv.is_filled()
        assert cv.value == "Securitize"
        assert cv.confidence == 0.9

    def test_cited_value_empty(self):
        from src.schema.models import CitedValue
        cv = CitedValue()
        assert not cv.is_filled()
        assert cv.value is None

    def test_company_data_empty_fill(self):
        from src.schema.models import CompanyData
        cd = CompanyData()
        assert cd.confidence_score() == 0.0

    def test_company_data_populated(self):
        from src.schema.models import CompanyData, CitedValue, Product
        cd = CompanyData()
        cd.profile.company_name = CitedValue(value="Chainlink", source_url="https://chain.link", confidence=0.9)
        cd.profile.founded_year = CitedValue(value=2017, confidence=0.8)
        cd.products.append(Product(
            product_name=CitedValue(value="Data Feeds", confidence=0.9),
            product_type=CitedValue(value="Oracle", confidence=0.8),
        ))
        assert cd.confidence_score() > 0
        assert cd.real_fill_score(0.4) > 0

    def test_serialization(self):
        from src.schema.models import CompanyData, CitedValue
        cd = CompanyData()
        cd.profile.company_name = CitedValue(value="Test", confidence=0.9)
        d = cd.model_dump()
        s = json.dumps(d, default=str)
        assert "Test" in s

    def test_missing_fields(self):
        from src.schema.models import CompanyData, CitedValue
        cd = CompanyData()
        cd.profile.company_name = CitedValue(value="Test", confidence=0.9)
        missing = cd.missing_fields(0.4)
        assert len(missing) > 0
        assert all("profile." in m for m in missing if m.startswith("profile.") and m != "profile.company_name")

    def test_apply_defaults(self):
        from src.schema.models import CompanyData
        cd = CompanyData()
        cd.apply_defaults("TestCo", "test.com")
        assert cd.profile.company_name.value == "TestCo"
        assert cd.profile.website.value is not None


class TestLLMExtractor:
    """Test LLM extractor batch specs and constructor."""

    def test_batch_specs_exist(self):
        from src.extractor.llm import ALL_BATCHES
        assert len(ALL_BATCHES) == 6
        names = [n for n, _ in ALL_BATCHES]
        assert "BatchA_Company" in names
        assert "BatchF_Partners_Licenses_Metrics_Deals" in names

    def test_batch_field_coverage(self):
        from src.extractor.llm import ALL_BATCHES
        total_fields = 0
        for _, spec in ALL_BATCHES:
            for table, fields in spec.items():
                total_fields += len(fields)
        assert total_fields >= 100, f"Expected >= 100 fields across batches, got {total_fields}"

    def test_extractor_init(self):
        from src.extractor.llm import LLMExtractor
        ext = LLMExtractor()
        assert ext.provider is not None
        assert hasattr(ext, 'call_logs')
        assert len(ext.call_logs) == 0


class TestProviders:
    """Test provider factory and config."""

    def test_factory_default(self):
        from src.providers.factory import get_provider
        p = get_provider("openai")
        assert p.config.model is not None

    def test_factory_invalid(self):
        from src.providers.factory import get_provider
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent")

    def test_provider_config(self):
        from src.providers.openai_provider import OpenAIProvider
        p = OpenAIProvider(model="gpt-4o-mini")
        assert p.config.model == "gpt-4o-mini"
        assert p.config.max_concurrent == 3

    def test_all_providers_instantiable(self):
        from src.providers.factory import PROVIDERS
        for name, cls in PROVIDERS.items():
            p = cls()
            assert p.config.api_key is not None or name == "zai"


class TestSearchClient:
    """Test search client structure."""

    def test_client_constructor(self):
        from src.search.client import SearXNGClient
        c = SearXNGClient(base_url="http://localhost:8888")
        assert hasattr(c, 'search')
        assert hasattr(c, 'deep_search')
        assert hasattr(c, 'gap_search')


class TestDatabaseSaver:
    """Test database saver helpers."""

    def test_val_empty(self):
        from src.schema.models import CitedValue
        from src.database.saver import _val
        assert _val(CitedValue()) is None

    def test_val_filled(self):
        from src.schema.models import CitedValue
        from src.database.saver import _val
        assert _val(CitedValue(value="hello", confidence=0.9)) == "hello"

    def test_val_rejects_na(self):
        from src.schema.models import CitedValue
        from src.database.saver import _val
        assert _val(CitedValue(value="N/A", confidence=0.5)) is None
        assert _val(CitedValue(value="unknown", confidence=0.5)) is None

    def test_val_rejects_confidence_float(self):
        from src.schema.models import CitedValue
        from src.database.saver import _val
        assert _val(CitedValue(value=0.85, confidence=0.9)) is None
        assert _val(CitedValue(value=99.5, confidence=0.9)) is None

    def test_int_helper(self):
        from src.schema.models import CitedValue
        from src.database.saver import _int
        assert _int(CitedValue(value=2023, confidence=0.9)) == 2023
        assert _int(CitedValue(value="2023", confidence=0.9)) == 2023
        assert _int(CitedValue(value="not_a_number", confidence=0.9)) is None
        assert _int(CitedValue()) is None

    def test_float_helper(self):
        from src.schema.models import CitedValue
        from src.database.saver import _float
        assert _float(CitedValue(value=1500000.0, confidence=0.9)) == 1500000.0
        assert _float(CitedValue(value="1.5M", confidence=0.9)) is None

    def test_bool_helper(self):
        from src.schema.models import CitedValue
        from src.database.saver import _bool
        assert _bool(CitedValue(value=True, confidence=0.9)) is True
        assert _bool(CitedValue(value="true", confidence=0.9)) is True
        assert _bool(CitedValue(value="yes", confidence=0.9)) is True
        assert _bool(CitedValue(value="false", confidence=0.9)) is False
        assert _bool(CitedValue(value="random", confidence=0.9)) is None

    def test_date_helper(self):
        from src.schema.models import CitedValue
        from src.database.saver import _date
        import datetime
        result = _date(CitedValue(value="2023-01-15", confidence=0.9))
        assert result is not None
        assert isinstance(result, (datetime.date, datetime.datetime))
        assert _date(CitedValue(value=2023, confidence=0.9)) is None

    def test_cost_calculation(self):
        from src.database.saver import DatabaseSaver
        cost = DatabaseSaver._calc_cost("gpt-4o-mini", 1000, 500)
        # $0.15/1M input + $0.60/1M output
        expected = (1000 / 1_000_000 * 0.15) + (500 / 1_000_000 * 0.60)
        assert abs(cost - expected) < 0.0001

    def test_cost_free_model(self):
        from src.database.saver import DatabaseSaver
        cost = DatabaseSaver._calc_cost("glm-4-plus-0111", 50000, 10000)
        assert cost == 0.0


class TestOrchestrator:
    """Test orchestrator output structuring."""

    def test_structure_output(self):
        from src.orchestrator import PipelineRunner
        mock = {
            "companies": {
                "company_name": {"value": "TestCo", "source_url": "https://test.com", "confidence": 0.9},
                "founded_year": {"value": 2020, "source_url": "https://test.com", "confidence": 0.8},
            },
            "products": {
                "rows": [
                    {
                        "product_name": {"value": "Product A", "confidence": 0.9},
                        "product_type": {"value": "Platform", "confidence": 0.8},
                    }
                ]
            },
        }
        data = PipelineRunner._structure_output(mock, "TestCo", "test.com")
        assert data.profile.company_name.value == "TestCo"
        assert data.profile.founded_year.value == 2020
        assert len(data.products) == 1
        assert data.products[0].product_name.value == "Product A"
