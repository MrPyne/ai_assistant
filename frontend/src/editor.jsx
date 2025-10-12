import React, { useRef, useEffect } from 'react'
import { useEditorDispatch } from './state/EditorContext'

export default function Editor({ token }) {
  const logEventSourceRef = useRef(null)
  const editorDispatch = useEditorDispatch()

  // keep EventSource behavior but use EditorContext dispatch directly
  const viewRunLogs = async (runId) => {
    try {
      const url = token ? `/api/runs/${runId}/stream?access_token=${token}` : `/api/runs/${runId}/stream`
      const es = new EventSource(url)
      es.onmessage = (e) => {
        try {
          const payload = JSON.parse(e.data)
          editorDispatch({ type: 'APPEND_SELECTED_RUN_LOG', payload })
        } catch (err) {}
      }
      es.onerror = (err) => {
        try { es.close() } catch (e) {}
        logEventSourceRef.current = null
      }
      logEventSourceRef.current = es
    } catch (err) {}
  }

  // expose viewRunLogs globally for callers that previously invoked editor.viewRunLogs
  useEffect(() => {
    window.__editor_viewRunLogs = viewRunLogs
    return () => { delete window.__editor_viewRunLogs }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return null
}
