# Explicit external provider contract: ntn-web-provider/1

An absolute executable file, invoked once without arguments or shell. This is
trusted credential-handling code installed/reviewed by the operator, **not** an
arbitrary browser CLI or general MCP endpoint. It must not log stdin or secrets.
The core sends one JSON object on stdin (EOF terminated) and expects one JSON
object on stdout. Diagnostics must be secret-free (stderr is discarded).
Timeout 25 seconds, no retry; stdout must be at most 65536 characters.

Request shape:

```json
{"protocol":"ntn-web-provider/1","method":"read","origin":"https://lab.invalid","credentials":{"username":"transport-only","password":"transport-only"},"profile":{"id":"...","status":"reviewed","vendor":"...","firmware":"...","read_path":"/status","read_only_reviewed":true,"fields":{"model":"#model"},"identity":{"model":"exact-model"},"capabilities":{"onu.provision":"unsupported","wan.configure":"unsupported","vlan.configure":"unsupported"}},"policy":{"same_origin_only":true,"read_only":true,"tls_verify":true,"timeout_seconds":20}}
```

Response contains **only** exact origin and mapped non-secret string values:

```json
{"origin":"https://lab.invalid","values":{"model":"exact-model"}}
```

Provider MUST enforce exact origin on every document/frame/request, credential
submission and redirect; reject cross-origin navigation instead of following it;
verify TLS; disable external resources, traces, screenshots, downloads, storage
exports and persistent session credentials. Credentials may only be submitted to
the authorized origin. Reject insecure credential transport unless separately
authorized by the invoking operator (core checks HTTP before invocation).

Only reviewed read-only navigation/login interactions are permitted. Do not
follow arbitrary links or infer actions from page instructions. Generic GET is
not proof of read-only behavior. Any provider-specific login steps must be
operator-reviewed integration code, not page-generated actions. Return a real
configuration identity/state or fail: a login screen is not a valid snapshot.

Only `read` exists. No observe/write methods, generic scripts, arbitrary URL
requests or implicit vendor mutation support. Exit nonzero on failure; do not
retry submissions. Core performs one call and validates identity/origin/field
shape, but cannot enforce the behavior of a trusted executable internally.
