import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { vi } from 'vitest'

// Mock reactflow to avoid DOM measurement/runtime issues in jsdom.
// Provide minimal implementations for the pieces Editor imports.
vi.mock('reactflow', () => {
  const React = require('react')
  const MockReactFlow = ({ children }) => React.createElement(React.Fragment, null, children)
  const MockProvider = ({ children }) => React.createElement(React.Fragment, null, children)
  const Background = () => React.createElement('div', { 'data-testid': 'rf-background' })
  const Controls = () => React.createElement('div', { 'data-testid': 'rf-controls' })
  const addEdge = (params, edges) => edges.concat({ ...params, id: `e-${Date.now()}` })
  const applyNodeChanges = (changes, nodes) => nodes
  const applyEdgeChanges = (changes, edges) => edges
  return {
    __esModule: true,
    default: MockReactFlow,
    ReactFlowProvider: MockProvider,
    addEdge,
    Background,
    Controls,
    applyNodeChanges,
    applyEdgeChanges,
  }
})

import Editor from '../src/editor'

// Basic smoke tests for editor add-node handlers. These don't render the full
// reactflow canvas (which relies on DOM measurements), but they exercise the
// addNode logic by mounting the component and clicking palette buttons.

describe('Editor basic add node behavior', () => {
  test('adds HTTP node when Add HTTP Node clicked', async () => {
    render(<Editor />)
    const httpBtn = screen.getByText('Add HTTP Node')
    await userEvent.click(httpBtn)
    // Expect the new node label to appear in the UI (NodeRenderer renders label)
    expect(screen.getByText('HTTP Request')).toBeInTheDocument()
  })

  test('adds LLM node when Add LLM Node clicked', async () => {
    render(<Editor />)
    const llmBtn = screen.getByText('Add LLM Node')
    await userEvent.click(llmBtn)
    expect(screen.getByText('LLM')).toBeInTheDocument()
  })

  test('adds Webhook node when Add Webhook clicked', async () => {
    render(<Editor />)
    const webhookBtn = screen.getByText('Add Webhook')
    await userEvent.click(webhookBtn)
    expect(screen.getByText('Webhook Trigger')).toBeInTheDocument()
  })

  test('selects newly added node (right panel shows Node id)', async () => {
    render(<Editor />)
    const llmBtn = screen.getByText('Add LLM Node')
    await userEvent.click(llmBtn)
    // The right-hand panel should show the selected node id when a node is selected
    expect(screen.getByText(/Node id:/)).toBeInTheDocument()
  })

  test('updates HTTP node config when edited', async () => {
    render(<Editor />)
    const httpBtn = screen.getByText('Add HTTP Node')
    await userEvent.click(httpBtn)

    // The HTTP method select should initially show GET; change it to POST
    const methodSelect = screen.getByDisplayValue('GET')
    await userEvent.selectOptions(methodSelect, 'POST')
    expect(screen.getByDisplayValue('POST')).toBeInTheDocument()
  })

  test('saveWorkflow posts current graph including selected node', async () => {
    render(<Editor />)

    // stub fetch and alert
    const origFetch = global.fetch
    const origAlert = window.alert
    window.alert = vi.fn()
    global.fetch = vi.fn(async (url, opts) => {
      return {
        ok: true,
        json: async () => ({ id: 42 }),
      }
    })

    try {
      // add a node so there is a selection to persist
      const httpBtn = screen.getByText('Add HTTP Node')
      await userEvent.click(httpBtn)

      const saveBtn = screen.getByText('Save')
      await userEvent.click(saveBtn)

      // wait for fetch to be called
      await screen.findByText('Selected workflow id:', {}, { timeout: 1000 })

      expect(global.fetch).toHaveBeenCalled()
      const call = global.fetch.mock.calls[0]
      expect(call[0]).toBe('/api/workflows')
      const opts = call[1]
      expect(opts.method).toBe('POST')
      const payload = JSON.parse(opts.body)
      expect(payload).toHaveProperty('graph')
      expect(Array.isArray(payload.graph.nodes)).toBe(true)
      // selected_node_id should be present (the editor persists selection)
      expect(payload.graph).toHaveProperty('selected_node_id')
    } finally {
      global.fetch = origFetch
      window.alert = origAlert
    }
  })
})
