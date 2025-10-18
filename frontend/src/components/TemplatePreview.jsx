import React, { useEffect, useRef } from 'react'
import ReactFlow from 'react-flow-renderer'
import NodeRenderer from '../NodeRenderer'

const NODE_TYPES = { default: NodeRenderer, input: NodeRenderer }

export default function TemplatePreview({ graph, height = 160 }) {
  const instRef = useRef(null)
  const hostRef = useRef(null)

  const nodes = (graph.nodes || []).map(n => ({
    id: String(n.id),
    type: n.type === 'input' ? 'input' : 'default',
    position: n.position || { x: 0, y: 0 },
    data: { ...(n.data || {}), label: n.data && n.data.label ? n.data.label : 'Node', config: n.data && n.data.config ? n.data.config : {}, __preview: true },
  }))

  const edges = (graph.edges || []).map(e => ({ id: e.id ? String(e.id) : `${e.source}-${e.target}`, source: String(e.source), target: String(e.target) }))

  useEffect(() => {
    const doFit = () => {
      try {
        if (instRef.current && typeof instRef.current.fitView === 'function') {
          instRef.current.fitView({ padding: 0.32 })
        }
      } catch (e) {
        // ignore
      }
    }
    const rafId = requestAnimationFrame(doFit)
    const t1 = setTimeout(doFit, 60)
    const t2 = setTimeout(doFit, 250)

    return () => {
      cancelAnimationFrame(rafId)
      clearTimeout(t1)
      clearTimeout(t2)
    }
  }, [graph])

  // Render inline always. This keeps the preview contained inside the
  // Templates modal (or wherever the TemplatePreview is used) so it scrolls
  // with the modal and does not escape due to a fixed-position portal.
  // It also avoids crossing stacking-context boundaries which made the
  // preview render underneath the modal in some environments.
  return (
    <div
      ref={hostRef}
      onWheel={(e) => { e.stopPropagation() }}
      style={{ width: '100%', height, overflow: 'visible', position: 'relative' }}
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
          style={{ width: '100%', height: '100%', position: 'relative' }}
        />
      </div>
    </div>
  )
}
