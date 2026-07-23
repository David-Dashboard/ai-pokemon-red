"""$0, CI-safe, mock-only tests for tools/gate0_appserver_client.py. No real `codex` process is
spawned anywhere in this file (Gate0AppServerClient is driven via an injected `send=` recorder
plus handle_message()/handle_line(), an in-process fake JSON-RPC peer) -- runs on Linux CI with no
codex install and no model turn.

Response shapes are checked against the actual `codex app-server generate-json-schema` dump
(codex-cli 0.144.3), committed under tests/fixtures/gate0_appserver/. `jsonschema` is not a
project dependency (checked pyproject.toml first), so schema checks below are structural
(required-keys / allowed-keys / enum-membership) rather than a full validator -- per the task's
own fallback instruction.
"""
import json
import time
from pathlib import Path

import pytest

from tools.gate0_appserver_client import (
    DEFAULT_CODEX_PATH,
    FALLBACK_ANSWER,
    INITIALIZE_CAPABILITIES,
    Gate0AppServerClient,
    _HANDLERS,
    build_command_execution_response,
    build_elicitation_response,
    build_file_change_response,
    build_permissions_response,
    build_tool_user_input_response,
    build_turn_start_request,
    encode_jsonrpc_line,
    pick_approve_label,
    resolve_codex_path,
)

FIXTURES = Path(__file__).parent / "fixtures" / "gate0_appserver"


def _load_schema(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _string_enum_values(definition):
    """Every plain string-enum value reachable from a schema definition, whether it's a bare
    `{"type": "string", "enum": [...]}` or a `oneOf`/`anyOf` container mixing string and object
    variants (object variants, e.g. acceptWithExecpolicyAmendment, are skipped -- not relevant
    here since this client only ever emits the plain-string decisions)."""
    values = []
    if definition.get("type") == "string" and "enum" in definition:
        values.extend(definition["enum"])
    for branch in definition.get("oneOf", []) + definition.get("anyOf", []):
        if branch.get("type") == "string" and "enum" in branch:
            values.extend(branch["enum"])
    return values


def _assert_required_keys_present(instance, schema):
    for key in schema.get("required", []):
        assert key in instance, f"missing required key {key!r} per schema {schema['title']}"


def _assert_keys_allowed(instance, schema):
    allowed = set(schema.get("properties", {}))
    extra = set(instance) - allowed
    assert not extra, f"unexpected keys {extra} not declared in {schema['title']} properties {allowed}"


def _server_request_methods(schema):
    """Every real request-method string declared as a `ServerRequest.json` `oneOf` branch."""
    return {branch["properties"]["method"]["enum"][0] for branch in schema["oneOf"]}


# ---------------------------------------------------------------------------
# Framing: newline-delimited JSON (JSONL), no "jsonrpc" field on the wire.
# ---------------------------------------------------------------------------

def test_encode_jsonrpc_line_is_newline_delimited_with_no_jsonrpc_field():
    line = encode_jsonrpc_line({"id": 1, "method": "initialize",
                                 "params": {"clientInfo": {"name": "x", "version": "1"}}})
    assert line.endswith(b"\n")
    assert line.count(b"\n") == 1
    decoded = json.loads(line.decode("utf-8"))
    assert "jsonrpc" not in decoded
    assert decoded["method"] == "initialize"


def test_handle_line_parses_a_raw_jsonl_wire_line():
    sent = []
    client = Gate0AppServerClient(send=sent.append)
    line = json.dumps({
        "id": 5, "method": "mcpServer/elicitation/request",
        "params": {"serverName": "docker_mcp", "threadId": "thr1", "mode": "form",
                   "message": "Confirm?", "requestedSchema": {"type": "object", "properties": {}}},
    })
    client.handle_line(line)
    assert sent == [{"id": 5, "result": {"action": "accept"}}]


# ---------------------------------------------------------------------------
# codex path resolution
# ---------------------------------------------------------------------------

def test_resolve_codex_path_defaults_and_honors_env_override(monkeypatch):
    monkeypatch.delenv("GATE0_CODEX_PATH", raising=False)
    assert resolve_codex_path() == DEFAULT_CODEX_PATH
    monkeypatch.setenv("GATE0_CODEX_PATH", "/custom/path/codex")
    assert resolve_codex_path() == "/custom/path/codex"


# ---------------------------------------------------------------------------
# Request-side grounding: de-circularize against the committed *Params.json ground truth (not just
# the response side). A wrong/renamed method or field name must fail HERE, at $0, not silently
# no-op or deny-all at the paid turn.
# ---------------------------------------------------------------------------

def test_all_handler_methods_are_real_server_request_branches():
    schema = _load_schema("ServerRequest.json")
    real_methods = _server_request_methods(schema)
    for method in _HANDLERS:
        assert method in real_methods, (
            f"_HANDLERS method {method!r} is not a real ServerRequest.json branch "
            f"(real methods: {sorted(real_methods)})")


def test_permissions_field_name_matches_ground_truth_params_schema():
    # build_permissions_response reads params["permissions"] -- confirm that's the REAL field name
    # (not hand-matched to the mock) and that it's required (so an absent key is a protocol
    # violation, justifying the raise in build_permissions_response, not a normal "empty" case).
    schema = _load_schema("PermissionsRequestApprovalParams.json")
    assert "permissions" in schema["properties"]
    assert "permissions" in schema["required"]


def test_tool_user_input_questions_and_id_field_names_match_ground_truth_params_schema():
    # build_tool_user_input_response reads params["questions"] and each question["id"] -- confirm
    # both are the REAL field names, that "questions" is required on ToolRequestUserInputParams
    # (justifying the raise in build_tool_user_input_response, not a silent {"answers": {}}), and
    # that "id" is required on ToolRequestUserInputQuestion.
    schema = _load_schema("ToolRequestUserInputParams.json")
    assert "questions" in schema["properties"]
    assert "questions" in schema["required"]
    question_schema = schema["definitions"]["ToolRequestUserInputQuestion"]
    assert "id" in question_schema["properties"]
    assert "id" in question_schema["required"]


def test_pick_approve_label_options_and_label_field_names_match_ground_truth_schema():
    # pick_approve_label reads question["options"] and option["label"] -- confirm both are the REAL
    # field names on ToolRequestUserInputQuestion/ToolRequestUserInputOption (not just hand-matched
    # to the mock), so a future codex rename of either fails HERE instead of silently degrading
    # every question to FALLBACK_ANSWER via pick_approve_label's own "no options offered" branch.
    schema = _load_schema("ToolRequestUserInputParams.json")
    question_schema = schema["definitions"]["ToolRequestUserInputQuestion"]
    assert "options" in question_schema["properties"]
    option_schema = schema["definitions"]["ToolRequestUserInputOption"]
    assert "label" in option_schema["properties"]


def test_permissions_response_raises_on_missing_permissions_field_instead_of_deny_all():
    # A missing `permissions` key is a protocol violation (the field is required per the schema
    # test above) -- must raise, not silently echo {} (an empty GrantedPermissionProfile = deny-all,
    # masking the exact bug this client exists to fix).
    with pytest.raises(ValueError):
        build_permissions_response({})


def test_tool_user_input_response_raises_on_question_missing_id_instead_of_bare_keyerror():
    with pytest.raises(ValueError):
        build_tool_user_input_response({"questions": [{"header": "h", "question": "q"}]})


def test_tool_user_input_response_raises_on_missing_questions_field_instead_of_empty_answers():
    # A missing `questions` key is a protocol violation (required per the schema test above) --
    # must raise, not silently return {"answers": {}} (indistinguishable from "zero questions were
    # asked", which would mask a codex schema rename of the field, asymmetric with how
    # build_permissions_response already treats a missing `permissions` key).
    with pytest.raises(ValueError):
        build_tool_user_input_response({})


def test_initialize_declares_experimental_and_form_elicitation_capabilities():
    # Blocker: item/tool/requestUserInput is EXPERIMENTAL (ServerRequest.json) and gated by
    # InitializeCapabilities.experimentalApi (default false); openai/form elicitations are gated by
    # mcpServerOpenaiFormElicitation. Confirm both are the REAL field names (v1/InitializeParams.json)
    # and that initialize() actually sends them set true.
    schema = _load_schema("InitializeParams.json")
    capabilities_schema = schema["definitions"]["InitializeCapabilities"]
    assert "experimentalApi" in capabilities_schema["properties"]
    assert "mcpServerOpenaiFormElicitation" in capabilities_schema["properties"]
    assert INITIALIZE_CAPABILITIES == {"experimentalApi": True, "mcpServerOpenaiFormElicitation": True}

    sent = []

    def fake_send(message):
        sent.append(message)
        if message.get("method") == "initialize":
            client.handle_message({"id": message["id"], "result": {
                "codexHome": "/home/.codex", "platformFamily": "windows",
                "platformOs": "windows", "userAgent": "codex-cli/0.144.3",
            }})

    client = Gate0AppServerClient(send=fake_send)
    client.initialize()

    initialize_message = next(m for m in sent if m.get("method") == "initialize")
    params = initialize_message["params"]
    _assert_required_keys_present(params, schema)
    _assert_keys_allowed(params, schema)
    capabilities = params["capabilities"]
    _assert_keys_allowed(capabilities, capabilities_schema)
    assert capabilities["experimentalApi"] is True
    assert capabilities["mcpServerOpenaiFormElicitation"] is True


# ---------------------------------------------------------------------------
# Byte-exact response shapes vs the generated schemas (the 4 ServerRequest types).
# ---------------------------------------------------------------------------

def test_elicitation_response_matches_schema_openai_codex_18268():
    # openai/codex#18268: an elicitation response with wrong/renamed fields silently deserializes
    # to "Denied" instead of failing loudly -- assert the EXACT field name and value.
    schema = _load_schema("McpServerElicitationRequestResponse.json")
    response = build_elicitation_response()
    assert response == {"action": "accept"}
    _assert_required_keys_present(response, schema)
    _assert_keys_allowed(response, schema)
    allowed = _string_enum_values(schema["definitions"]["McpServerElicitationAction"])
    assert allowed == ["accept", "decline", "cancel"]
    assert response["action"] in allowed


def test_tool_user_input_response_shape_is_byte_exact_hapi_287():
    # tiann/hapi#287: no/renamed `answers` field -> codex cancels ("missing field `answers`").
    schema = _load_schema("ToolRequestUserInputResponse.json")
    params = {
        "itemId": "item1", "threadId": "thr1", "turnId": "turn1",
        "questions": [{
            "id": "q1", "header": "Approve app tool call?", "question": "Run docker exec?",
            "options": [{"label": "Approve", "description": "Allow the call"},
                        {"label": "Deny", "description": "Refuse the call"}],
        }],
    }
    response = build_tool_user_input_response(params)
    assert response == {"answers": {"q1": {"answers": ["Approve"]}}}
    _assert_required_keys_present(response, schema)
    _assert_keys_allowed(response, schema)
    answer_schema = schema["definitions"]["ToolRequestUserInputAnswer"]
    for answer in response["answers"].values():
        _assert_required_keys_present(answer, answer_schema)
        assert isinstance(answer["answers"], list)
        assert all(isinstance(item, str) for item in answer["answers"])


def test_permissions_response_grants_exactly_the_requested_profile_scoped_session():
    schema = _load_schema("PermissionsRequestApprovalResponse.json")
    requested = {"fileSystem": {"write": ["/workspace"]}, "network": {"enabled": True}}
    response = build_permissions_response({"permissions": requested}, scope="session")
    assert response == {"permissions": requested, "scope": "session"}
    _assert_required_keys_present(response, schema)
    _assert_keys_allowed(response, schema)
    allowed_scopes = _string_enum_values(schema["definitions"]["PermissionGrantScope"])
    assert allowed_scopes == ["turn", "session"]
    assert response["scope"] in allowed_scopes


def test_permissions_scope_is_configurable_and_validated():
    assert build_permissions_response({"permissions": {}})["scope"] == "session"  # default
    assert build_permissions_response({"permissions": {}}, scope="turn")["scope"] == "turn"
    with pytest.raises(ValueError):
        build_permissions_response({"permissions": {}}, scope="bogus")


def test_command_execution_and_file_change_responses_are_the_accept_decision():
    cases = [
        (build_command_execution_response, "CommandExecutionRequestApprovalResponse.json",
         "CommandExecutionApprovalDecision"),
        (build_file_change_response, "FileChangeRequestApprovalResponse.json",
         "FileChangeApprovalDecision"),
    ]
    for build_fn, schema_file, decision_definition in cases:
        schema = _load_schema(schema_file)
        response = build_fn()
        assert response == {"decision": "accept"}
        _assert_required_keys_present(response, schema)
        _assert_keys_allowed(response, schema)
        allowed = _string_enum_values(schema["definitions"][decision_definition])
        assert "accept" in allowed
        assert response["decision"] in allowed


# ---------------------------------------------------------------------------
# pick_approve_label: option selection for item/tool/requestUserInput.
# ---------------------------------------------------------------------------

def test_pick_approve_label_matches_case_insensitively():
    question = {"id": "q", "header": "h", "question": "q", "options": [
        {"label": "No thanks", "description": ""}, {"label": "APPROVE", "description": ""}]}
    assert pick_approve_label(question) == "APPROVE"


def test_pick_approve_label_falls_back_to_first_option_without_a_keyword_match():
    question = {"id": "q", "header": "h", "question": "q",
                "options": [{"label": "Foo", "description": ""}, {"label": "Bar", "description": ""}]}
    assert pick_approve_label(question) == "Foo"


def test_pick_approve_label_falls_back_to_fixed_answer_when_no_options_offered():
    question = {"id": "q", "header": "h", "question": "q"}
    assert pick_approve_label(question) == FALLBACK_ANSWER


# ---------------------------------------------------------------------------
# PR #27256: autoResolutionMs is contract-plumbing only -- no reliance on any auto-accept timer.
# ---------------------------------------------------------------------------

def test_tool_user_input_never_relies_on_autoResolutionMs_timer():
    params_with_timer = {
        "itemId": "item1", "threadId": "thr1", "turnId": "turn1", "autoResolutionMs": 999999999,
        "questions": [{"id": "q1", "header": "h", "question": "q",
                       "options": [{"label": "Approve", "description": ""}]}],
    }
    params_without_timer = {k: v for k, v in params_with_timer.items() if k != "autoResolutionMs"}
    started = time.monotonic()
    with_timer = build_tool_user_input_response(params_with_timer)
    without_timer = build_tool_user_input_response(params_without_timer)
    elapsed = time.monotonic() - started
    expected = {"answers": {"q1": {"answers": ["Approve"]}}}
    assert with_timer == without_timer == expected
    assert elapsed < 1.0  # no sleep/wait tied to autoResolutionMs -- answers immediately either way


# ---------------------------------------------------------------------------
# codex-plugin-cc #258: responses must route to the ORIGINATING request, not a decoy.
# ---------------------------------------------------------------------------

def test_tool_user_input_routes_to_the_originating_request_not_a_decoy():
    sent = []
    client = Gate0AppServerClient(send=sent.append)

    def _request(request_id, thread, turn, item, question_id):
        return {
            "id": request_id, "method": "item/tool/requestUserInput",
            "params": {
                "threadId": thread, "turnId": turn, "itemId": item,
                "questions": [{"id": question_id, "header": "Approve?", "question": "Run it?",
                               "options": [{"label": "Approve", "description": "yes"},
                                           {"label": "Deny", "description": "no"}]}],
            },
        }

    decoy = _request(99, "thr_decoy", "turn_decoy", "item_decoy", "q_decoy")
    real = _request(7, "thr_real", "turn_real", "item_real", "q_real")
    client.handle_message(decoy)
    client.handle_message(real)

    responses = {message["id"]: message for message in sent}
    assert set(responses) == {7, 99}
    assert responses[7]["result"] == {"answers": {"q_real": {"answers": ["Approve"]}}}
    assert responses[99]["result"] == {"answers": {"q_decoy": {"answers": ["Approve"]}}}
    assert "q_decoy" not in responses[7]["result"]["answers"]
    assert "q_real" not in responses[99]["result"]["answers"]


def test_elicitation_routes_to_the_originating_request_id_not_a_decoy():
    sent = []
    client = Gate0AppServerClient(send=sent.append)
    decoy = {"id": "decoy-id", "method": "mcpServer/elicitation/request",
             "params": {"serverName": "docker_mcp", "threadId": "thr_decoy", "mode": "form",
                        "message": "?", "requestedSchema": {"type": "object", "properties": {}}}}
    real = {"id": "real-id", "method": "mcpServer/elicitation/request",
            "params": {"serverName": "docker_mcp", "threadId": "thr_real", "mode": "form",
                       "message": "?", "requestedSchema": {"type": "object", "properties": {}}}}
    client.handle_message(decoy)
    client.handle_message(real)
    responses = {message["id"]: message for message in sent}
    assert responses["decoy-id"]["result"] == {"action": "accept"}
    assert responses["real-id"]["result"] == {"action": "accept"}
    assert set(responses) == {"decoy-id", "real-id"}

    # Response schemas carry no threadId, so the only way to prove the decoy/real threadIds were
    # actually kept apart (not just asserted-and-ignored) is the audit trail, which logs threadId
    # per originating request id -- assert it maps each id back to its OWN threadId, not the other's.
    server_request_entries = {entry["request_id"]: entry["thread_id"]
                               for entry in client.audit if entry["event"] == "server_request"}
    assert server_request_entries == {"decoy-id": "thr_decoy", "real-id": "thr_real"}


# ---------------------------------------------------------------------------
# Handler robustness for item/commandExecution/requestApproval and item/fileChange/requestApproval.
# ---------------------------------------------------------------------------

def test_command_execution_and_file_change_requests_are_answered_and_routed():
    sent = []
    client = Gate0AppServerClient(send=sent.append)
    client.handle_message({
        "id": 1, "method": "item/commandExecution/requestApproval",
        "params": {"itemId": "item1", "threadId": "thr1", "turnId": "turn1", "startedAtMs": 0,
                   "command": "docker exec world_mcp python probe.py"},
    })
    client.handle_message({
        "id": 2, "method": "item/fileChange/requestApproval",
        "params": {"itemId": "item2", "threadId": "thr1", "turnId": "turn1", "startedAtMs": 0},
    })
    responses = {message["id"]: message["result"] for message in sent}
    assert responses[1] == {"decision": "accept"}
    assert responses[2] == {"decision": "accept"}


def test_unhandled_server_request_method_is_left_unresolved_but_logged_not_silent():
    # A method-name mismatch/drift (wrong/renamed method) must be visible in the audit trail, not a
    # silent no-op indistinguishable from "nothing happened" at the paid turn.
    sent = []
    client = Gate0AppServerClient(send=sent.append)
    client.handle_message({"id": 1, "method": "attestation/generate", "params": {}})
    assert sent == []
    assert client.audit == [{"event": "unhandled_server_request", "method": "attestation/generate",
                              "request_id": 1}]


# ---------------------------------------------------------------------------
# Structured logging: method + ids + action ONLY, never params/result/secret values.
# ---------------------------------------------------------------------------

def test_audit_log_records_only_method_ids_and_action_never_params_or_result():
    sent = []
    client = Gate0AppServerClient(send=sent.append)
    secret = "sk-should-never-appear-in-any-audit-entry-9f3a"
    client.handle_message({
        "id": 1, "method": "item/commandExecution/requestApproval",
        "params": {"itemId": "item1", "threadId": "thr1", "turnId": "turn1", "startedAtMs": 0,
                   "command": f"curl -H 'Authorization: Bearer {secret}'", "reason": secret},
    })
    assert len(client.audit) == 2  # one server_request entry, one client_response entry
    assert secret not in json.dumps(client.audit)
    allowed_keys = {"event", "method", "request_id", "thread_id", "turn_id", "item_id", "action"}
    for entry in client.audit:
        assert set(entry) <= allowed_keys
        assert "params" not in entry and "result" not in entry


def test_audit_log_path_writes_jsonl_when_configured(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    sent = []
    client = Gate0AppServerClient(send=sent.append, audit_log_path=log_path)
    client.handle_message({
        "id": 1, "method": "item/fileChange/requestApproval",
        "params": {"itemId": "i1", "threadId": "t1", "turnId": "tu1", "startedAtMs": 0},
    })
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        entry = json.loads(line)
        assert set(entry) <= {"event", "method", "request_id", "thread_id", "turn_id", "item_id", "action"}


def test_invalid_permission_scope_rejected_at_construction():
    with pytest.raises(ValueError):
        Gate0AppServerClient(send=lambda message: None, permission_scope="bogus")


# ---------------------------------------------------------------------------
# initialize()/thread/start() handshake never auto-starts a turn (the one paid step stays manual).
# ---------------------------------------------------------------------------

def test_initialize_then_start_thread_never_auto_sends_turn_start():
    sent = []

    def fake_send(message):
        sent.append(message)
        if "id" in message and message.get("method") == "initialize":
            client.handle_message({"id": message["id"], "result": {
                "codexHome": "/home/.codex", "platformFamily": "windows",
                "platformOs": "windows", "userAgent": "codex-cli/0.144.3",
            }})
        elif "id" in message and message.get("method") == "thread/start":
            client.handle_message({"id": message["id"], "result": {"thread": {"id": "thr1"}}})

    client = Gate0AppServerClient(send=fake_send, permission_scope="session")
    client.initialize()
    client.start_thread(cwd="/workspace")

    methods_sent = [message["method"] for message in sent if "method" in message]
    assert methods_sent == ["initialize", "initialized", "thread/start"]
    assert "turn/start" not in methods_sent

    thread_start_message = next(message for message in sent if message.get("method") == "thread/start")
    assert thread_start_message["params"]["approvalsReviewer"] == "user"
    assert thread_start_message["params"]["cwd"] == "/workspace"


def test_start_thread_fields_match_ground_truth_thread_start_params_schema():
    # start_thread sends {"cwd": ..., "approvalsReviewer": "user", ...} -- confirm both are the REAL
    # ThreadStartParams field names and that "user" is a real ApprovalsReviewer enum value (not just
    # hand-matched to the mock), so a future codex rename/removal of either fails HERE instead of
    # silently mis-routing approvals to the wrong reviewer at the paid turn. ThreadStartParams.json
    # (committed) was, before this test, never loaded by any test in this file.
    schema = _load_schema("ThreadStartParams.json")
    assert "cwd" in schema["properties"]
    assert "approvalsReviewer" in schema["properties"]
    allowed_reviewers = schema["definitions"]["ApprovalsReviewer"]["enum"]
    assert "user" in allowed_reviewers

    sent = []

    def fake_send(message):
        sent.append(message)
        if message.get("method") == "thread/start":
            client.handle_message({"id": message["id"], "result": {"thread": {"id": "thr1"}}})

    client = Gate0AppServerClient(send=fake_send)
    client.start_thread(cwd="/workspace")

    thread_start_message = next(message for message in sent if message.get("method") == "thread/start")
    params = thread_start_message["params"]
    _assert_keys_allowed(params, schema)
    assert params["cwd"] == "/workspace"
    assert params["approvalsReviewer"] == "user"


def test_build_turn_start_request_is_pure_and_never_auto_sent():
    request = build_turn_start_request("thr1", [{"type": "text", "text": "hi"}])
    assert request == {"threadId": "thr1", "input": [{"type": "text", "text": "hi"}]}
