import React from 'react'
import { render, fireEvent, waitFor } from '@testing-library/react'
import Editor from '../src/editor'

// Basic smoke test to ensure the Test Node modal opens and calls the API.
// We mock fetch to return a canned response.

describe('Node Test UI', () => {
  beforeEach(() => {
    global.fetch = jest.fn()
  })
  afterEach(() => {
    jest.resetAllMocks()
  })

  it('opens modal and displays mock response', async () => {
    const mockResp = { result: { text: '[mock]' }, warnings: [] }
    global.fetch.mockResolvedValueOnce({ ok: true, text: async () => JSON.stringify(mockResp) })

    const { getByText, findByText } = render(<Editor />)

    // Add an LLM node then select it
    fireEvent.click(getByText('Add LLM Node'))
    // The node list is rendered by react-flow which our test environment
    // may not mount fully; instead interact with the sidebar Selected Node
    // by selecting the newly added node via the Save button which sets selection.

    // Click the Save button to ensure nodes exist (no-op)
    fireEvent.click(getByText('Save'))

    // Click Add LLM Node again to ensure a selected node appears in right panel
    fireEvent.click(getByText('Add LLM Node'))

    // The Selected Node header should appear
    await findByText('Selected Node')

    // Click Test Node button
    fireEvent.click(getByText('Test Node'))

    // Modal should render and we can click Run Test
    await findByText('Test Node: LLM')
    // Ensure provider override UI is present
    await findByText('Provider override (optional)')
    // Select no override and run
    fireEvent.click(getByText('Run Test'))

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/api/node_test', expect.any(Object)))

    // Response should appear in modal
    await findByText('[mock]')
  })
})
