import { useCallback, useRef } from 'react'

export default function useRuns({ workflowId, token, setNodes, editorDispatch, saveWorkflow }) {
  const esRef = useRef(null)
  const runIdRef = useRef(null)

  const loadRuns = useCallback(async () => {
    try {
      const url = workflowId ? `/api/runs?workflow_id=${workflowId}` : '/api/runs'
      const headers = {}
      if (token) headers.Authorization = `Bearer ${token}`
      const resp = await fetch(url, { headers })
      if (!resp.ok) return
      const data = await resp.json()
      const items = data && Array.isArray(data.items) ? data.items : (Array.isArray(data) ? data : (data && Array.isArray(data.items) ? data.items : []))
      editorDispatch({ type: 'SET_RUNS', payload: items })
    } catch (e) {
      // ignore
    }
  }, [workflowId, token, editorDispatch])

  const openRunEventSource = useCallback(async (runId) => {
    try {
      if (esRef.current && typeof esRef.current.close === 'function') {
        try { esRef.current.close() } catch (e) {}
      }

      let ESImpl = window.EventSource
      if (token) {
        try {
          const mod = await import('event-source-polyfill')
          ESImpl = mod && (mod.EventSourcePolyfill || mod.default || mod)
        } catch (e) {
          ESImpl = window.EventSource
        }
      }

      const es = (ESImpl === window.EventSource)
        ? new ESImpl(`/api/runs/${runId}/stream`)
        : new ESImpl(`/api/runs/${runId}/stream`, { headers: { Authorization: `Bearer ${token}` } })

      try { runIdRef.current = runId } catch (e) {}

      es.addEventListener('log', (ev) => {
        try {
          const msg = typeof ev.data === 'string' ? JSON.parse(ev.data) : ev.data
          editorDispatch({ type: 'APPEND_SELECTED_RUN_LOG', payload: msg })
        } catch (e) {}
      })

      es.addEventListener('node', (ev) => {
        try {
          const payload = typeof ev.data === 'string' ? JSON.parse(ev.data) : ev.data
          editorDispatch({ type: 'APPEND_SELECTED_RUN_LOG', payload })
          try {
            const currentRun = runIdRef.current
            if (payload && currentRun && String(payload.run_id) === String(currentRun) && (payload.status === 'started' || payload.status === 'success' || payload.status === 'failed')) {
              editorDispatch({ type: 'SET_RIGHT_PANEL_OPEN', payload: true })
              editorDispatch({ type: 'SET_ACTIVE_RIGHT_TAB', payload: 'runs' })
            }
          } catch (e) {}
          try {
            const nid = payload && payload.node_id ? String(payload.node_id) : null
            if (nid) {
              setNodes((prev) => {
                return prev.map((n) => {
                  if (String(n.id) !== String(nid)) return n
                  const existingData = n.data || {}
                  return { ...n, data: { ...existingData, runtime: payload } }
                })
              })
            }
          } catch (e) {
            // ignore node update errors
          }
        } catch (e) {}
      })

      es.addEventListener('status', (ev) => {
        try {
          const payload = typeof ev.data === 'string' ? JSON.parse(ev.data) : ev.data
          editorDispatch({ type: 'APPEND_SELECTED_RUN_LOG', payload })
          try { loadRuns() } catch (e) {}
        } catch (e) {}
        try { es.close() } catch (e) {}
      })

      es.onerror = () => {
        // ignore for tests
      }
      esRef.current = es
      const origClose = es.close && es.close.bind(es)
      es.close = () => {
        try { runIdRef.current = null } catch (e) {}
        try { if (origClose) origClose() } catch (e) {}
      }
      return es
    } catch (e) {
      return null
    }
  }, [token, editorDispatch, setNodes, loadRuns])

  const runWorkflow = useCallback(async () => {
    try {
      let wid = workflowId
      if (!wid) {
        const saved = await saveWorkflow({ silent: true })
        wid = saved && saved.id
        if (!wid) return
      }
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`
      const resp = await fetch(`/api/workflows/${wid}/run`, { method: 'POST', headers, body: JSON.stringify({}) })
      if (!resp.ok) return
      const data = await resp.json()
      const runId = data && data.run_id
      await loadRuns()
      if (runId) {
        try { editorDispatch({ type: 'CLEAR_SELECTED_RUN_LOGS' }) } catch (e) {}
        const headers2 = {}
        if (token) headers2.Authorization = `Bearer ${token}`
        const rresp = await fetch(`/api/runs/${runId}/logs`, { headers: headers2 })
        if (rresp && rresp.ok) {
          const rd = await rresp.json()
          const logs = rd && Array.isArray(rd.logs) ? rd.logs : []
          editorDispatch({ type: 'SET_SELECTED_RUN_LOGS', payload: logs })
        }
        openRunEventSource(runId)
      }
      alert('Run queued')
    } catch (e) {
      // ignore
    }
  }, [workflowId, token, saveWorkflow, loadRuns, editorDispatch, openRunEventSource])

  const viewRunLogs = useCallback(async (runId) => {
    try {
      if (!runId) return
      if (esRef.current && typeof esRef.current.close === 'function') {
        try { esRef.current.close() } catch (e) {}
      }
      try { editorDispatch({ type: 'CLEAR_SELECTED_RUN_LOGS' }) } catch (e) {}
      const headers = {}
      if (token) headers.Authorization = `Bearer ${token}`
      const rresp = await fetch(`/api/runs/${runId}/logs`, { headers })
      if (rresp && rresp.ok) {
        const rd = await rresp.json()
        const logs = rd && Array.isArray(rd.logs) ? rd.logs : []
        editorDispatch({ type: 'SET_SELECTED_RUN_LOGS', payload: logs })
      }
      openRunEventSource(runId)
    } catch (e) {
      // ignore
    }
  }, [token, editorDispatch, openRunEventSource])

  return { loadRuns, openRunEventSource, runWorkflow, viewRunLogs }
}
