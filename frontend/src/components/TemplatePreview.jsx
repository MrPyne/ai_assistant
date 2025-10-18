import React, { useEffect, useRef, useMemo } from 'react'
import ReactFlow from 'react-flow-renderer'
import NodeRenderer from '../NodeRenderer'

const NODE_TYPES = { default: NodeRenderer, input: NodeRenderer }

/**
 * TemplatePreview
 * Renders a read-only React Flow preview for a given graph. This component
 * is intentionally lightweight and always renders inline so the preview
 * remains contained inside the calling modal (prevents React Portal escape
 * issues with ReactFlow nodes).
 */
export default function TemplatePreview({ graph = { nodes: [], edges: [] }, height = 160, className = '' }) {
  const instRef = useRef(null)
  const hostRef = useRef(null)

  // Build nodes/edges once per graph using useMemo for stability/performance
  const nodes = useMemo(() => {
    return (graph.nodes || []).map(n => ({
      id: String(n.id),
      type: n.type === 'input' ? 'input' : 'default',
      position: n.position || { x: 0, y: 0 },
      data: {
        ...(n.data || {}),
        label: n.data && n.data.label ? n.data.label : 'Node',
        config: n.data && n.data.config ? n.data.config : {},
        __preview: true,
      },
    }))
  }, [graph.nodes])

  const edges = useMemo(() => {
    return (graph.edges || []).map(e => ({ id: e.id ? String(e.id) : `${e.source}-${e.target}`, source: String(e.source), target: String(e.target) }))
  }, [graph.edges])

  // Compute a lightweight key for the current preview so we only call fitView
  // when the graph content meaningfully changes. This prevents repeated
  // fitView calls (and ReactFlow internal viewport updates) from creating a
  // re-render loop when parents re-render without changing the graph.
  const previewKey = useMemo(() => {
    const nIds = (nodes || []).map(n => n.id).join(',')
    const eIds = (edges || []).map(e => e.id).join(',')
    return `${nIds}|${eIds}`
  }, [nodes, edges])

  // Fit view after mount / graph changes. Use requestAnimationFrame + timeouts
  // to increase likelihood ReactFlow has mounted and layout is stable. Only
  // run the fit when the previewKey changes.
  const lastFitKey = useRef(null)
  useEffect(() => {
    let cancelled = false

    const runFit = () => {
      if (cancelled) return
      try {
        if (!instRef.current || typeof instRef.current.fitView !== 'function') return
        // Only fit when the graph content changed since the last fit
        if (lastFitKey.current === previewKey) return
        instRef.current.fitView({ padding: 0.32 })
        lastFitKey.current = previewKey
      } catch (e) {
        // swallow — preview fit is best-effort
      }
    }

    const rafId = requestAnimationFrame(runFit)
    const t1 = setTimeout(runFit, 60)
    const t2 = setTimeout(runFit, 250)

    return () => {
      cancelled = true
      cancelAnimationFrame(rafId)
      clearTimeout(t1)
      clearTimeout(t2)
    }
  }, [previewKey])

  return (
    <div
      ref={hostRef}
      className={["template-preview", className].filter(Boolean).join(' ')}
      onWheel={(e) => { e.stopPropagation() }}
      style={{ width: '100%', height, overflow: 'visible', position: 'relative' }}
      aria-hidden={true}
    >
      <div style={{ width: '100%', height: '100%', position: 'relative', overflow: 'visible' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onInit={(inst) => { instRef.current = inst }}
          nodesDraggable={false}
          nodesConnectable={false}
          panOnScroll={false}
          zoomOnScroll={false}
          panOnDrag={false}
          elementsSelectable={false}
          fitView={false}
          style={{ width: '100%', height: '100%', position: 'relative', background: 'transparent' }}
        />
      </div>
    </div>
  )
}
