import pytest

from semantic_layer.nl_to_sparql import (
    MAX_LIMIT,
    PREFIXES,
    build_prompt,
    from_template,
    guard,
    translate,
)

PROPS = ["temperature", "humidity", "co", "smoke", "distance", "count", "occupancy"]
SUBS = ["temp_humidity", "lighting", "gas", "agv", "counting"]


def q(body: str) -> str:
    return PREFIXES + "\n\n" + body


class TestGuard:
    def test_valid_select_passes(self):
        ok, v = guard(
            q("SELECT ?s WHERE { ?s a sosa:Observation } LIMIT 10"), PROPS, SUBS
        )
        assert ok and v == []

    def test_ask_passes(self):
        ok, _ = guard(q("ASK { ?s a sosa:Observation }"), PROPS, SUBS)
        assert ok

    def test_insert_is_blocked(self):
        ok, v = guard(q("INSERT DATA { <a> <b> <c> }"), PROPS, SUBS)
        assert not ok
        assert any("INSERT" in x for x in v)

    def test_delete_is_blocked(self):
        ok, v = guard(q("DELETE WHERE { ?s ?p ?o }"), PROPS, SUBS)
        assert not ok

    def test_drop_is_blocked(self):
        ok, _ = guard(q("DROP GRAPH <urn:x>"), PROPS, SUBS)
        assert not ok

    def test_service_federation_is_blocked(self):
        ok, v = guard(
            q("SELECT ?s WHERE { SERVICE <http://evil> { ?s ?p ?o } } LIMIT 5"),
            PROPS,
            SUBS,
        )
        assert not ok
        assert any("SERVICE" in x for x in v)

    def test_construct_is_blocked(self):
        ok, _ = guard(q("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"), PROPS, SUBS)
        assert not ok

    def test_missing_limit_is_blocked(self):
        ok, v = guard(q("SELECT ?s WHERE { ?s a sosa:Observation }"), PROPS, SUBS)
        assert not ok
        assert any("LIMIT" in x for x in v)

    def test_oversized_limit_is_blocked(self):
        ok, v = guard(
            q(f"SELECT ?s WHERE {{ ?s ?p ?o }} LIMIT {MAX_LIMIT + 1}"), PROPS, SUBS
        )
        assert not ok

    def test_unknown_ontology_property_is_blocked(self):
        ok, v = guard(
            q(
                "SELECT ?v WHERE { ?o sosa:observedProperty sf:measuresRadiation ;"
                " sosa:hasSimpleResult ?v } LIMIT 10"
            ),
            PROPS,
            SUBS,
        )
        assert not ok
        assert any("radiation" in x for x in v)

    def test_known_ontology_property_is_allowed(self):
        ok, v = guard(
            q(
                "SELECT ?v WHERE { ?o sosa:observedProperty sf:measuresTemperature ;"
                " sosa:hasSimpleResult ?v } LIMIT 10"
            ),
            PROPS,
            SUBS,
        )
        assert ok, v

    def test_empty_query_is_blocked(self):
        ok, _ = guard("", PROPS, SUBS)
        assert not ok

    def test_vocabulary_grows_with_the_ontology(self):
        bad = q(
            "SELECT ?v WHERE { ?o sosa:observedProperty sf:measuresVibration ;"
            " sosa:hasSimpleResult ?v } LIMIT 10"
        )
        assert not guard(bad, PROPS, SUBS)[0]
        assert guard(bad, PROPS + ["vibration"], SUBS)[0]


class TestTemplates:
    def test_alert_ranking_question_matches(self):
        result = from_template("哪个子系统告警最多？")
        assert result is not None
        assert "GROUP BY" in result[0]

    def test_recent_temperature_matches(self):
        result = from_template("最近的温度是多少")
        assert result is not None
        assert "measuresTemperature" in result[0]

    def test_sensor_count_matches(self):
        result = from_template("现在有多少个传感器")
        assert result is not None
        assert "COUNT" in result[0]

    def test_co_threshold_matches(self):
        result = from_template("一氧化碳有没有超标")
        assert result is not None
        assert "FILTER" in result[0]

    def test_unrelated_question_does_not_match(self):
        assert from_template("今天天气怎么样") is None

    def test_every_template_passes_the_guard(self):
        for question in (
            "哪个子系统告警最多",
            "最近的温度",
            "有多少个传感器",
            "一氧化碳超标了吗",
        ):
            matched = from_template(question)
            assert matched is not None, question
            sparql, _ = matched
            ok, violations = guard(sparql, PROPS, SUBS)
            assert ok, (question, violations)


class TestPrompt:
    def test_prompt_lists_the_vocabulary(self):
        prompt = build_prompt("最近的温度", PROPS, SUBS)
        assert "temperature" in prompt
        assert "temp_humidity" in prompt

    def test_prompt_states_the_restrictions(self):
        prompt = build_prompt("x", PROPS, SUBS)
        assert "INSERT" in prompt
        assert str(MAX_LIMIT) in prompt


class TestTranslate:
    @pytest.mark.asyncio
    async def test_template_path_needs_no_llm(self):
        result = await translate("哪个子系统告警最多", PROPS, SUBS, allow_llm=False)
        assert result.accepted
        assert result.source == "template"

    @pytest.mark.asyncio
    async def test_no_template_and_no_llm_is_refused(self):
        result = await translate("帮我写一首诗", PROPS, SUBS, allow_llm=False)
        assert not result.accepted
        assert result.sparql == ""

    @pytest.mark.asyncio
    async def test_llm_output_is_guarded(self, monkeypatch):
        import semantic_layer.nl_to_sparql as mod

        monkeypatch.setattr(mod, "LLM_API_KEY", "test")

        async def malicious(prompt, client=None):
            return "```sparql\nDELETE WHERE { ?s ?p ?o }\n```"

        monkeypatch.setattr(mod, "call_llm", malicious)
        result = await translate("删掉所有数据", PROPS, SUBS)
        assert not result.accepted
        assert any("DELETE" in v for v in result.violations)

    @pytest.mark.asyncio
    async def test_llm_hallucinated_sensor_is_rejected(self, monkeypatch):
        import semantic_layer.nl_to_sparql as mod

        monkeypatch.setattr(mod, "LLM_API_KEY", "test")

        async def hallucinate(prompt, client=None):
            return (
                "SELECT ?v WHERE { ?o sosa:observedProperty sf:measuresRadiation ;"
                " sosa:hasSimpleResult ?v } LIMIT 10"
            )

        monkeypatch.setattr(mod, "call_llm", hallucinate)
        result = await translate("辐射水平如何", PROPS, SUBS)
        assert not result.accepted

    @pytest.mark.asyncio
    async def test_good_llm_output_is_accepted(self, monkeypatch):
        import semantic_layer.nl_to_sparql as mod

        monkeypatch.setattr(mod, "LLM_API_KEY", "test")

        async def good(prompt, client=None):
            return (
                "SELECT ?v WHERE { ?o sosa:observedProperty sf:measuresHumidity ;"
                " sosa:hasSimpleResult ?v } LIMIT 10"
            )

        monkeypatch.setattr(mod, "call_llm", good)
        result = await translate("湿度多少", PROPS, SUBS)
        assert result.accepted
        assert result.source == "llm"
        assert "humidity" in result.used_properties

    @pytest.mark.asyncio
    async def test_llm_failure_is_reported_not_raised(self, monkeypatch):
        import semantic_layer.nl_to_sparql as mod

        monkeypatch.setattr(mod, "LLM_API_KEY", "test")

        async def boom(prompt, client=None):
            raise RuntimeError("network down")

        monkeypatch.setattr(mod, "call_llm", boom)
        result = await translate("湿度多少", PROPS, SUBS)
        assert not result.accepted
        assert any("失败" in v for v in result.violations)
