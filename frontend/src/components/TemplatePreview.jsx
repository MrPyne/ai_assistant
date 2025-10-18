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
function TemplatePreview({ graph = { nodes: [], edges: [] }, height = 160, className = '' }) {
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
    // Include node positions in the preview key so visual/layout changes
    // (not just id churn) will trigger a re-fit. Round positions to
    // integers to avoid tiny floating point jitter causing spurious updates.
    const nKeys = (nodes || []).map(n => `${n.id}@${Math.round(n.position.x)}:${Math.round(n.position.y)}`).join(',')
    const eIds = (edges || []).map(e => e.id).join(',')
    return `${nKeys}|${eIds}`
  }, [nodes, edges])

  // Fit view after mount / graph changes. Use requestAnimationFrame + timeouts
  // to increase likelihood ReactFlow has mounted and layout is stable. Only
  // run the fit when the previewKey changes.
  const lastFitKey = useRef(null)
  useEffect(() => {
    let cancelled = false
    // Log when previewKey changes so we can detect frequent refits/remounts
    console.debug('[TemplatePreview] previewKey effect', { previewKey, nodesCount: nodes.length, edgesCount: edges.length })

    const runFit = () => {
      if (cancelled) return
      try {
        if (!instRef.current || typeof instRef.current.fitView !== 'function') return
        // Only fit when the graph content changed since the last fit
        if (lastFitKey.current === previewKey) return
        console.debug('[TemplatePreview] calling fitView', { previewKey, nodesCount: nodes.length, edgesCount: edges.length })
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

  // Log mount / unmount so we can confirm whether the preview is being
  // remounted frequently (which would indicate parent-level keying/unmounting)
  useEffect(() => {
    console.debug('[TemplatePreview] mount', { previewKey, nodesCount: nodes.length, edgesCount: edges.length })
    return () => {
      console.debug('[TemplatePreview] unmount', { previewKey, nodesCount: nodes.length, edgesCount: edges.length })
    }
  }, [])

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

// Wrap the component in React.memo with a custom comparator so parent
// re-renders (filters, search input, etc.) do not cause the preview to
// re-render or re-initialize ReactFlow unless the underlying graph
// content (node/edge ids) or size actually changes. This prevents the
// preview canvas from repeatedly reloading when the templates dialog
// updates frequently.
const arePropsEqual = (prev, next) => {
  if (prev.height !== next.height) return false
  if (prev.className !== next.className) return false

  const prevNodes = (prev.graph && prev.graph.nodes) || []
  const nextNodes = (next.graph && next.graph.nodes) || []
  if (prevNodes.length !== nextNodes.length) return false
  for (let i = 0; i < prevNodes.length; i++) {
    if (String(prevNodes[i].id) !== String(nextNodes[i].id)) return false
  }

  const prevEdges = (prev.graph && prev.graph.edges) || []
  const nextEdges = (next.graph && next.graph.edges) || []
  if (prevEdges.length !== nextEdges.length) return false
  for (let i = 0; i < prevEdges.length; i++) {
    const p = prevEdges[i]
    const n = nextEdges[i]
    const pid = p && (p.id ? String(p.id) : `${p.source}-${p.target}`)
    const nid = n && (n.id ? String(n.id) : `${n.source}-${n.target}`)
    if (pid !== nid) return false
  }

  return true
}

export default React.memo(TemplatePreview, arePropsEqual)
