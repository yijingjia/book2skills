import json

import pytest

from app.pipeline.ku_same_as_judge import extract_judgment_items, normalize_judge_response


def test_extract_judgment_items_accepts_standard_judgments_key():
    raw = {"judgments": [{"from_ku_id": "ku-0000", "to_ku_id": "ku-0001"}]}
    assert extract_judgment_items(raw) == raw["judgments"]


def test_extract_judgment_items_accepts_qwen_nested_data_key():
    raw = {"data": [{"from_ku_id": "ku-0000", "to_ku_id": "ku-0001"}]}
    assert extract_judgment_items(raw) == raw["data"]


def test_extract_judgment_items_accepts_top_level_list():
    raw = [{"from_ku_id": "ku-0000", "to_ku_id": "ku-0001"}]
    assert extract_judgment_items(raw) == raw


def test_normalize_judge_response_filters_invalid_and_coerces_decisions():
    candidates = {
        "pairs": [
            {
                "candidate_id": "cand-ku-0000-ku-0001",
                "from_ku_id": "ku-0000",
                "to_ku_id": "ku-0001",
                "similarity": 0.61,
            }
        ]
    }
    raw = {
        "data": [
            {
                "candidate_id": "cand-ku-0000-ku-0001",
                "from_ku_id": "ku-0000",
                "to_ku_id": "ku-0001",
                "decision": "same_as",
                "confidence": 0.91,
                "evidence": "都描述用类比解释复杂概念。",
            },
            {
                "candidate_id": "missing",
                "from_ku_id": "ku-9999",
                "to_ku_id": "ku-0001",
                "decision": "same_as",
                "confidence": 0.91,
                "evidence": "invalid",
            },
        ]
    }

    result = normalize_judge_response(raw, candidates, decided_by="backend_llm")

    assert result == {
        "judgments": [
            {
                "candidate_id": "cand-ku-0000-ku-0001",
                "from_ku_id": "ku-0000",
                "to_ku_id": "ku-0001",
                "decision": "same_as",
                "confidence": 0.91,
                "evidence": "都描述用类比解释复杂概念。",
                "decided_by": "backend_llm",
            }
        ]
    }


@pytest.mark.asyncio
async def test_ku_same_as_judge_batches_calls_and_merges_results():
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.pipeline.ku_same_as_judge import KUSameAsJudge

    source_kus = {
        "knowledge_units": [
            {"ku_id": "ku-0001", "method": "M1"},
            {"ku_id": "ku-0002", "method": "M2"},
            {"ku_id": "ku-0003", "method": "M3"},
        ]
    }
    candidates = {
        "pairs": [
            {"candidate_id": "c1", "from_ku_id": "ku-0001", "to_ku_id": "ku-0002", "similarity": 0.8},
            {"candidate_id": "c2", "from_ku_id": "ku-0002", "to_ku_id": "ku-0003", "similarity": 0.7},
            {"candidate_id": "c3", "from_ku_id": "ku-0001", "to_ku_id": "ku-0003", "similarity": 0.6},
        ]
    }

    with patch("app.pipeline.ku_same_as_judge.get_llm_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Batch size is 2, so it should make 2 batches: [c1, c2] and [c3]
        judge = KUSameAsJudge(batch_size=2)

        # Mock responses for 2 batches
        response_batch_1 = MagicMock()
        response_batch_1.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "judgments": [
                            {"candidate_id": "c1", "decision": "same_as", "confidence": 0.9, "evidence": "E1"},
                            {"candidate_id": "c2", "decision": "not_same", "confidence": 0.1, "evidence": "E2"},
                        ]
                    })
                )
            )
        ]

        response_batch_2 = MagicMock()
        response_batch_2.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "judgments": [
                            {"candidate_id": "c3", "decision": "alias_of", "confidence": 0.85, "evidence": "E3"}
                        ]
                    })
                )
            )
        ]

        mock_client.chat.completions.create = AsyncMock(
            side_effect=[response_batch_1, response_batch_2]
        )

        result = await judge.judge(source_kus=source_kus, candidates=candidates)

        assert mock_client.chat.completions.create.call_count == 2
        assert len(result["judgments"]) == 3

        # Verify the structure and values
        j1 = next(j for j in result["judgments"] if j["candidate_id"] == "c1")
        assert j1["decision"] == "same_as"
        assert j1["confidence"] == 0.9
        assert j1["evidence"] == "E1"
        assert j1["decided_by"] == "backend_llm"

        j2 = next(j for j in result["judgments"] if j["candidate_id"] == "c2")
        assert j2["decision"] == "not_same"
        assert j2["confidence"] == 0.1

        j3 = next(j for j in result["judgments"] if j["candidate_id"] == "c3")
        assert j3["decision"] == "alias_of"
        assert j3["confidence"] == 0.85


@pytest.mark.asyncio
async def test_signatures_support_positional_arguments():
    # 1. normalize_judge_response should support positional decided_by
    candidates = {"pairs": []}
    res = normalize_judge_response({}, candidates, "some_decider")
    assert res == {"judgments": []}

    # 2. KUSameAsJudge.__init__ should support positional batch_size
    from app.pipeline.ku_same_as_judge import KUSameAsJudge
    judge = KUSameAsJudge(25)
    assert judge.batch_size == 25

    # 3. KUSameAsJudge.judge should support positional source_kus and candidates
    # (Just verifying it can be invoked this way; we can mock or pass minimal inputs)
    from unittest.mock import AsyncMock, patch
    with patch("app.pipeline.ku_same_as_judge.get_llm_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        judge = KUSameAsJudge(25)
        # We should be able to call judge.judge(source_kus, candidates) positionally
        # We will mock _judge_batch to avoid deep client calls
        judge._judge_batch = AsyncMock(return_value={"judgments": []})

        await judge.judge({"knowledge_units": []}, {"pairs": []})


def test_extract_judgment_items_prioritizes_data_over_other_keys():
    raw = {
        "other_key": ["not", "dictionaries"],
        "data": [{"candidate_id": "c1", "decision": "same_as"}],
    }
    # If other_key is processed first by iterating values, it would return [],
    # but since data is checked explicitly first, it should return the item in data.
    res = extract_judgment_items(raw)
    assert len(res) == 1
    assert res[0]["candidate_id"] == "c1"


def test_extract_judgment_items_accumulates_all_lists():
    raw = {
        "list1": [{"candidate_id": "c1", "decision": "same_as"}],
        "list2": [{"candidate_id": "c2", "decision": "not_same"}],
        "non_list": "val",
    }
    res = extract_judgment_items(raw)
    assert len(res) == 2
    assert {item["candidate_id"] for item in res} == {"c1", "c2"}


@pytest.mark.asyncio
async def test_ku_same_as_judge_aclose():
    from unittest.mock import AsyncMock, patch

    from app.pipeline.ku_same_as_judge import KUSameAsJudge

    with patch("app.pipeline.ku_same_as_judge.get_llm_client"), \
         patch("app.pipeline.ku_same_as_judge.close_llm_client", new_callable=AsyncMock) as mock_close:

        judge = KUSameAsJudge()
        client = judge.client
        await judge.aclose()
        mock_close.assert_called_once_with(client)
        assert judge.client is None


def test_batch_prompt_skips_missing_ku_ids(caplog):
    import logging

    from app.pipeline.ku_same_as_judge import _batch_prompt

    source_kus = {
        "knowledge_units": [
            {"ku_id": "ku-0001", "method": "M1"},
        ]
    }
    pairs = [
        {"candidate_id": "c1", "from_ku_id": "ku-0001", "to_ku_id": "ku-0002"},
    ]

    with caplog.at_level(logging.WARNING):
        res_str = _batch_prompt(source_kus, pairs)

    assert "Skipping pair c1: KU id not found in source_kus." in caplog.text
    res = json.loads(res_str)
    assert res == {"pairs": []}


@pytest.mark.asyncio
async def test_ku_same_as_judge_async_context_manager():
    from unittest.mock import AsyncMock, patch

    from app.pipeline.ku_same_as_judge import KUSameAsJudge

    with patch("app.pipeline.ku_same_as_judge.get_llm_client") as mock_get_client, \
         patch("app.pipeline.ku_same_as_judge.close_llm_client", new_callable=AsyncMock) as mock_close:

        async with KUSameAsJudge() as judge:
            assert isinstance(judge, KUSameAsJudge)
            client = judge.client
            assert client == mock_get_client.return_value
            mock_close.assert_not_called()

        mock_close.assert_called_once_with(client)
        assert judge.client is None

