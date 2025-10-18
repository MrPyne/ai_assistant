import React, { useEffect, useRef, useMemo } from 'react'
import ReactFlow from 'react-flow-renderer'
import NodeRenderer from '../NodeRenderer'

const NODE_TYPES = { default: NodeRenderer, input: NodeRenderer }

function roundPos(pos) {
  return { x: Math.round((pos && pos.x) || 0), y: Math.round((pos && pos.y) || 0) }
}

/**
 * StaticPreview
 * Lightweight SVG-based thumbnail used for small inline previews to avoid
 * mounting a full ReactFlow instance (which has previously caused mount/
 * unmount and fitView thrash in the templates list). The SVG mirrors the
 * node/edge positions at reduced fidelity solely for a stable visual.
 */
function StaticPreview({ nodes = [], edges = [], width = 300, height = 140 }) {
  // Simple node size used for layout calculations
  const NODE_W = 120
  const NODE_H = 36
  const PADDING = 8

  // Determine bounds of nodes
  const bounds = useMemo(() => {
    if (!nodes.length) return { minX: 0, minY: 0, maxX: NODE_W, maxY: NODE_H }
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const n of nodes) {
      const p = n.position || { x: 0, y: 0 }
      minX = Math.min(minX, p.x)
      minY = Math.min(minY, p.y)
      maxX = Math.max(maxX, p.x + NODE_W)
      maxY = Math.max(maxY, p.y + NODE_H)
    }
    if (!isFinite(minX)) return { minX: 0, minY: 0, maxX: NODE_W, maxY: NODE_H }
    return { minX, minY, maxX, maxY }
  }, [nodes])

  const view = useMemo(() => {
    const contentW = Math.max(1, bounds.maxX - bounds.minX)
    const contentH = Math.max(1, bounds.maxY - bounds.minY)
    const scaleX = (width - PADDING * 2) / contentW
    const scaleY = (height - PADDING * 2) / contentH
    const scale = Math.min(scaleX, scaleY)
    const offsetX = -bounds.minX * scale + PADDING + (width - PADDING * 2 - contentW * scale) / 2
    const offsetY = -bounds.minY * scale + PADDING + (height - PADDING * 2 - contentH * scale) / 2
    return { scale, offsetX, offsetY }
  }, [bounds, width, height])

  // Project a layout position into SVG coords
  const project = (p) => ({ x: Math.round((p.x || 0) * view.scale + view.offsetX), y: Math.round((p.y || 0) * view.scale + view.offsetY) })

  return (
    <svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" role="img" aria-hidden>
      <defs>
        <filter id="shadow" x="-50%" y="-50%" width="200%" height="200%">
          <feDropShadow dx="0" dy="1" stdDeviation="1" floodColor="#000" floodOpacity="0.12" />
        </filter>
      </defs>

      {/* edges */}
      {edges.map(e => {
        const s = nodes.find(n => String(n.id) === String(e.source))
        const t = nodes.find(n => String(n.id) === String(e.target))
        if (!s || !t) return null
        const ps = project(s.position || { x: 0, y: 0 })
        const pt = project(t.position || { x: 0, y: 0 })
        const x1 = ps.x + Math.round((NODE_W * view.scale) / 2)
        const y1 = ps.y + Math.round((NODE_H * view.scale) / 2)
        const x2 = pt.x + Math.round((NODE_W * view.scale) / 2)
        const y2 = pt.y + Math.round((NODE_H * view.scale) / 2)
        return (
          <g key={e.id || `${e.source}-${e.target}`} fill="none" stroke="var(--muted)" strokeWidth={1.5} strokeOpacity={0.6}>
            <path d={`M ${x1} ${y1} L ${x2} ${y2}`} strokeLinecap="round" strokeLinejoin="round" />
            <circle cx={x2} cy={y2} r={2} fill="var(--muted)" />
          </g>
        )
      })}

      {/* nodes */}
      {nodes.map(n => {
        const p = project(n.position || { x: 0, y: 0 })
        const w = Math.round(NODE_W * view.scale)
        const h = Math.round(NODE_H * view.scale)
        const rx = Math.max(3, Math.round(6 * view.scale))
        const label = (n.data && n.data.label) || 'Node'
        return (
          <g key={n.id} transform={`translate(${p.x}, ${p.y})`}>
            <rect x={0} y={0} width={w} height={h} rx={rx} fill="var(--panel)" stroke="var(--muted)" strokeWidth={1} filter="url(#shadow)" />
            <text x={Math.round(w / 2)} y={Math.round(h / 2 + 4)} fontSize={Math.max(8, Math.round(12 * view.scale))} fill="var(--text)" textAnchor="middle">{label}</text>
          </g>
        )
      })}
    </svg>
  )
}

/**
 * TemplatePreview
 * For small inline previews we now render a static SVG thumbnail to avoid
 * repeatedly mounting ReactFlow. For larger previews (overlay) we keep the
 * interactive ReactFlow instance for fidelity.
 */
function TemplatePreview({ graph = { nodes: [], edges: [] }, height = 160, className = '' }) {
  const instRef = useRef(null)

  // Fingerprint the graph content (ids + rounded node positions + type)
  const graphFingerprint = useMemo(() => {
    const nPart = (graph.nodes || []).map(n => {
      const pos = n.position || { x: 0, y: 0 }
      const r = roundPos(pos)
      return `${n.id}@${r.x}:${r.y}:${n.type || 'default'}`
    }).join(',')
    const ePart = (graph.edges || []).map(e => (e.id ? String(e.id) : `${e.source}-${e.target}`)).join(',')
    return `${nPart}|${ePart}`
  }, [graph])

  // Build nodes/edges once per graphFingerprint
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
  }, [graphFingerprint])

  const edges = useMemo(() => {
    return (graph.edges || []).map(e => ({ id: e.id ? String(e.id) : `${e.source}-${e.target}`, source: String(e.source), target: String(e.target) }))
  }, [graphFingerprint])

  // If the preview is small, render a static SVG thumbnail to avoid mounting
  // ReactFlow which previously caused fitView / viewport churn.
  const USE_STATIC_THRESHOLD = 180
  const shouldUseStatic = height <= USE_STATIC_THRESHOLD

  // Keep logs for diagnostics
  useEffect(() => {
    console.debug('[TemplatePreview] mount', { graphFingerprint, nodesCount: nodes.length, edgesCount: edges.length, height })
    return () => console.debug('[TemplatePreview] unmount', { graphFingerprint, nodesCount: nodes.length, edgesCount: edges.length, height })
  }, [graphFingerprint, height])

  if (shouldUseStatic) {
    return (
      <div className={["template-preview", className].filter(Boolean).join(' ')} style={{ width: '100%', height, overflow: 'hidden' }} aria-hidden={true}>
        <StaticPreview nodes={nodes} edges={edges} width={340} height={height - 8} />
      </div>
    )
  }

  // --- large preview path (keeps ReactFlow) ---
  // Fit view after mount / graph changes. Only run when graphFingerprint changes.
  const lastFitKey = useRef(null)
  const lastFitAt = useRef(0)
  const fitCalls = useRef(0)
  useEffect(() => {
    let cancelled = false
    console.debug('[TemplatePreview] previewKey effect', { graphFingerprint, nodesCount: nodes.length, edgesCount: edges.length })

    const runFit = () => {
      if (cancelled) return
      try {
        if (!instRef.current || typeof instRef.current.fitView !== 'function') return
        const now = Date.now()
        if (lastFitKey.current === graphFingerprint) return
        if (now - lastFitAt.current < 500) {
          if (fitCalls.current >= 3) return
        }
        console.debug('[TemplatePreview] calling fitView', { graphFingerprint, nodesCount: nodes.length, edgesCount: edges.length })
        instRef.current.fitView({ padding: 0.32 })
        lastFitKey.current = graphFingerprint
        lastFitAt.current = now
        fitCalls.current += 1
      } catch (e) {}
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
  }, [graphFingerprint])

  return (
    <div className={["template-preview", className].filter(Boolean).join(' ')} onWheel={(e) => { e.stopPropagation() }} style={{ width: '100%', height, overflow: 'visible', position: 'relative' }} aria-hidden={true}>
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

const arePropsEqual = (prev, next) => {
  if (prev.height !== next.height) return false
  if (prev.className !== next.className) return false

  const prevNodes = (prev.graph && prev.graph.nodes) || []
  const nextNodes = (next.graph && next.graph.nodes) || []
  if (prevNodes.length !== nextNodes.length) return false
  for (let i = 0; i < prevNodes.length; i++) {
    const pa = prevNodes[i]
    const na = nextNodes[i]
    if (String(pa.id) !== String(na.id)) return false
    const rp = roundPos(pa.position || { x: 0, y: 0 })
    const rn = roundPos(na.position || { x: 0, y: 0 })
    if (rp.x !== rn.x || rp.y !== rn.y) return false
    if ((pa.type || 'default') !== (na.type || 'default')) return false
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
