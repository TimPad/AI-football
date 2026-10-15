import json
import os
import subprocess
import sys
from pathlib import Path
import pytest


def store(tmp_path):
    from aifootball.processor.workspace import Workspace
    return Workspace(tmp_path,{'source':'a'*64,'context':'b'*64})


def test_cache_integrity_and_fingerprint(tmp_path):
    from aifootball.processor.workspace import Workspace
    ws=store(tmp_path);ws.put_json('window-1',{'events':[]})
    assert store(tmp_path).get_json('window-1')=={'events':[]}
    with pytest.raises(ValueError,match='fingerprint'):Workspace(tmp_path,{'source':'c'*64})
    cache=next((tmp_path/'cache').glob('*.json'));cache.write_text('{"hash":"bad","value":{}}')
    with pytest.raises(ValueError,match='corrupt'):ws.get_json('window-1')


def test_cache_key_does_not_become_filesystem_path(tmp_path):
    ws=store(tmp_path);ws.put_json('../outside',{'value':2})
    assert ws.get_json('../outside')=={'value':2}
    assert not (tmp_path.parent/'outside').exists()


def test_exclusive_process_lock(tmp_path):
    ws=store(tmp_path)
    with ws.exclusive():
        code="from pathlib import Path; from aifootball.processor.workspace import Workspace; Workspace(Path(__import__('sys').argv[1]),{'source':'a'*64,'context':'b'*64})"
        proc=subprocess.run([sys.executable,'-c',code,str(tmp_path)],capture_output=True,text=True)
        assert proc.returncode!=0 and 'locked' in proc.stderr
    assert store(tmp_path).get_json('missing') is None


@pytest.mark.parametrize('after',[False,True])
def test_interruption_at_rename_leaves_old_or_new_complete_value(tmp_path,monkeypatch,after):
    ws=store(tmp_path);ws.put_json('window-1',{'events':['old']})
    real=os.replace
    def crash(src,dest):
        if after:real(src,dest)
        raise OSError('simulated crash')
    monkeypatch.setattr(os,'replace',crash)
    with pytest.raises(OSError):ws.put_json('window-1',{'events':['new']})
    monkeypatch.setattr(os,'replace',real)
    assert store(tmp_path).get_json('window-1')=={'events':['new' if after else 'old']}
    assert not list(tmp_path.rglob('*.tmp'))


def test_unknown_usage_does_not_reset_budget_on_resume(tmp_path):
    from aifootball.processor.budget import Budget
    budget=Budget(store(tmp_path),max_requests=1)
    reservation=budget.reserve_call('w1',100,200);budget.settle_call(reservation,None)
    resumed=Budget(store(tmp_path),max_requests=1)
    with pytest.raises(ValueError,match='budget'):resumed.reserve_call('w2',100,200)
    assert resumed.snapshot()['requests']==1 and resumed.snapshot()['usage_unknown'] is True


def test_real_usage_and_repeat_settlement(tmp_path):
    from aifootball.processor.budget import Budget
    budget=Budget(store(tmp_path),max_requests=3,max_input_tokens=100,max_output_tokens=100)
    first=budget.reserve_call('w1',60,60)
    with pytest.raises(ValueError,match='budget'):budget.reserve_call('w2',60,60)
    budget.settle_call(first,{'prompt_tokens':10,'completion_tokens':20})
    budget.settle_call(first,{'prompt_tokens':10,'completion_tokens':20})
    budget.reserve_call('w2',60,60)
    assert budget.snapshot()['input_tokens']==70
    assert budget.snapshot()['output_tokens']==80
    assert budget.snapshot()['requests']==2
    with pytest.raises(ValueError):budget.settle_call(first,{'prompt_tokens':9,'completion_tokens':20})


def test_reserved_request_survives_process_restart(tmp_path):
    from aifootball.processor.budget import Budget
    budget=Budget(store(tmp_path),max_requests=1)
    budget.reserve_call('w1',10,20)
    resumed=Budget(store(tmp_path),max_requests=1)
    with pytest.raises(ValueError,match='budget'):resumed.reserve_call('retry-w1',10,20)
    assert resumed.snapshot()['requests']==1
    assert resumed.snapshot()['usage_unknown'] is True


def test_actual_usage_over_limit_is_not_erased(tmp_path):
    from aifootball.processor.budget import Budget
    budget=Budget(store(tmp_path),max_input_tokens=100)
    reservation=budget.reserve_call('w1',80,20)
    budget.settle_call(reservation,{'prompt_tokens':120,'completion_tokens':10})
    assert budget.snapshot()['input_tokens']==120
    with pytest.raises(ValueError,match='budget'):budget.reserve_call('w2',1,1)


def test_budget_limit_policy_cannot_reset_consumption(tmp_path):
    from aifootball.processor.budget import Budget
    budget=Budget(store(tmp_path),max_requests=2)
    budget.reserve_call('w1',10,20)
    with pytest.raises(ValueError,match='budget'):Budget(store(tmp_path),max_requests=1)
