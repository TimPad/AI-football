"""Reserve before every paid attempt. Unknown usage never refunds its reservation."""
from hashlib import sha256
from uuid import uuid4


class Budget:
    KEY='__qwen_budget_v1__'

    def __init__(self,workspace,*,max_requests=200,max_input_tokens=300000,max_output_tokens=100000):
        self.workspace=workspace
        self.limits={'max_requests':max_requests,'max_input_tokens':max_input_tokens,'max_output_tokens':max_output_tokens}
        if any(type(v) is not int or v<0 for v in self.limits.values()):raise ValueError('invalid budget limits')
        with workspace.exclusive():
            state=workspace.get_json(self.KEY)
            if state is None:workspace.put_json(self.KEY,{'version':'1','limits':self.limits,'entries':{}})
            else:self._validate(state)

    def _validate(self,state):
        if state.get('version')!='1' or state.get('limits')!=self.limits or type(state.get('entries')) is not dict:
            raise ValueError('budget policy mismatch or corrupt ledger')
        for entry in state['entries'].values():
            if (type(entry) is not dict or set(entry)!={'key_sha256','input_tokens','output_tokens','state','usage'} or
                entry['state'] not in ('reserved','completed','unknown') or
                any(type(entry[k]) is not int or entry[k]<0 for k in ('input_tokens','output_tokens'))):
                raise ValueError('corrupt budget ledger')
        return state

    def _state(self):return self._validate(self.workspace.get_json(self.KEY))

    def _snapshot(self,state):
        entries=list(state['entries'].values())
        return {**self.limits,'requests':len(entries),'input_tokens':sum(e['input_tokens'] for e in entries),
                'output_tokens':sum(e['output_tokens'] for e in entries),
                'usage_unknown':any(e['state']!='completed' for e in entries)}

    def snapshot(self):
        with self.workspace.exclusive():return self._snapshot(self._state())

    def reserve_call(self,key,input_estimate,output_limit):
        if type(key) is not str or not key or any(type(v) is not int or v<0 for v in (input_estimate,output_limit)):
            raise ValueError('invalid budget reservation')
        with self.workspace.exclusive():
            state=self._state();totals=self._snapshot(state)
            if (totals['requests']+1>self.limits['max_requests'] or
                totals['input_tokens']+input_estimate>self.limits['max_input_tokens'] or
                totals['output_tokens']+output_limit>self.limits['max_output_tokens']):raise ValueError('budget exhausted')
            reservation=str(uuid4())
            state['entries'][reservation]={'key_sha256':sha256(key.encode()).hexdigest(),'input_tokens':input_estimate,
                                          'output_tokens':output_limit,'state':'reserved','usage':None}
            self.workspace.put_json(self.KEY,state)
            return reservation

    def settle_call(self,reservation,usage):
        if usage is not None and (type(usage) is not dict or any(type(usage.get(k)) is not int or usage[k]<0 for k in ('prompt_tokens','completion_tokens'))):
            raise ValueError('invalid budget usage')
        # completion_tokens already includes reasoning tokens; do not add details again.
        normalized=None if usage is None else {'prompt_tokens':usage['prompt_tokens'],'completion_tokens':usage['completion_tokens']}
        with self.workspace.exclusive():
            state=self._state()
            if reservation not in state['entries']:raise ValueError('unknown budget reservation')
            entry=state['entries'][reservation]
            if entry['state']!='reserved':
                if entry['usage']!=normalized:raise ValueError('budget already settled differently')
                return
            entry['state']='unknown' if normalized is None else 'completed';entry['usage']=normalized
            if normalized is not None:entry['input_tokens']=normalized['prompt_tokens'];entry['output_tokens']=normalized['completion_tokens']
            self.workspace.put_json(self.KEY,state)
