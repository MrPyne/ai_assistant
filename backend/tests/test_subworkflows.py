import pytest
from backend import tasks


def test_subworkflow_inline_execution():
    # child graph: single noop node
    child_graph = {
        'nodes': [
            {'id': 'c1', 'type': 'noop'}
        ],
        'edges': []
    }

    # parent graph: execute workflow node that references inline child graph
    parent_graph = {
        'nodes': [
            {
                'id': 'p1',
                'data': {
                    'label': 'ExecuteWorkflow',
                    'config': {
                        'workflow': child_graph
                    }
                }
            }
        ],
        'edges': []
    }

    res = tasks.process_run(run_db_id=12345, node_graph=parent_graph)
    assert res['status'] == 'success'
    outputs = res['output']
    # ensure parent node output contains subworkflow_result and that the child executed
    assert 'p1' in outputs
    sub = outputs['p1']
    assert 'subworkflow_result' in sub
    child_res = sub['subworkflow_result']
    assert isinstance(child_res, dict)
    assert child_res.get('status') == 'success'
    assert 'output' in child_res
    assert 'c1' in child_res['output']
    # noop node should yield a simple ok status
    assert child_res['output']['c1'] == {'status': 'ok'}
