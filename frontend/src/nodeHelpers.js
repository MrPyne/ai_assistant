export function inferKindFromLabel(label, nodeType, id) {
  const rawLabel = (typeof label === 'string' && label.trim()) ? label.trim() : null;
  const l = (rawLabel || (nodeType === 'input' ? 'Webhook Trigger' : null) || nodeType || id || 'Node').toLowerCase();
  let kind = 'generic';
  if (l.includes('webhook')) kind = 'webhook';
  else if (l.includes('http') || l.includes('request')) kind = 'http';
  else if (l.includes('llm') || l.includes('ai') || l.includes('model')) kind = 'llm';
  else if (l.includes('email') || l.includes('send email') || l.includes('send-email')) kind = 'email';
  else if (l.includes('cron') || l.includes('timer')) kind = 'cron';
  else if (l.includes('slack')) kind = 'slack';
  else if (l.includes('db') || l.includes('query')) kind = 'db';
  else if (l.includes('s3') || l.includes('upload')) kind = 's3';
  else if (l.includes('transform') || l.includes('jinja') || l.includes('template')) kind = 'transform';
  else if (l.includes('wait') || l.includes('delay')) kind = 'wait';
  return {
    rawLabel,
    label: rawLabel || (nodeType === 'input' ? 'Webhook Trigger' : null) || nodeType || id || 'Node',
    kind,
    isIf: l === 'if' || l === 'condition',
    isSwitch: l === 'switch'
  };
}

export function resultPreviewFromRuntime(runtime) {
  if (!runtime) return null;
  if (runtime.result) {
    if (typeof runtime.result === 'string') return runtime.result;
    try { return JSON.stringify(runtime.result); } catch (e) { return String(runtime.result); }
  }
  if (runtime.error) return runtime.error.message || (typeof runtime.error === 'string' ? runtime.error : JSON.stringify(runtime.error));
  if (runtime.message) return runtime.message;
  return null;
}

export function truncated(s, n = 100) {
  return (typeof s === 'string' && s.length > n) ? s.slice(0, n - 1) + '...' : s;
}
