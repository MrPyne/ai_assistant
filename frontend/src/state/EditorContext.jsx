import React, { createContext, useContext, useReducer } from 'react'
import { normalizeSelectedRunLogs, appendSelectedRunLog } from './editorUtils'

const EditorStateContext = createContext(null)
const EditorDispatchContext = createContext(null)

const defaultState = {
  workflowName: 'New Workflow',
  autoSaveEnabled: false,
  saveStatus: 'idle',
  lastSavedAt: null,
  // selection model: support multi-select via selectedIds, keep single-item helpers for compatibility
  selectedIds: [],
  selectedNodeId: null,
  selectedEdgeId: null,
  showNodeTest: false,
  nodeTestToken: '',
  showTemplates: false,
  webhookTestPayload: '{}',
  validationError: null,
  selectedRunDetail: null,
  runDetailError: null,
  loadingRunDetail: false,
  runs: [],
  selectedRunLogs: [],
  leftPanelOpen: true,
  rightPanelOpen: true,
  showTemplates: false,
  leftPanelWidth: 300,
  rightPanelWidth: 360,
  activeLeftTab: 'palette',
  activeRightTab: 'inspector',
  isDirty: false,
}

function reducer(state, action) {
  switch (action.type) {
    case 'SET_WORKFLOW_NAME':
      return { ...state, workflowName: action.payload }
    case 'SET_AUTOSAVE_ENABLED':
      return { ...state, autoSaveEnabled: !!action.payload }
    case 'SET_SAVE_STATUS':
      return { ...state, saveStatus: action.payload }
    case 'SET_LAST_SAVED_AT':
      return { ...state, lastSavedAt: action.payload }
    case 'SET_SELECTED_NODE_ID':
      return { ...state, selectedNodeId: action.payload, selectedEdgeId: null, selectedIds: action.payload ? [String(action.payload)] : [] }
    case 'SET_SELECTED_EDGE_ID':
      return { ...state, selectedEdgeId: action.payload, selectedNodeId: null, selectedIds: action.payload ? [String(action.payload)] : [] }
    case 'SET_SELECTION':
      // payload expected to be array of ids
      return { ...state, selectedIds: Array.isArray(action.payload) ? action.payload.map(String) : [], selectedNodeId: (Array.isArray(action.payload) && action.payload.length === 1) ? String(action.payload[0]) : null, selectedEdgeId: null }
    case 'TOGGLE_SELECTION':
      // payload: id to toggle
      const id = String(action.payload)
      const exists = (state.selectedIds || []).includes(id)
      if (exists) {
        const next = (state.selectedIds || []).filter(i => i !== id)
        return { ...state, selectedIds: next, selectedNodeId: next.length === 1 ? next[0] : null }
      }
      return { ...state, selectedIds: [...(state.selectedIds || []), id], selectedNodeId: id }
    case 'CLEAR_SELECTION':
      return { ...state, selectedIds: [], selectedNodeId: null, selectedEdgeId: null }
    case 'SET_SHOW_NODE_TEST':
      return { ...state, showNodeTest: !!action.payload }
    case 'SET_NODE_TEST_TOKEN':
      return { ...state, nodeTestToken: action.payload }
    case 'SET_SHOW_TEMPLATES':
      return { ...state, showTemplates: !!action.payload }
    case 'SET_WEBHOOK_TEST_PAYLOAD':
      return { ...state, webhookTestPayload: action.payload }
    case 'SET_VALIDATION_ERROR':
      return { ...state, validationError: action.payload }
    case 'SET_SELECTED_RUN_DETAIL':
      return { ...state, selectedRunDetail: action.payload }
    case 'SET_RUN_DETAIL_ERROR':
      return { ...state, runDetailError: action.payload }
    case 'SET_LOADING_RUN_DETAIL':
      return { ...state, loadingRunDetail: !!action.payload }
    case 'SET_RUNS':
      return { ...state, runs: action.payload || [] }
    case 'SET_SELECTED_RUN_LOGS':
      return { ...state, selectedRunLogs: normalizeSelectedRunLogs(action.payload) }
    case 'APPEND_SELECTED_RUN_LOG':
      try {
        const appended = appendSelectedRunLog(state.selectedRunLogs, action.payload)
        if (appended === null) return state
        return { ...state, selectedRunLogs: appended }
      } catch (e) {
        return { ...state, selectedRunLogs: (state.selectedRunLogs || []).concat([action.payload]) }
      }
    case 'CLEAR_SELECTED_RUN_LOGS':
      return { ...state, selectedRunLogs: [] }
    case 'SET_LEFT_PANEL_OPEN':
      return { ...state, leftPanelOpen: !!action.payload }
    case 'SET_RIGHT_PANEL_OPEN':
      return { ...state, rightPanelOpen: !!action.payload }
    case 'SET_LEFT_PANEL_WIDTH':
      return { ...state, leftPanelWidth: Number(action.payload) || state.leftPanelWidth }
    case 'SET_RIGHT_PANEL_WIDTH':
      return { ...state, rightPanelWidth: Number(action.payload) || state.rightPanelWidth }
    case 'SET_ACTIVE_LEFT_TAB':
      return { ...state, activeLeftTab: action.payload }
    case 'SET_ACTIVE_RIGHT_TAB':
      return { ...state, activeRightTab: action.payload }
    case 'MARK_DIRTY':
      return { ...state, isDirty: true, saveStatus: 'dirty' }
    case 'MARK_CLEAN':
      return { ...state, isDirty: false }
    case 'RESET':
      return { ...defaultState, ...(action.payload || {}) }
    default:
      return state
  }
}

export function EditorProvider({ children, initialState = {} }) {
  const [state, dispatch] = useReducer(reducer, { ...defaultState, ...(initialState || {}) })
  return (
    <EditorStateContext.Provider value={state}>
      <EditorDispatchContext.Provider value={dispatch}>
        {children}
      </EditorDispatchContext.Provider>
    </EditorStateContext.Provider>
  )
}

export function useEditorState() {
  const ctx = useContext(EditorStateContext)
  if (ctx === null) throw new Error('useEditorState must be used within EditorProvider')
  return ctx
}

export function useEditorDispatch() {
  const ctx = useContext(EditorDispatchContext)
  if (ctx === null) throw new Error('useEditorDispatch must be used within EditorProvider')
  return ctx
}

export function useEditor() {
  return [useEditorState(), useEditorDispatch()]
}

export default EditorStateContext
