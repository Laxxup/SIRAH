from __future__ import annotations

import json
import stat

from sirah.conversation.session_log import (
    SessionLog,
    delete_session,
    purge_sessions,
    resolve_session,
)


def test_session_log_uses_private_jsonl_and_redacts_content_by_default(tmp_path):
    log = SessionLog(state_home=tmp_path)
    log.write("response_validated", transcript="private", pcm=b"audio", token="secret")
    log.close()

    records = [json.loads(line) for line in log.path.read_text().splitlines()]
    assert stat.S_IMODE(log.path.stat().st_mode) == 0o600
    assert all("transcript" not in record and "pcm" not in record and "token" not in record for record in records)
    assert resolve_session(log.session_id, tmp_path) == log.path


def test_session_log_records_text_only_when_explicitly_authorized(tmp_path):
    log = SessionLog(include_text=True, state_home=tmp_path)
    log.write("response_validated", transcript="hola", validated_speech="buenas")
    log.close()

    assert "hola" in log.path.read_text()


def test_delete_and_purge_only_remove_recognized_session_files(tmp_path):
    logs = [SessionLog(state_home=tmp_path) for _ in range(3)]
    for log in logs:
        log.close()

    deleted = delete_session(logs[0].session_id, tmp_path)
    assert not deleted.exists()
    assert len(purge_sessions(tmp_path, keep=1)) == 1
