# Codex Vigil persistent-session live smoke evidence

Generated: 2026-07-09T23:25:56Z

Result: successful, bounded continuity smoke.

Deployment: PR `#8`, merge commit
`5b56e11053c5a46bc0baf698ba8a8d09d3f385aa`.

| Check | Evidence |
|---|---|
| Runner received first admitted live turn | `action=wake-ok`, `verdict=SPEAK`, `wake_exit=0`, `message_id=1524918915925545041` |
| First wake created the dedicated Codex task | `codex_session_id=019f4931-7b42-72d3-80c1-071a0aa56c09` |
| Outbound re-gate suppressed the first attempted send | `direction=hook-outbound`, `action=deny-pass`, `trigger_message_id=1524918915925545041` |
| Runner received a second admitted live turn | `action=wake-ok`, `verdict=SPEAK`, `wake_exit=0`, `message_id=1524918945847574590` |
| Second wake resumed the exact same Codex task | `codex_session_id=019f4931-7b42-72d3-80c1-071a0aa56c09` |
| Outbound hook allowed the second room send | `direction=hook-outbound`, `action=allow-speak`, `trigger_message_id=1524918945847574590` |
| Discord room delivery confirmed | `reply_message_id=1524919275670736906` |
| Configuration app health saw persisted state | `mode=persistent`, `active=true`, no state error |

Channel: `1522258711047831653`

This proves two admitted Discord turns reached one persisted Codex task through
the deployed push-driven runner, and that one response traversed the outbound
gate and reached Discord. It does not establish sustained operation, reconnect
continuity over a long interval, or behavior under transport backlog.

Message bodies were intentionally omitted from this evidence file.
