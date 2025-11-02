import { useCallback, useEffect, useRef, useState } from 'react'
import { applyNodeChanges, applyEdgeChanges, addEdge } from 'react-flow-renderer'

// Hook to encapsulate node/edge state and common helpers used by the editor.
// Keeps behavior identical to the inline implementation but reduces Editor.jsx
// size so the editor responsibilities are clearer.
export default function useNodes({ editorDispatch } = {}) {
  const [nodes, setNodes] = useState([])
  const [edges, setEdges] = useState([])
  const nodesRef = useRef(nodes)

  useEffect(() => {
    nodesRef.current = nodes
  }, [nodes])

  const setNodesSafe = useCallback((next) => {
    setNodes(next)
  }, [])

  const updateNodeConfig = useCallback((id, cb) => {
    setNodes((prev) => {
      const copy = prev.map(n => {
        if (n.id !== id) return n
        const existing = (n.data && n.data.config) || {}
        let delta = {}
        try {
          if (typeof cb === 'function') {
            delta = cb(existing) || {}
          } else if (cb && typeof cb === 'object') {
            delta = cb
          } else {
            delta = {}
          }
        } catch (e) {
          delta = {}
        }
        return { ...n, data: { ...n.data, config: { ...existing, ...delta } } }
      })
      return copy
    })
    try {
      if (editorDispatch) editorDispatch({ type: 'MARK_DIRTY' })
    } catch (e) {}
  }, [editorDispatch])

  const onNodesChange = useCallback((changes) => {
    setNodes((nds) => applyNodeChanges(changes, nds))
    try { if (editorDispatch) editorDispatch({ type: 'MARK_DIRTY' }) } catch (e) {}
  }, [editorDispatch])

  const onEdgesChange = useCallback((changes) => {
    setEdges((eds) => applyEdgeChanges(changes, eds))
    try { if (editorDispatch) editorDispatch({ type: 'MARK_DIRTY' }) } catch (e) {}
  }, [editorDispatch])

  const onConnect = useCallback((connection) => {
    setEdges((eds) => addEdge(connection, eds))
    try { if (editorDispatch) editorDispatch({ type: 'MARK_DIRTY' }) } catch (e) {}
  }, [editorDispatch])

  // generic helper to add a node
  const addNode = useCallback((label, type = 'default', config = {}) => {
    const id = `n-${Date.now().toString(36)}-${Math.floor(Math.random() * 1000)}`
    const node = { id: String(id), type, data: { label, config }, position: { x: 0, y: 0 } }
    setNodes((s) => { const next = s.concat([node]); return next })
    // update editor selection to newly added node
    setTimeout(() => {
      try { if (editorDispatch) editorDispatch({ type: 'SET_SELECTED_NODE_ID', payload: String(id) }) } catch (e) {}
    }, 0)
  }, [editorDispatch])

  const nodeOptions = useCallback((excludeId) => {
    try {
      return nodes
        .filter(n => String(n.id) !== String(excludeId))
        .map(n => ({ id: String(n.id), label: (n.data && n.data.label) || String(n.id) }))
    } catch (e) {
      return []
    }
  }, [nodes])

  const deleteSelected = useCallback((sel, editorDispatchLocal) => {
    try {
      const selArr = sel || []
      if (!selArr.length) return
      // remove nodes with ids in sel
      setNodes((prev) => prev.filter(n => !selArr.includes(String(n.id))))
      // remove edges that reference deleted nodes OR that are individually selected
      setEdges((prev) => prev.filter(e => !selArr.includes(String(e.source)) && !selArr.includes(String(e.target)) && !selArr.includes(String(e.id))))
      try { if (editorDispatchLocal) editorDispatchLocal({ type: 'CLEAR_SELECTION' }) } catch (e) {}
      try { if (editorDispatchLocal) editorDispatchLocal({ type: 'MARK_DIRTY' }) } catch (e) {}
    } catch (e) {
      // ignore
    }
  }, [])

  return {
    nodes,
    edges,
    setNodes,
    setEdges,
    nodesRef,
    setNodesSafe,
    addNode,
    onNodesChange,
    onEdgesChange,
    onConnect,
    updateNodeConfig,
    nodeOptions,
    deleteSelected,
  }
}
