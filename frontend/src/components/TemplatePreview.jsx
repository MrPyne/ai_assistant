import React, { useEffect, useRef } from 'react'
import ReactFlow, { ReactFlowProvider } from 'react-flow-renderer'
import NodeRenderer from '../NodeRenderer'

const NODE_TYPES = { default: NodeRenderer, input: NodeRenderer }

export default function TemplatePreview({ graph, height = 160 }) {
  const instRef = useRef(null)

  const nodes = (graph.nodes || []).map(n => ({
    id: String(n.id),
    type: n.type === 'input' ? 'input' : 'default',
    position: n.position || { x: 0, y: 0 },
    data: { label: n.data && n.data.label ? n.data.label : 'Node', config: n.data && n.data.config ? n.data.config : {} },
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

  // Prevent wheel events inside the preview from bubbling up to parent
  // containers (like the TemplatesModal) which can cause the whole
  // modal/sidebar to scroll when the user intends to interact with the
  // embedded ReactFlow preview. We stop propagation here but allow the
  // ReactFlow instance to handle pointer interaction normally.
  return (
    <div
      onWheel={(e) => {
        // stop propagation so the parent modal doesn't scroll while
        // the user is interacting with the flow preview.
        e.stopPropagation()
      }}
      style={{ width: '100%', height, overflow: 'hidden' }}
    >
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
        style={{ width: '100%', height: '100%' }}
      />
    </div>
  )
}
