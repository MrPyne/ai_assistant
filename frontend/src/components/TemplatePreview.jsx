import React, { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import ReactFlow from 'react-flow-renderer'
import NodeRenderer from '../NodeRenderer'

const NODE_TYPES = { default: NodeRenderer, input: NodeRenderer }

export default function TemplatePreview({ graph, height = 160 }) {
  const instRef = useRef(null)
  const hostRef = useRef(null)
  const portalRef = useRef(null)
  const [mountedPortal, setMountedPortal] = useState(false)

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


  // Create a portal element attached to document.body so the ReactFlow
  // canvas can render above the modal and avoid ancestor overflow clipping.
  useEffect(() => {
    if (typeof document === 'undefined') return
    // Decide whether we should render the flow into a body-attached
    // portal (to paint above page content) or inline inside the nearest
    // templates modal. Rendering inline when inside the modal removes
    // the risk of creating a new containing block (fixed positioning
    // inside transformed ancestors) and ensures the preview stays
    // clipped and scrolls with the dialog.
    let createdEl = null
    let mountInline = false
    try {
      if (hostRef.current) {
        const maybeModal = hostRef.current.closest('.templates-modal') || hostRef.current.closest('[role="dialog"]')
        if (maybeModal && maybeModal instanceof HTMLElement) {
          // If we're inside the templates modal, render inline to keep the
          // preview contained and avoid stacking/containing-block issues.
          mountInline = true
        }
      }
    } catch (e) {
      // ignore and fall back to portal
    }

    if (!mountInline) {
      const el = document.createElement('div')
      el.className = 'template-preview-portal'
      el.style.position = 'fixed'
      el.style.top = '0px'
      el.style.left = '0px'
      el.style.width = '100px'
      el.style.height = '100px'
      el.style.overflow = 'visible'
      el.style.pointerEvents = 'auto'
      el.style.transform = 'none'
      el.setAttribute('data-portal-generated', 'true')
      document.body.appendChild(el)
      createdEl = el
      portalRef.current = el
      setMountedPortal(true)
    } else {
      // Ensure portalRef is null to indicate inline rendering path
      portalRef.current = null
      setMountedPortal(false)
    }

    return () => {
      try {
        if (createdEl && createdEl.parentNode) createdEl.parentNode.removeChild(createdEl)
      } catch (e) {}
      portalRef.current = null
      setMountedPortal(false)
    }
  }, [])

  // Keep the portal positioned over the host element (only needed when
  // we're using a body-attached portal). When rendering inline inside the
  // modal this effect is skipped which prevents the preview from "escaping"
  // the dialog during scroll.
  useEffect(() => {
    if (!portalRef.current || !hostRef.current) return
    let raf = 0
    const update = () => {
      try {
        const r = hostRef.current.getBoundingClientRect()
        const el = portalRef.current
        el.style.top = `${r.top}px`
        el.style.left = `${r.left}px`
        el.style.width = `${r.width}px`
        el.style.height = `${r.height}px`
      } catch (e) {}
      raf = requestAnimationFrame(update)
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [mountedPortal])

  // Prevent wheel events inside the preview from bubbling up to parent
  // containers (like the TemplatesModal) which can cause the whole
  // modal/sidebar to scroll when the user intends to interact with the
  // embedded ReactFlow preview. We stop propagation here but allow the
  // ReactFlow instance to handle pointer interaction normally.
  // Host wrapper remains in-flow (keeps layout) but the actual flow canvas
  // is rendered into a body-attached portal so it can appear above the modal.
  return (
    <div
      ref={hostRef}
      onWheel={(e) => { e.stopPropagation() }}
      style={{ width: '100%', height, overflow: 'visible', position: 'relative' }}
    >
      {mountedPortal && portalRef.current ? createPortal(
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
      , portalRef.current) : (
        // Inline render path: render ReactFlow directly inside the host so it
        // stays contained and scrolls with the modal. This avoids portal
        // positioning issues when the modal itself is portaled to body.
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
      )}
    </div>
  )
}
