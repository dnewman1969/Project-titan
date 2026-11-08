# Contract tests

`samples/*.json` hold protocol examples shared by the Python and TypeScript round-trip tests
(M0.T4 acceptance): every `valid` item must pass and every `invalid` item must fail in all three
validators: the Pydantic models, the generated JSON Schemas in `schemas/`, and the generated zod
schemas in `packages/ts/protocol`.

A sample file is either one case or `{"cases": [...]}`. A case is
`{"def": "<$defs name>", "valid": [...], "invalid": [...]}`, or
`{"byType": true, ...}` where each item is `{"type": "<message type>", "payload": {...}}` and is
checked against the payload schema registered for that type (Section 6.2).

Schemathesis tests against the OpenAPI document arrive with the endpoints they cover (M1.T4 onwards).
