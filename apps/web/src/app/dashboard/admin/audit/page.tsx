"use client";

/**
 * Admin Audit Log Viewer.
 *
 * Read-only browser for audit.audit_logs. Admin-only (enforced server-side
 * via permission check; client also gates by role for UX).
 *
 * Features:
 * - Filter by actor_id, action, resource_type, resource_id, date range
 * - Paginated (100 per page)
 * - Detail view modal for individual log entries
 * - Stats summary card (events grouped by action/outcome for last 24h)
 */

import { useEffect, useState } from "react";
import {
  ShieldAlert,
  Filter,
  ChevronLeft,
  ChevronRight,
  Search,
  RefreshCw,
  X,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { auditApi } from "@/lib/api/client";
import type {
  AuditLog,
  AuditLogListResponse,
  AuditStatsResponse,
  AuditOutcome,
} from "@/lib/api/types";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn, formatDate } from "@/lib/utils";

const ACTION_CATEGORIES = [
  { value: "", label: "All actions" },
  { value: "login.success", label: "Login success" },
  { value: "login.failed", label: "Login failed" },
  { value: "pii.accessed", label: "PII accessed" },
  { value: "pii.updated", label: "PII updated" },
  { value: "consent.granted", label: "Consent granted" },
  { value: "consent.withdrawn", label: "Consent withdrawn" },
  { value: "dsr.access.requested", label: "DSR: access" },
  { value: "dsr.erasure.requested", label: "DSR: erasure" },
  { value: "dsr.erasure.applied", label: "DSR: erasure applied" },
  { value: "grievance.filed", label: "Grievance filed" },
  { value: "payment.captured", label: "Payment captured" },
  { value: "payment.refunded", label: "Payment refunded" },
  { value: "escrow.released", label: "Escrow released" },
  { value: "security.csrf.violation", label: "CSRF violation" },
  { value: "security.rate_limit.exceeded", label: "Rate limit exceeded" },
  { value: "authz.denied", label: "Permission denied" },
  { value: "role.changed", label: "Role changed" },
];

const OUTCOME_COLORS: Record<AuditOutcome, string> = {
  success: "bg-green-100 text-green-700",
  failure: "bg-amber-100 text-amber-700",
  denied: "bg-red-100 text-red-700",
  error: "bg-red-100 text-red-700",
};

export default function AdminAuditPage() {
  const { user } = useAuthStore();
  const [data, setData] = useState<AuditLogListResponse | null>(null);
  const [stats, setStats] = useState<AuditStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState({
    actor_id: "",
    action: "",
    resource_type: "",
    resource_id: "",
  });
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);

  const limit = 100;

  const isAdmin = user?.role === "admin";

  // Effects run on mount regardless of what render() returned, so the role gate
  // further down does NOT stop them — without these guards every non-admin who
  // lands here fires /audit/logs + /audit/stats, and each 403 writes an
  // `authz.denied` event, polluting the very stats this page displays.
  // NOTE: this is UX hygiene only. `user.role` is hydrated from localStorage,
  // so this page must never be treated as an authz boundary — the server is
  // the only thing enforcing admin access.
  useEffect(() => {
    if (!isAdmin) return;
    void load();
  }, [offset, isAdmin]);

  useEffect(() => {
    if (!isAdmin) return;
    void loadStats();
  }, [isAdmin]);

  async function load() {
    setLoading(true);
    try {
      const d = await auditApi.searchLogs({
        ...Object.fromEntries(
          Object.entries(filters).filter(([, v]) => v.trim() !== ""),
        ),
        limit,
        offset,
      });
      setData(d);
    } catch (err) {
      console.error("Failed to load audit logs:", err);
    } finally {
      setLoading(false);
    }
  }

  async function loadStats() {
    try {
      const s = await auditApi.stats(24);
      setStats(s);
    } catch (err) {
      console.error("Failed to load stats:", err);
    }
  }

  // Gate by role (server also enforces this)
  if (!isAdmin) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-red-700">
              <ShieldAlert className="h-5 w-5" />
              Access Denied
            </CardTitle>
            <CardDescription>
              You need administrator privileges to view audit logs.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-full bg-primary-50 p-2.5">
            <ShieldAlert className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Audit Logs</h1>
            <p className="text-sm text-gray-600">
              Read-only security audit trail. Append-only.
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={() => { void load(); void loadStats(); }}>
          <RefreshCw className="h-4 w-4 mr-1.5" />
          Refresh
        </Button>
      </div>

      {/* Stats summary */}
      {stats && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Last 24 hours</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatBox
                label="Total events"
                value={stats.total_events}
                color="text-gray-900"
              />
              <StatBox
                label="Failed logins"
                value={stats.by_action["login.failed"] ?? 0}
                color="text-amber-700"
              />
              <StatBox
                label="PII accesses"
                value={stats.by_action["pii.accessed"] ?? 0}
                color="text-blue-700"
              />
              <StatBox
                label="Permission denials"
                value={stats.by_action["authz.denied"] ?? 0}
                color="text-red-700"
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Filter className="h-4 w-4" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <input
              type="text"
              placeholder="Actor ID (UUID)"
              value={filters.actor_id}
              onChange={(e) => setFilters({ ...filters, actor_id: e.target.value })}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <select
              value={filters.action}
              onChange={(e) => setFilters({ ...filters, action: e.target.value })}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {ACTION_CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
            <input
              type="text"
              placeholder="Resource type"
              value={filters.resource_type}
              onChange={(e) => setFilters({ ...filters, resource_type: e.target.value })}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <input
              type="text"
              placeholder="Resource ID"
              value={filters.resource_id}
              onChange={(e) => setFilters({ ...filters, resource_id: e.target.value })}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
          <div className="flex justify-end mt-3">
            <Button
              onClick={() => {
                setOffset(0);
                void load();
              }}
            >
              <Search className="h-4 w-4 mr-1.5" />
              Apply filters
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Logs table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center text-gray-500">Loading…</div>
          ) : !data || data.logs.length === 0 ? (
            <div className="p-8 text-center text-gray-500">No audit logs match your filters.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">Time</th>
                    <th className="px-4 py-3 font-medium">Action</th>
                    <th className="px-4 py-3 font-medium">Outcome</th>
                    <th className="px-4 py-3 font-medium">Actor</th>
                    <th className="px-4 py-3 font-medium">Resource</th>
                    <th className="px-4 py-3 font-medium">IP</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {data.logs.map((log) => (
                    <tr
                      key={log.id}
                      onClick={() => setSelectedLog(log)}
                      className="cursor-pointer hover:bg-gray-50"
                    >
                      <td className="px-4 py-2.5 text-gray-600 whitespace-nowrap">
                        {formatDate(log.occurred_at)}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-900">
                        {log.action}
                      </td>
                      <td className="px-4 py-2.5">
                        <span
                          className={cn(
                            "text-[10px] uppercase tracking-wide px-2 py-0.5 rounded",
                            OUTCOME_COLORS[log.outcome],
                          )}
                        >
                          {log.outcome}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-gray-600">
                        {log.actor_id ? (
                          <span className="font-mono text-xs">
                            {log.actor_id.slice(0, 8)}…
                            {log.actor_role && (
                              <span className="ml-1 text-gray-400">({log.actor_role})</span>
                            )}
                          </span>
                        ) : (
                          <span className="text-gray-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-gray-600">
                        {log.resource_type ? (
                          <span className="text-xs">
                            {log.resource_type}
                            {log.resource_id && (
                              <span className="text-gray-400 ml-1">
                                ({log.resource_id.slice(0, 8)}…)
                              </span>
                            )}
                          </span>
                        ) : (
                          <span className="text-gray-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-gray-500 text-xs font-mono">
                        {log.ip_address ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {data && (
        <div className="flex items-center justify-between text-sm text-gray-600">
          <div>
            Showing {offset + 1}-{Math.min(offset + limit, data.total)} of {data.total}
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              <ChevronLeft className="h-4 w-4" />
              Prev
            </Button>
            <Button
              variant="outline"
              disabled={offset + limit >= data.total}
              onClick={() => setOffset(offset + limit)}
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Detail modal */}
      {selectedLog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setSelectedLog(null)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6 border-b border-gray-100 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">Audit log detail</h3>
              <button
                type="button"
                onClick={() => setSelectedLog(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-6 space-y-3 text-sm">
              <DetailRow label="Log ID" value={selectedLog.id} mono />
              <DetailRow label="Action" value={selectedLog.action} mono />
              <DetailRow label="Outcome" value={selectedLog.outcome} />
              <DetailRow
                label="Occurred at"
                value={formatDate(selectedLog.occurred_at)}
              />
              <DetailRow
                label="Actor ID"
                value={selectedLog.actor_id ?? "—"}
                mono
              />
              <DetailRow label="Actor role" value={selectedLog.actor_role ?? "—"} />
              <DetailRow
                label="Resource type"
                value={selectedLog.resource_type ?? "—"}
              />
              <DetailRow
                label="Resource ID"
                value={selectedLog.resource_id ?? "—"}
                mono
              />
              <DetailRow label="IP address" value={selectedLog.ip_address ?? "—"} mono />
              <DetailRow label="Request ID" value={selectedLog.request_id ?? "—"} mono />
              <div>
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">
                  Details (JSONB)
                </div>
                <pre className="bg-gray-50 p-3 rounded-lg text-xs overflow-x-auto">
                  {JSON.stringify(selectedLog.details, null, 2)}
                </pre>
              </div>
              <div>
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">
                  User agent
                </div>
                <div className="text-xs text-gray-600 break-all">
                  {selectedLog.user_agent ?? "—"}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatBox({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="p-3 rounded-lg bg-gray-50">
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className={cn("text-2xl font-bold mt-1", color)}>{value.toLocaleString("en-IN")}</div>
    </div>
  );
}

function DetailRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex gap-4">
      <div className="text-xs text-gray-500 uppercase tracking-wide w-32 flex-shrink-0 pt-0.5">
        {label}
      </div>
      <div className={cn("text-sm text-gray-900 flex-1 break-all", mono && "font-mono")}>
        {value}
      </div>
    </div>
  );
}
