import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, AuditLogPage } from "../../api/client";

const PAGE_SIZE = 20;

export function AdminAuditLog() {
  const [page, setPage] = useState(1);
  const auditLog = useQuery({
    queryKey: ["admin", "audit-log", page],
    queryFn: () => api<AuditLogPage>(`/admin/audit-log?page=${page}&page_size=${PAGE_SIZE}`),
  });
  const totalPages = auditLog.data
    ? Math.max(1, Math.ceil(auditLog.data.total / auditLog.data.page_size))
    : 1;

  return (
    <div className="admin-audit-log">
      {auditLog.isLoading && <p role="status">Loading audit log…</p>}
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Actor</th>
            <th>Action</th>
            <th>Entity</th>
          </tr>
        </thead>
        <tbody>
          {auditLog.data?.items.map((entry) => (
            <tr key={entry.id}>
              <td>{new Date(entry.created_at).toLocaleString()}</td>
              <td>{entry.actor_name}</td>
              <td>{entry.action}</td>
              <td>{entry.entity_type} · {entry.entity_id}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="admin-pagination">
        <button disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>
          Previous
        </button>
        <span>Page {page} of {totalPages}</span>
        <button disabled={page >= totalPages} onClick={() => setPage((current) => current + 1)}>
          Next
        </button>
      </div>
    </div>
  );
}
