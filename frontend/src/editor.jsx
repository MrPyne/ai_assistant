import React, { useRef, useState } from 'react'

export default function Editor({ editorDispatch, token }) {
  const logEventSourceRef = useRef(null)
  const [logEventSource, setLogEventSource] = useState(null)

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
        setLogEventSource(null)
      }
      logEventSourceRef.current = es
      setLogEventSource(es)
    } catch (err) {}
  }

  return null
}
