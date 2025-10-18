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
    const el = document.createElement('div')
    // mark portal so we can scope CSS overrides (prevent preview nodes from
    // participating in z-index ordering). We avoid adding any z-index here.
    el.className = 'template-preview-portal'
    // Use fixed positioning for the portal so it reliably paints above
    // other fixed/positioned stacking contexts (modals, overlays, etc.).
    // Absolute positioning combined with scroll offsets was previously
    // used; switching to `fixed` avoids subtle stacking/paint ordering
    // issues on some browsers/containers.
    el.style.position = 'fixed'
    el.style.top = '0px'
    el.style.left = '0px'
    el.style.width = '100px'
    el.style.height = '100px'
    el.style.overflow = 'visible'
    el.style.pointerEvents = 'auto'
    // Avoid assigning z-index here — templates/preview should not compete
    // with dialogs. Dialogs control the stacking order via CSS variables.
    // Previously we set el.style.zIndex to a portal/templates variable; we
    // remove that to ensure previews never outrank modals.
    // try {
    //   const root = getComputedStyle(document.documentElement)
    //   const z = root.getPropertyValue('--z-portal') || root.getPropertyValue('--z-templates-modal') || root.getPropertyValue('--z-templates-overlay')
    //   el.style.zIndex = z ? z.trim() : '9999'
    // } catch (e) {
    // }
    // Avoid accidental transforms creating new stacking contexts
    el.style.transform = 'none'
    // Prevent portal from being trapped in a stacking context created by
    // ancestors. Leave a lightweight diagnostic attribute for devs.
    el.setAttribute('data-portal-generated', 'true')

    // Prefer mounting the portal into the nearest .templates-modal (if
    // present) so the preview becomes part of the modal's content and is
    // not occluded by overlays. Fall back to document.body when no modal
    // ancestor exists.
    let mountRoot = document.body
    try {
      if (hostRef.current) {
        const maybeModal = hostRef.current.closest('.templates-modal') || hostRef.current.closest('[role="dialog"]')
        if (maybeModal && maybeModal instanceof HTMLElement) mountRoot = maybeModal
      }
    } catch (e) {
      // ignore and fallback to body
    }
    mountRoot.appendChild(el)
    portalRef.current = el
    setMountedPortal(true)
    return () => {
      try { if (el.parentNode) el.parentNode.removeChild(el) } catch (e) {}
      portalRef.current = null
      setMountedPortal(false)
    }
  }, [])

  // Keep the portal positioned over the host element
  useEffect(() => {
    if (!portalRef.current || !hostRef.current) return
    let raf = 0
    const update = () => {
      try {
        const r = hostRef.current.getBoundingClientRect()
        const el = portalRef.current
        // portal is fixed to the viewport so use the host's rect (viewport
        // coordinates) directly. Previously we added window.scrollY/X which
        // caused incorrect positioning when the modal or inner scroll
        // containers moved, producing node "leakage" during scroll.
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
      , portalRef.current) : null}
    </div>
  )
}
