import React, { createContext, useContext, useReducer } from 'react'

const EditorStateContext = createContext(null)
const EditorDispatchContext = createContext(null)

const defaultState = {
  workflowName: 'New Workflow',
  autoSaveEnabled: false,
  saveStatus: 'idle',
  lastSavedAt: null,
  selectedNodeId: null,
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
      return { ...state, selectedNodeId: action.payload }
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
