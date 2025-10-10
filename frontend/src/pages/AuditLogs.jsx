import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';

export default function AuditLogs() {
  const { token } = useAuth();
  const [items, setItems] = useState([]);
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [action, setAction] = useState('');
  const [objectType, setObjectType] = useState('');
  const [userId, setUserId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => {
    if (token) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, limit, offset, action, objectType]);

  const authHeaders = () => ({ 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) });

  const load = async () => {
    try {
      const params = new URLSearchParams();
      params.set('limit', String(limit));
      params.set('offset', String(offset));
      if (action) params.set('action', action);
      if (objectType) params.set('object_type', objectType);
      if (userId) params.set('user_id', userId);
      if (dateFrom) params.set('date_from', dateFrom);
      if (dateTo) params.set('date_to', dateTo);
      const resp = await fetch('/api/audit_logs?' + params.toString(), { headers: authHeaders() });
      if (resp.ok) {
        const data = await resp.json();
        setItems(data.items || []);
        setTotal(data.total || 0);
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('Failed to load audit logs', err);
    }
  };

  const exportCsv = async () => {
    try {
      const params = new URLSearchParams();
      if (action) params.set('action', action);
      if (objectType) params.set('object_type', objectType);
      if (userId) params.set('user_id', userId);
      if (dateFrom) params.set('date_from', dateFrom);
      if (dateTo) params.set('date_to', dateTo);
      const resp = await fetch('/api/audit_logs/export?' + params.toString(), { headers: authHeaders() });
      if (resp.ok) {
        const text = await resp.text();
        const blob = new Blob([text], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'audit_logs.csv';
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('Export failed', err);
    }
  };

  const prev = () => { setOffset(Math.max(0, offset - limit)); };
  const next = () => { if (offset + limit < total) setOffset(offset + limit); };

  return (
    <div style={{ padding: 12 }}>
      <h2>Audit Logs</h2>
      <div style={{ marginBottom: 8 }}>
        <input placeholder="Action" value={action} onChange={(e) => setAction(e.target.value)} style={{ marginRight: 6 }} />
        <input placeholder="Object type" value={objectType} onChange={(e) => setObjectType(e.target.value)} style={{ marginRight: 6 }} />
        <input placeholder="User id" value={userId} onChange={(e) => setUserId(e.target.value)} style={{ marginRight: 6, width: 100 }} />
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} style={{ marginRight: 6 }} />
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} style={{ marginRight: 6 }} />
        <button onClick={() => { setOffset(0); load(); }}>Filter</button>
        <button onClick={exportCsv} style={{ marginLeft: 8 }}>Export CSV</button>
      </div>
      <div style={{ marginBottom: 8 }}>
        <button onClick={prev} disabled={offset === 0}>Prev</button>
        <span style={{ margin: '0 8px' }}>Page {Math.floor(offset / limit) + 1} of {Math.max(1, Math.ceil(total / limit))} (total {total})</span>
        <button onClick={next} disabled={offset + limit >= total}>Next</button>
      </div>
      <div>
        {items.length === 0 ? (
          <div className="muted">No entries</div>
        ) : (
          items.map((r) => (
            <div key={r.id} style={{ padding: 8, borderBottom: '1px solid #eee' }}>
              <div><strong>{r.action}</strong> <span className="muted">{r.object_type} {r.object_id ? `#{r.object_id}` : ''}</span></div>
              <div className="muted">user: {r.user_id} workspace: {r.workspace_id} at: {r.timestamp}</div>
              {r.detail ? <div style={{ marginTop: 6 }}>{r.detail}</div> : null}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
