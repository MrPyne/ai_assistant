import EmailNode from './nodes/EmailNode'
import SlackNode from './nodes/SlackNode'

// Node UI registry: centralized descriptor for how NodeInspector should render
// each node label. This keeps a single source of truth and makes adding new
// node types simple: add an entry here.
//
// Each entry has shape:
// {
//   kind: 'friendly' | 'dedicated' | 'server',
//   component?: ReactComponent // for 'friendly' UIs implemented in frontend
// }
//
// 'friendly' -> render the provided component (and do not render server schema or raw JSON)
// 'dedicated' -> NodeInspector has a built-in UI for this label (rendered inline in NodeInspector)
// 'server' -> no frontend UI; attempt to render server-provided rjsf form

const NODE_UI_REGISTRY = {
  'Send Email': { kind: 'friendly', component: EmailNode },
  'Slack Message': { kind: 'friendly', component: SlackNode },

  // Labels that NodeInspector handles with inline dedicated UIs
  'LLM': { kind: 'dedicated' },
  'HTTP Request': { kind: 'dedicated' },
  'DB Query': { kind: 'dedicated' },
  'Transform': { kind: 'dedicated' },
  'Wait': { kind: 'dedicated' },
  'Cron Trigger': { kind: 'dedicated' },
  'HTTP Trigger': { kind: 'dedicated' },
  'SplitInBatches': { kind: 'dedicated' },
  'Loop': { kind: 'dedicated' },
  'Parallel': { kind: 'dedicated' },
  'Webhook Trigger': { kind: 'dedicated' },
}

export function getNodeUI(label) {
  if (!label) return null
  return NODE_UI_REGISTRY[label] || null
}

export default NODE_UI_REGISTRY
