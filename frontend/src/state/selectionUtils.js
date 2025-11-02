// Pure helpers for selection-related reducer cases
export function setSelectedNodeId(state, payload) {
  return {
    ...state,
    selectedNodeId: payload,
    selectedEdgeId: null,
    selectedIds: payload ? [String(payload)] : [],
  }
}

export function setSelectedEdgeId(state, payload) {
  return {
    ...state,
    selectedEdgeId: payload,
    selectedNodeId: null,
    selectedIds: payload ? [String(payload)] : [],
  }
}

export function setSelection(state, payload) {
  const selected = Array.isArray(payload) ? payload.map(String) : []
  return {
    ...state,
    selectedIds: selected,
    selectedNodeId: Array.isArray(payload) && payload.length === 1 ? String(payload[0]) : null,
    selectedEdgeId: null,
  }
}

export function toggleSelection(state, payload) {
  const id = String(payload)
  const exists = (state.selectedIds || []).includes(id)
  if (exists) {
    const next = (state.selectedIds || []).filter(i => i !== id)
    return { ...state, selectedIds: next, selectedNodeId: next.length === 1 ? next[0] : null }
  }
  return { ...state, selectedIds: [...(state.selectedIds || []), id], selectedNodeId: id }
}

export function clearSelection(state) {
  return { ...state, selectedIds: [], selectedNodeId: null, selectedEdgeId: null }
}
