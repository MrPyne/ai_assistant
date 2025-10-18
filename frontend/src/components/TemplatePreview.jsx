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
    // Force-create a body-attached portal so the preview can be painted
    // above modal overlays for immediate QA. This bypasses the inline
    // rendering path which can leave the preview behind due to ancestor
    // stacking contexts. This is a temporary, force override for testing.
    let createdEl = null
    try {
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
      // Force an inline-important z-index to overcome stubborn stacking issues
      // Use the max signed 32-bit int which browsers accept as a large value
      el.style.setProperty('z-index', '2147483647', 'important')
      // Ensure the portal forms its own stacking context so it can paint above
      // other contexts where possible.
      el.style.isolation = 'isolate'
      el.setAttribute('data-portal-generated', 'true')
      document.body.appendChild(el)
      // Ensure the portal is the last child so it paints after other overlays
      try { document.body.appendChild(el) } catch (e) {}
      createdEl = el
      portalRef.current = el
      setMountedPortal(true)
      // Observe body mutations and keep the portal as the last child — this
      // helps when other code portals overlays to body after we mount.
      const mo = new MutationObserver(() => {
        try {
          if (portalRef.current && document.body.lastElementChild !== portalRef.current) {
            document.body.appendChild(portalRef.current)
          }
        } catch (e) {}
      })
      mo.observe(document.body, { childList: true })
      // attach observer so we can disconnect it on cleanup
      createdEl.__mo = mo
    } catch (e) {
      // fallback: leave portalRef null so inline rendering can be used
      portalRef.current = null
      setMountedPortal(false)
    }

    // Diagnostic logging to help identify why the portal could be occluded
    try {
      const p = portalRef.current
      if (p) {
        // small delay so styles from CSS files have applied
        setTimeout(() => {
          try {
            const portalStyle = window.getComputedStyle(p)
            const overlay = document.querySelector('.templates-overlay')
            const overlayStyle = overlay ? window.getComputedStyle(overlay) : null
            console.warn('[TemplatePreview] portal mounted', { portalParent: p.parentElement, portalZ: portalStyle.zIndex, overlayZ: overlayStyle && overlayStyle.zIndex })
            console.warn('[TemplatePreview] portal computed styles', portalStyle)
            if (overlay) console.warn('[TemplatePreview] templates overlay computed styles', overlayStyle)
            if (window.__logStackingContexts) {
              try { window.__logStackingContexts(p) } catch (e) {}
              try { if (overlay) window.__logStackingContexts(overlay) } catch (e) {}
            }
          } catch (e) {}
        }, 50)
      }
    } catch (e) {}

    return () => {
      try {
        if (createdEl) {
          try { if (createdEl.__mo) createdEl.__mo.disconnect() } catch (e) {}
          if (createdEl.parentNode) createdEl.parentNode.removeChild(createdEl)
        }
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
