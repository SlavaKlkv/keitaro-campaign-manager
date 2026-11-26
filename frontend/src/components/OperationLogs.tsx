import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { OperationLogItem } from "../types";

/** Просмотр журнала операций из PostgreSQL. */
export function OperationLogs() {
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
            История создания кампаний и изменений потоков/офферов.
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
                <th>Описание</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((row) => (
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
                  <td>{row.summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
