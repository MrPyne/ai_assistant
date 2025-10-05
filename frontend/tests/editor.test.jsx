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
})
