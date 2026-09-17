from desfibrilator.llm_geocode import (
    ProposalBatch,
    ReviewBatch,
    _decode_llm_json,
)


def test_decode_gepeto_final_result_wrapper():
    payload = _decode_llm_json('final_result[ARGS]{"records": []}')

    assert payload == {"records": []}
    assert ProposalBatch.model_validate(payload).records == []


def test_decode_llm_json_ignores_trailing_wrapper_text():
    assert _decode_llm_json('{"records": []} trailing text') == {"records": []}


def test_review_output_model_accepts_rejection():
    result = ReviewBatch.model_validate(
        {
            "records": [
                {
                    "address_key": "key",
                    "decision": "reject",
                    "candidate_ref": None,
                    "precision": "reject",
                    "confidence": 0.9,
                    "rationale": "No defensible candidate.",
                }
            ]
        }
    )

    assert result.records[0].decision == "reject"
