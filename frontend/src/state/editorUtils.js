// Helper utilities extracted from EditorContext reducer to keep concerns separated.

export function normalizeSelectedRunLogs(incomingPayload) {
  try {
    const incoming = Array.isArray(incomingPayload) ? incomingPayload : []
    const keyOf = (obj) => {
      try {
        return `${obj && obj.type ? obj.type : ''}|${obj && obj.run_id ? String(obj.run_id) : ''}|${obj && obj.node_id ? String(obj.node_id) : ''}|${obj && obj.timestamp ? String(obj.timestamp) : ''}|${obj && obj.level ? String(obj.level) : ''}|${obj && obj.message ? String(obj.message) : ''}`
      } catch (e) {
        try {
          return JSON.stringify(obj)
        } catch (e2) {
          return String(obj)
        }
      }
    }

    const seenIds = new Set()
    const seenKeys = new Set()
    const out = []
    for (const it of incoming) {
      if (it && (it.id !== undefined && it.id !== null)) {
        const sid = String(it.id)
        if (seenIds.has(sid)) continue
        seenIds.add(sid)
        out.push(it)
      } else {
        const k = keyOf(it)
        if (seenKeys.has(k)) continue
        seenKeys.add(k)
        out.push(it)
      }
    }
    return out
  } catch (e) {
    return Array.isArray(incomingPayload) ? incomingPayload : []
  }
}

export function appendSelectedRunLog(existing, incoming) {
  try {
    const existingArr = existing || []
    const keyOf = (obj) => {
      try {
        return `${obj && obj.type ? obj.type : ''}|${obj && obj.run_id ? String(obj.run_id) : ''}|${obj && obj.node_id ? String(obj.node_id) : ''}|${obj && obj.timestamp ? String(obj.timestamp) : ''}|${obj && obj.level ? String(obj.level) : ''}|${obj && obj.message ? String(obj.message) : ''}`
      } catch (e) {
        try {
          return JSON.stringify(obj)
        } catch (e2) {
          return String(obj)
        }
      }
    }

    if (incoming && (incoming.id !== undefined && incoming.id !== null)) {
      const found = existingArr.find((l) => (l && l.id !== undefined && l.id !== null) && String(l.id) === String(incoming.id))
      if (found) return null
      return existingArr.concat([incoming])
    }

    const incomingKey = keyOf(incoming)
    const dup = existingArr.find((l) => {
      try {
        return keyOf(l) === incomingKey
      } catch (e) {
        return false
      }
    })
    if (dup) return null
    return existingArr.concat([incoming])
  } catch (e) {
    return (existing || []).concat([incoming])
  }
}
