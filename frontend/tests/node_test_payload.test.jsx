import React from 'react'
import { render, fireEvent, waitFor, findByText } from '@testing-library/react'
import NodeTestModal from '../src/components/NodeTestModal'

// Ensure the NodeTestModal includes provider override and secret override
// in the POST payload when the user selects them.

describe('Node Test payload', () => {
  beforeEach(() => {
    global.fetch = jest.fn()
  })
  afterEach(() => {
    jest.resetAllMocks()
  })

  it('sends provider_id and _override_secret_id when overrides selected', async () => {
    const providers = [{ id: 10, type: 'openai' }, { id: 20, type: 'ollama' }]
    const secrets = [{ id: 100, name: 'dev-key' }, { id: 200, name: 'other-key' }]
    const node = { id: 'n1', data: { label: 'LLM', config: { provider_id: 10 } } }

    // Mock the fetch response for the node_test call
    const mockResp = { result: { text: '[mock]' }, warnings: [] }
    global.fetch.mockResolvedValueOnce({ ok: true, text: async () => JSON.stringify(mockResp) })

    const { getByText, getByDisplayValue, container } = render(
      <NodeTestModal node={node} token={'tok'} providers={providers} secrets={secrets} onClose={() => {}} />
    )

    // Modal header should render
    await findByText(container, 'Test Node: LLM')

    // Select provider override (choose the second provider)
    const selects = container.querySelectorAll('select')
    // First select is provider override, second is secret override
    expect(selects.length).toBeGreaterThanOrEqual(2)
    const providerSelect = selects[0]
    const secretSelect = selects[1]

    // Change provider to id 20
    fireEvent.change(providerSelect, { target: { value: String(providers[1].id) } })
    // Change secret to id 200
    fireEvent.change(secretSelect, { target: { value: String(secrets[1].id) } })

    // Click Run Test
    fireEvent.click(getByText('Run Test'))

    await waitFor(() => expect(global.fetch).toHaveBeenCalled())

    // Inspect the fetch call payload
    expect(global.fetch).toHaveBeenCalledWith('/api/node_test', expect.any(Object))
    const opts = global.fetch.mock.calls[0][1]
    expect(opts).toBeDefined()
    expect(opts.method).toBe('POST')
    expect(opts.headers['Content-Type']).toBe('application/json')
    // parse body
    const body = JSON.parse(opts.body)
    expect(body).toBeDefined()
    // node should include provider_id and _override_secret_id set to the selected values
    expect(body.node).toBeDefined()
    expect(body.node.provider_id).toBe(Number(providers[1].id))
    expect(body.node._override_secret_id).toBe(Number(secrets[1].id))
  })
})
