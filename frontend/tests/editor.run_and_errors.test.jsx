import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { vi } from 'vitest'

// Reuse reactflow mock to avoid DOM issues
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

// Simple EventSource mock to simulate SSE streaming in tests
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
  // helper for tests to simulate incoming messages
  triggerMessage(data) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) })
    }
  }
}

describe('Editor run and error handling', () => {
  test('runWorkflow queues a run, loads existing logs and streams new ones via EventSource', async () => {
    const origFetch = global.fetch
    const origEventSource = global.EventSource
    const origAlert = window.alert
    window.alert = vi.fn()

    // make a fetch stub that handles various endpoints used by runWorkflow/viewRunLogs
    global.fetch = vi.fn(async (url, opts) => {
      const s = String(url || '')
      if (s.includes('/api/workflows') && opts && opts.method === 'POST') {
        // saveWorkflow -> returns workflow id
        return { ok: true, json: async () => ({ id: 99 }) }
      }
      if (s.includes('/api/workflows/99/run') && opts && opts.method === 'POST') {
        return { ok: true, json: async () => ({ run_id: 500 }) }
      }
      if (s.includes('/api/runs?workflow_id=99')) {
        return { ok: true, json: async () => ([{ id: 500, status: 'queued' }]) }
      }
      if (s.includes('/api/runs/500/logs')) {
        return { ok: true, json: async () => ({ logs: [{ id: 'l1', timestamp: 't', node_id: 'n-1', level: 'info', message: 'initial log' }] }) }
      }
      // default for other calls
      return { ok: true, json: async () => ([]) }
    })

    try {
      // install EventSource mock
      global.EventSource = MockEventSource

      render(<Editor />)

      // add a node and save to set workflow id
      const httpBtn = screen.getByText('Add HTTP Node')
      await userEvent.click(httpBtn)

      const saveBtn = screen.getByText('Save')
      await userEvent.click(saveBtn)

      // wait for selected workflow id text to update
      expect(await screen.findByText(/Selected workflow id:/)).toBeInTheDocument()

      // now click Run
      const runBtn = screen.getByText('Run')
      await userEvent.click(runBtn)

      // after running, loadRuns should have been called and logs loaded
      expect(global.fetch).toHaveBeenCalled()
      // initial logs should appear in the Selected Run Logs pane
      expect(await screen.findByText('initial log')).toBeInTheDocument()

      // simulate SSE streaming a new log message
      const es = MockEventSource._last
      expect(es).toBeTruthy()
      es.triggerMessage({ id: 'l2', timestamp: 't2', node_id: 'n-1', level: 'info', message: 'streamed log' })

      // the streamed message should appear
      expect(await screen.findByText('streamed log')).toBeInTheDocument()

      // ensure alert was called to indicate run queued
      expect(window.alert).toHaveBeenCalled()
    } finally {
      global.fetch = origFetch
      global.EventSource = origEventSource
      window.alert = origAlert
    }
  })

  test('viewRunLogs cleans up previous EventSource and opens a new one on repeated view calls', async () => {
    const origFetch = global.fetch
    const origEventSource = global.EventSource
    const origAlert = window.alert
    window.alert = vi.fn()

    global.fetch = vi.fn(async (url, opts) => {
      const s = String(url || '')
      if (s.includes('/api/workflows') && opts && opts.method === 'POST') {
        return { ok: true, json: async () => ({ id: 99 }) }
      }
      if (s.includes('/api/workflows/99/run') && opts && opts.method === 'POST') {
        return { ok: true, json: async () => ({ run_id: 500 }) }
      }
      if (s.includes('/api/runs?workflow_id=99')) {
        return { ok: true, json: async () => ([{ id: 500, status: 'queued' }]) }
      }
      if (s.includes('/api/runs/500/logs')) {
        return { ok: true, json: async () => ({ logs: [] }) }
      }
      return { ok: true, json: async () => ([]) }
    })

    try {
      global.EventSource = MockEventSource

      render(<Editor />)

      // add a node and save
      const httpBtn = screen.getByText('Add HTTP Node')
      await userEvent.click(httpBtn)

      const saveBtn = screen.getByText('Save')
      await userEvent.click(saveBtn)

      // run to create first EventSource
      const runBtn = screen.getByText('Run')
      await userEvent.click(runBtn)

      // wait for EventSource to be constructed
      expect(MockEventSource.createdCount).toBeGreaterThanOrEqual(1)

      // click View Logs in runs list to trigger a second EventSource
      const viewBtn = await screen.findByText('View Logs')
      await userEvent.click(viewBtn)

      // another EventSource should have been created
      expect(MockEventSource.createdCount).toBeGreaterThanOrEqual(2)
    } finally {
      global.fetch = origFetch
      global.EventSource = origEventSource
      window.alert = origAlert
    }
  })

  test('saveWorkflow shows alert on non-ok response', async () => {
    const origFetch = global.fetch
    const origAlert = window.alert
    window.alert = vi.fn()

    global.fetch = vi.fn(async (url, opts) => {
      const s = String(url || '')
      if (s.includes('/api/workflows') && opts && opts.method === 'POST') {
        return { ok: false, text: async () => 'server error' }
      }
      return { ok: true, json: async () => ([]) }
    })

    try {
      render(<Editor />)
      const httpBtn = screen.getByText('Add HTTP Node')
      await userEvent.click(httpBtn)

      const saveBtn = screen.getByText('Save')
      await userEvent.click(saveBtn)

      expect(window.alert).toHaveBeenCalled()
      // should indicate failure
      expect(window.alert.mock.calls.some(c => String(c[0]).includes('Save failed'))).toBe(true)
    } finally {
      global.fetch = origFetch
      window.alert = origAlert
    }
  })

  test('loadWorkflows shows alert when request fails', async () => {
    const origFetch = global.fetch
    const origAlert = window.alert
    window.alert = vi.fn()

    global.fetch = vi.fn(async (url, opts) => {
      const s = String(url || '')
      if (s.includes('/api/workflows') && (!opts || !opts.method)) {
        return { ok: false, text: async () => 'nope' }
      }
      return { ok: true, json: async () => ([]) }
    })

    try {
      render(<Editor />)
      const tokenInput = screen.getByPlaceholderText('Paste bearer token here')
      await userEvent.type(tokenInput, 't')

      const loadBtn = screen.getByText('Load')
      await userEvent.click(loadBtn)

      expect(window.alert).toHaveBeenCalled()
      expect(window.alert.mock.calls.some(c => String(c[0]).includes('Failed to load workflows'))).toBe(true)
    } finally {
      global.fetch = origFetch
      window.alert = origAlert
    }
  })
})
