import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type {
  OfferDiffEntry,
  OperationLogItem,
  PendingRollback,
  SnapshotOfferEntry,
} from "../types";

interface OperationLogsProps {
  onRollbackToSnapshot?: (rollback: PendingRollback) => void;
}

function asOfferDiffList(details: Record<string, unknown> | null | undefined): OfferDiffEntry[] {
  if (!details || !Array.isArray(details.diff)) return [];
  return details.diff.filter(
    (item): item is OfferDiffEntry =>
      typeof item === "object" && item !== null && "offer_id" in item && "change" in item
  );
}

function asSnapshotOffers(raw: unknown): SnapshotOfferEntry[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (item): item is SnapshotOfferEntry =>
      typeof item === "object" && item !== null && "offer_id" in item && "share" in item
  );
}

/** Просмотр журнала операций из PostgreSQL с diff «было → стало» и откатом к снимку. */
export function OperationLogs({ onRollbackToSnapshot }: OperationLogsProps) {
  const [logs, setLogs] = useState<OperationLogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listLogs(100);
      setLogs(data);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Не удалось загрузить журнал"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  return (
    <section className="card">
      <div className="section-head">
        <div>
          <p className="eyebrow">PostgreSQL · operation_logs</p>
          <h1>Журнал операций</h1>
          <p className="subtitle">
            История создания кампаний и изменений потоков/офферов с diff «было →
            стало» и откатом в черновик редактора.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => void loadLogs()}
          disabled={loading}
        >
          {loading ? "Загрузка…" : "Обновить"}
        </button>
      </div>

      {error && (
        <div className="alert alert-danger" role="alert">
          {error}
        </div>
      )}

      {logs.length === 0 && !loading ? (
        <p className="empty-state">Записей пока нет.</p>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Время</th>
                <th>Операция</th>
                <th>Ресурс</th>
                <th>Статус</th>
                <th>Описание и diff «было → стало»</th>
                <th>Откат</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((row) => {
                const diffList = asOfferDiffList(row.details);
                const campaignId =
                  typeof row.details?.campaign_id === "number"
                    ? row.details.campaign_id
                    : null;
                const streamId =
                  typeof row.details?.stream_id === "number"
                    ? row.details.stream_id
                    : row.resource_type === "stream"
                      ? row.resource_id
                      : null;
                const beforeOffers = asSnapshotOffers(row.details?.before);
                const afterOffers = asSnapshotOffers(row.details?.after);
                const canRollback =
                  Boolean(onRollbackToSnapshot) &&
                  campaignId !== null &&
                  streamId !== null &&
                  (beforeOffers.length > 0 || afterOffers.length > 0);

                return (
                  <tr key={row.id}>
                    <td className="mono-id">#{row.id}</td>
                    <td className="nowrap muted-cell">
                      {new Date(row.created_at).toLocaleString("ru-RU")}
                    </td>
                    <td>
                      <code>{row.operation}</code>
                    </td>
                    <td className="nowrap">
                      {row.resource_type}
                      {row.resource_id !== null ? ` #${row.resource_id}` : ""}
                    </td>
                    <td>
                      <span
                        className={`status-badge ${
                          row.status === "success"
                            ? "status-success"
                            : "status-danger"
                        }`}
                      >
                        {row.status}
                      </span>
                    </td>
                    <td>
                      <div>{row.summary}</div>
                      {diffList.length > 0 && (
                        <ul className="diff-list">
                          {diffList.map((d) => (
                            <li key={d.offer_id} className={`diff-item diff-${d.change}`}>
                              <span className="mono-id">#{d.offer_id}</span>{" "}
                              <span>{d.name}:</span>{" "}
                              {d.change === "added" && (
                                <span className="status-badge status-success">
                                  + {d.after_share ?? 0}%
                                </span>
                              )}
                              {d.change === "removed" && (
                                <span className="status-badge status-danger">
                                  − {d.before_share ?? 0}% → 0%
                                </span>
                              )}
                              {d.change === "changed" && (
                                <span>
                                  {d.before_share ?? 0}% → <strong>{d.after_share ?? 0}%</strong>
                                </span>
                              )}
                              {d.change === "unchanged" && (
                                <span className="muted-cell">
                                  {d.after_share ?? 0}% (без изм.)
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td className="nowrap">
                      {canRollback && onRollbackToSnapshot ? (
                        <div className="btn-row">
                          {beforeOffers.length > 0 && (
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() =>
                                onRollbackToSnapshot({
                                  logId: row.id,
                                  campaignId: campaignId!,
                                  streamId: streamId!,
                                  label: "было",
                                  offers: beforeOffers,
                                })
                              }
                            >
                              Откатить к «было»
                            </button>
                          )}
                          {afterOffers.length > 0 && (
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() =>
                                onRollbackToSnapshot({
                                  logId: row.id,
                                  campaignId: campaignId!,
                                  streamId: streamId!,
                                  label: "стало",
                                  offers: afterOffers,
                                })
                              }
                            >
                              Снимок «стало»
                            </button>
                          )}
                        </div>
                      ) : (
                        <span className="muted-cell">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
