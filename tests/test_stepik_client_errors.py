from stepik_autopilot.infra.stepik.client import response_error_message


def test_oauth_error_exposes_safe_http_diagnostics() -> None:
    message = response_error_message(
        "Stepik OAuth token request failed",
        401,
        {"error": "invalid_client", "error_description": "The supplied secret must not be exposed"},
    )

    assert message == "Stepik OAuth token request failed (HTTP 401; Unauthorized; error=invalid_client)"
    assert "secret" not in message


def test_error_diagnostics_omit_unstructured_response_body() -> None:
    message = response_error_message("Stepik API request failed", 502, "upstream response")

    assert message == "Stepik API request failed (HTTP 502; Bad Gateway)"
