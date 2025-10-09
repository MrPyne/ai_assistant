import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { vi } from 'vitest'

// Mock react-flow-renderer like other editor tests
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

// Test that when backend returns structured validation error { message, node_id }
// the editor focuses the offending node, displays the validation message, and
// marks the node visually as invalid (NodeRenderer applies red border/style).

describe('Editor validation error handling (structured response)', () => {
  test('saveWorkflow handles 400 JSON {message,node_id} by selecting and marking the node', async () => {
    const origFetch = global.fetch
    const origAlert = window.alert
    window.alert = vi.fn()

    // Stub fetch to return a non-ok JSON body extracting the node id from the
    // posted payload so tests don't need to know the generated id beforehand.
    global.fetch = vi.fn(async (url, opts) => {
      const s = String(url || '')
      if (s.includes('/api/workflows') && opts && opts.method === 'POST') {
        try {
          const body = JSON.parse(opts.body || '{}')
          // prefer selected_node_id if present, otherwise use first node id
          const graph = body.graph || {}
          let nid = graph.selected_node_id
          if (!nid && Array.isArray(graph.nodes) && graph.nodes.length > 0) nid = graph.nodes[0].id
          return { ok: false, json: async () => ({ message: 'LLM node missing prompt', node_id: nid }) }
        } catch (e) {
          return { ok: false, json: async () => ({ message: 'Invalid workflow', node_id: null }) }
        }
      }

      // default: harmless success for other endpoints
      return { ok: true, json: async () => ([]) }
    })

    try {
      render(<Editor />)

      // add an LLM node and save the workflow; the fetch stub will inspect the
      // POST body and return a structured validation error referencing the
      // created node id.
      const llmBtn = screen.getByText('Add LLM Node')
      await userEvent.click(llmBtn)

      const saveBtn = screen.getByText('Save')
      await userEvent.click(saveBtn)

      // The editor should show the validation error box with the message
      expect(await screen.findByText('LLM node missing prompt')).toBeInTheDocument()

      // The right panel shows the selected node id (the editor should select the offending node)
      const nodeIdLabel = await screen.findByText(/Node id:/)
      expect(nodeIdLabel).toBeInTheDocument()

      // Find the rendered node label and assert its containing .node-card has the invalid inline style
      const nodeLabel = await screen.findByText('LLM')
      const nodeCard = nodeLabel.closest('.node-card')
      expect(nodeCard).toBeTruthy()
      // style should include the red border applied by NodeRenderer when invalid
      const style = nodeCard.getAttribute('style') || ''
      expect(style.includes('border: 2px solid')).toBe(true)
      expect(style.includes('#ff4d4f') || style.includes('rgb')).toBe(true)

    } finally {
      global.fetch = origFetch
      window.alert = origAlert
    }
  })
})
