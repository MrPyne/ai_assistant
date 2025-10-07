import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { vi } from 'vitest'

// Reuse react-flow-renderer mock to avoid DOM issues
vi.mock('react-flow-renderer', () => {
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

// Lightweight EventSource mock
class MockEventSource {
  constructor(url) {
    this.url = url
    this.onmessage = null
    this.onerror = null
    MockEventSource._last = this
    MockEventSource.createdCount = (MockEventSource.createdCount || 0) + 1
    MockEventSource._instances = MockEventSource._instances || []
    MockEventSource._instances.push(this)
  }
  close() {
    /* noop */
  }
  triggerMessage(data) {
    if (this.onmessage) this.onmessage({ data: JSON.stringify(data) })
  }
  triggerError() {
    if (this.onerror) this.onerror(new Error('stream error'))
  }
}

describe('Editor sanitization and SSE behavior', () => {
  test('loadWorkflows sanitizes numeric ids and missing/malformed node data and restores selection', async () => {
    const origFetch = global.fetch
    const origAlert = window.alert
    window.alert = vi.fn()

    // respond to GET /api/workflows with a workflow that has numeric ids and bad data
    global.fetch = vi.fn(async (url, opts) => {
      const s = String(url || '')
      if (s.includes('/api/workflows') && (!opts || !opts.method)) {
        // Return a single workflow with graph.nodes containing numeric id and malformed data
        return {
          ok: true,
          json: async () => ([{
            id: 42,
            graph: {
              nodes: [
                { id: 1, // numeric id
                  // data is a string (malformed); sanitize should replace with object
                  data: 'not-an-object',
                  position: { x: 10, y: 20 },
                  selected: true
                }
              ],
              edges: [],
              selected_node_id: 1
            }
          }])
        }
      }
      // default
      return { ok: true, json: async () => ([]) }
    })

    try {
      render(<Editor />)
      const tokenInput = screen.getByPlaceholderText('Paste bearer token here')
      await userEvent.type(tokenInput, 't')

      const loadBtn = screen.getByText('Load')
      await userEvent.click(loadBtn)

      // The sanitized node should show in the Selected Node panel and selected id restored
      expect(await screen.findByText(/Node id:/)).toBeInTheDocument()
      // selected id should be '1' (stringified)
      expect(screen.getByText(/Node id:\s*/)).toBeTruthy()
      expect(screen.getByText('1')).toBeTruthy()
    } finally {
      global.fetch = origFetch
      window.alert = origAlert
    }
  })

  test('loadWorkflows handles legacy array graph format and clears selection', async () => {
    const origFetch = global.fetch
    const origAlert = window.alert
    window.alert = vi.fn()

    global.fetch = vi.fn(async (url, opts) => {
      const s = String(url || '')
      if (s.includes('/api/workflows') && (!opts || !opts.method)) {
        // legacy graph: array of elements
        return {
          ok: true,
          json: async () => ([{
            id: 7,
            graph: [
              { id: 'n1', type: 'input', data: { label: 'Webhook Trigger' }, position: { x: 0, y: 0 } },
              { id: 'n2', source: 'n1', target: 'n3' }
            ]
          }])
        }
      }
      return { ok: true, json: async () => ([]) }
    })

    try {
      render(<Editor />)
      const tokenInput = screen.getByPlaceholderText('Paste bearer token here')
      await userEvent.type(tokenInput, 't')

      const loadBtn = screen.getByText('Load')
      await userEvent.click(loadBtn)

      // For legacy flows, selection should be cleared
      expect(await screen.findByText(/Selected workflow id:/)).toBeInTheDocument()
      // selected node panel should indicate no node selected
      expect(await screen.findByText('No node selected. Click a node to view/edit its config.')).toBeInTheDocument()
    } finally {
      global.fetch = origFetch
      window.alert = origAlert
    }
  })

  test('viewRunLogs handles EventSource errors and allows reopening the stream', async () => {
    const origFetch = global.fetch
    const origEventSource = global.EventSource
    const origAlert = window.alert
    window.alert = vi.fn()

    // stub fetch for run workflow flow
    global.fetch = vi.fn(async (url, opts) => {
      const s = String(url || '')
      if (s.includes('/api/workflows') && opts && opts.method === 'POST') {
        return { ok: true, json: async () => ({ id: 99 }) }
      }
      if (s.includes('/api/workflows/99/run') && opts && opts.method === 'POST') {
        return { ok: true, json: async () => ({ run_id: 500 }) }
      }
      if (s.includes('/api/runs?workflow_id=99')) {
        return { ok: true, json: async () => ({ items: [{ id: 500, status: 'queued' }], total: 1, limit: 50, offset: 0 }) }
      }
      if (s.includes('/api/runs/500/logs')) {
        return { ok: true, json: async () => ({ logs: [] }) }
      }
      return { ok: true, json: async () => ([]) }
    })

    try {
      global.EventSource = MockEventSource

      render(<Editor />)

      // add and save then run to open initial EventSource
      const httpBtn = screen.getByText('Add HTTP Node')
      await userEvent.click(httpBtn)

      const saveBtn = screen.getByText('Save')
      await userEvent.click(saveBtn)

      const runBtn = screen.getByText('Run')
      await userEvent.click(runBtn)

      // ensure we created an EventSource
      expect(MockEventSource.createdCount).toBeGreaterThanOrEqual(1)
      const first = MockEventSource._last
      expect(first).toBeTruthy()

      // simulate error on the EventSource
      first.triggerError()

      // now open logs again by clicking View Logs for the run
      const viewBtn = await screen.findByText('View Logs')
      await userEvent.click(viewBtn)

      // a new EventSource should have been created
      expect(MockEventSource.createdCount).toBeGreaterThanOrEqual(2)
    } finally {
      global.fetch = origFetch
      global.EventSource = origEventSource
      window.alert = origAlert
    }
  })
})
