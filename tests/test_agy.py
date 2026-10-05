import json
import subprocess
from pathlib import Path

import pytest

from airlock import cli
from airlock.adapters.agy import AgyAdapter
from airlock.adapters.base import ProviderError
from airlock.models import AgentMode, AgentRequest, ReviewResult, Verdict
from airlock.schema import parse_review_json


def make_request(tmp_path, mode=AgentMode.READ):
    schema = tmp_path / 'schema.json'
    schema.write_text('{"type":"object"}')
    return AgentRequest('review', tmp_path, schema if mode is AgentMode.READ else None, 10, mode)


@pytest.mark.parametrize('mode', [AgentMode.READ, AgentMode.WRITE])
def test_agy_isolated_agent_and_subprocess(monkeypatch, tmp_path, mode):
    request = make_request(tmp_path, mode)
    launches = []

    def fake_run(command, **kwargs):
        launch = Path(kwargs['cwd'])
        launches.append(launch)
        hooks = json.loads((launch / '.agents' / 'hooks.json').read_text())
        assert hooks['airlock-capability-gate']['PreToolUse'][0]['matcher'] == '*'
        config = json.loads((launch / 'gate-config.json').read_text())
        assert config == {'root': str(tmp_path), 'writing': mode is AgentMode.WRITE}
        (launch / 'gate-active').write_text('active')
        if mode is AgentMode.READ:
            assert '--mode' not in command
            assert command[command.index('--json-schema') + 1] == str(request.schema_path)
        else:
            assert command[command.index('--mode') + 1] == 'accept-edits'
            assert '--json-schema' not in command
        assert command[command.index('--add-dir') + 1] == str(tmp_path)
        assert str(tmp_path) in kwargs['input']
        assert kwargs['timeout'] == 10
        assert launch != tmp_path
        assert '--dangerously-skip-permissions' not in command
        assert '--continue' not in command and '--conversation' not in command
        assert '--disable-slash-commands' in command
        return subprocess.CompletedProcess(command, 0, json.dumps({
            'status': 'SUCCESS', 'response': 'repaired',
            'structured_output': {'verdict': 'approve', 'summary': 'clean', 'reasonable': [], 'findings': []},
        }), '')

    monkeypatch.setattr('airlock.adapters.base.shutil.which', lambda _: '/bin/agy')
    monkeypatch.setattr('airlock.adapters.base.subprocess.run', fake_run)
    result = AgyAdapter().run(request)
    assert parse_review_json(result.output).verdict is Verdict.APPROVE
    assert all(not path.exists() for path in launches)
    assert not (tmp_path / '.agents').exists()


@pytest.mark.parametrize('output', [
    'invalid', '{}', '[]',
    '{"status":"SUCCESS"}',
    '{"status":"SUCCESS","structured_output":null}',
    '{"status":"SUCCESS","error":"permission denied","structured_output":{}}',
    *[json.dumps({'status': status, 'structured_output': {'verdict': 'approve'}})
      for status in ['ERROR', 'WAITING', 'CANCELED', 'INTERRUPTED', 'INVALID', 'RUNNING']],
])
def test_agy_invalid_or_unsuccessful_output_is_provider_failure(monkeypatch, tmp_path, output):
    monkeypatch.setattr('airlock.adapters.base.shutil.which', lambda _: '/bin/agy')
    def run(cmd, **kwargs):
        (Path(kwargs['cwd']) / 'gate-active').write_text('active')
        return subprocess.CompletedProcess(cmd, 0, output, '')
    monkeypatch.setattr('airlock.adapters.base.subprocess.run', run)
    with pytest.raises(ProviderError) as exc:
        AgyAdapter().run(make_request(tmp_path))
    assert exc.value.evidence['output'] == output


def test_agy_requires_read_schema(tmp_path):
    with pytest.raises(ValueError, match='schema'):
        AgyAdapter().command(AgentRequest('review', tmp_path, None, 10))


@pytest.mark.parametrize('writer,reviewer', [('agy', 'codex'), ('claude', 'agy')])
def test_cli_agy_repair_routing(monkeypatch, writer, reviewer):
    def repair(**kwargs):
        assert kwargs['writer'].executable == writer
        assert kwargs['reviewer'].executable == reviewer
        return ReviewResult(Verdict.APPROVE, 'clean'), type('Store', (), {'artifact_path': Path('/tmp/run')})()
    monkeypatch.setattr(cli, 'repair_repository', repair)
    assert cli.main(['repair', '--writer', writer, '--reviewer', reviewer, '--task', 'fix']) == 0


def test_cli_agy_review_routing(monkeypatch):
    def review(**kwargs):
        assert isinstance(kwargs['adapter'], AgyAdapter)
        return ReviewResult(Verdict.BLOCKED, 'blocked'), type('Store', (), {'artifact_path': Path('/tmp/run')})()
    monkeypatch.setattr(cli, 'review_repository', review)
    assert cli.main(['review', '--reviewer', 'agy']) == 2


@pytest.mark.parametrize('failure', ['missing', 'timeout', 'nonzero'])
def test_agy_provider_failures_preserve_evidence(monkeypatch, tmp_path, failure):
    monkeypatch.setattr('airlock.adapters.base.shutil.which',
                        lambda _: None if failure == 'missing' else '/bin/agy')
    def run(command, **kwargs):
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(command, 10, output=b'partial', stderr=b'timeout')
        return subprocess.CompletedProcess(command, 1, '', 'authentication required')
    monkeypatch.setattr('airlock.adapters.base.subprocess.run', run)
    with pytest.raises(ProviderError) as exc:
        AgyAdapter().run(make_request(tmp_path))
    assert exc.value.evidence['timed_out'] is (failure == 'timeout')
    assert exc.value.evidence['exit_code'] == (1 if failure == 'nonzero' else None)


@pytest.mark.parametrize('active,denied', [(False, False), (True, True)])
def test_agy_missing_hook_or_forbidden_attempt_never_approves(monkeypatch, tmp_path, active, denied):
    monkeypatch.setattr('airlock.adapters.base.shutil.which', lambda _: '/bin/agy')
    def run(cmd, **kwargs):
        launch = Path(kwargs['cwd'])
        if active:
            (launch / 'gate-active').write_text('active')
        if denied:
            (launch / 'gate-denied').write_text('denied')
        return subprocess.CompletedProcess(cmd, 0, json.dumps({
            'status': 'SUCCESS', 'structured_output': {
                'verdict': 'approve', 'summary': 'clean', 'reasonable': [], 'findings': [],
            },
        }), '')
    monkeypatch.setattr('airlock.adapters.base.subprocess.run', run)
    with pytest.raises(ProviderError, match='hook|forbidden'):
        AgyAdapter().run(make_request(tmp_path))


@pytest.mark.parametrize('tool', ['run_command', 'call_mcp_tool', 'invoke_subagent',
                                 'notebook_edit', 'ask_permission', 'unknown'])
def test_agy_gate_denies_other_capabilities(tmp_path, tool):
    from airlock.adapters.agy_gate import allowed_tool
    assert not allowed_tool({'name': tool, 'args': {}}, tmp_path, True)


def test_agy_gate_enforces_read_and_write_boundaries(tmp_path):
    from airlock.adapters.agy_gate import allowed_tool
    root = tmp_path / 'repo'
    root.mkdir()
    target = root / 'file.py'
    read = {'name': 'view_file', 'args': {'AbsolutePath': str(target)}}
    write = {'name': 'write_to_file', 'args': {'TargetFile': str(target)}}
    assert allowed_tool(read, root, False)
    assert allowed_tool(write, root, True)
    assert not allowed_tool(write, root, False)
    for path in [tmp_path / 'outside', root / '..' / 'outside', root / '.git' / 'config',
                 root / '.airlock' / 'runs' / 'verdict.json']:
        assert not allowed_tool({'name': 'write_to_file', 'args': {'TargetFile': str(path)}}, root, True)
    (root / 'escape').symlink_to(tmp_path, target_is_directory=True)
    assert not allowed_tool({'name': 'write_to_file',
                             'args': {'TargetFile': str(root / 'escape' / 'outside')}}, root, True)
    assert not allowed_tool({'name': 'view_file', 'args': {'AbsolutePath': 'relative'}}, root, False)


def test_agy_hook_malformed_input_denies(tmp_path):
    import sys
    from airlock.adapters import agy_gate
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'root': str(tmp_path), 'writing': False}))
    result = subprocess.run([sys.executable, agy_gate.__file__, str(config), 'check'],
                            input='invalid', text=True, capture_output=True, check=True)
    assert json.loads(result.stdout)['decision'] == 'deny'


def test_agy_gate_allows_structured_result_submission(tmp_path):
    from airlock.adapters.agy_gate import allowed_tool
    assert allowed_tool({'name': 'finish', 'args': {'verdict': 'blocked'}}, tmp_path, False)
    assert not allowed_tool({'name': 'finish', 'args': 'invalid'}, tmp_path, False)
