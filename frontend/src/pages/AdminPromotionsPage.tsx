import { type FormEvent, useEffect, useMemo, useState } from "react";
import { apiFetch, ApiError } from "../api/client";
import type {
  Promotion,
  PromotionDraft,
  PromotionListResponse,
} from "../api/types";
import { useAuth } from "../context/useAuth";
import { toPromotionWrite } from "./promotionForm";

function initialDraft(): PromotionDraft {
  const start = new Date();
  const end = new Date(start.getTime() + 7 * 24 * 60 * 60 * 1000);
  return {
    promotionId: "",
    name: "",
    discountPercent: "10.00",
    scope: "PRODUCT",
    productIdsText: "",
    category: "",
    startsAt: start.toISOString().slice(0, 16),
    endsAt: end.toISOString().slice(0, 16),
    enabled: true,
  };
}

function editableDate(value: string): string {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

export function AdminPromotionsPage() {
  const token = useAuth().user?.access_token;
  const [promotions, setPromotions] = useState<Promotion[] | null>(null);
  const [draft, setDraft] = useState<PromotionDraft>(initialDraft);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reload(): void {
    if (!token) return;
    void apiFetch<PromotionListResponse>(token, "/v1/promotions")
      .then((data) => setPromotions(data.promotions))
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : String(err)));
  }

  useEffect(reload, [token]);

  const counts = useMemo(() => ({
    active: promotions?.filter((promotion) => promotion.lifecycleState === "ACTIVE").length ?? 0,
    scheduled: promotions?.filter((promotion) => promotion.lifecycleState === "SCHEDULED").length ?? 0,
    disabled: promotions?.filter((promotion) => !promotion.enabled).length ?? 0,
  }), [promotions]);

  function startEdit(promotion: Promotion): void {
    setEditingId(promotion.promotionId);
    setDraft({
      promotionId: promotion.promotionId,
      name: promotion.name,
      discountPercent: promotion.discountPercent,
      scope: promotion.scope,
      productIdsText: promotion.productIds.join(", "),
      category: promotion.category ?? "",
      startsAt: editableDate(promotion.startsAt),
      endsAt: editableDate(promotion.endsAt),
      enabled: promotion.enabled,
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function resetForm(): void {
    setEditingId(null);
    setDraft(initialDraft());
  }

  async function save(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const path = editingId ? `/v1/promotions/${encodeURIComponent(editingId)}` : "/v1/promotions";
      await apiFetch<Promotion>(token, path, {
        method: editingId ? "PUT" : "POST",
        body: toPromotionWrite(draft, !editingId),
      });
      resetForm();
      reload();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function setEnabled(promotion: Promotion, enabled: boolean): Promise<void> {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await apiFetch<Promotion>(
        token,
        `/v1/promotions/${encodeURIComponent(promotion.promotionId)}`,
        { method: "PUT", body: { enabled } },
      );
      setPromotions((current) => current?.map((item) => item.promotionId === updated.promotionId ? updated : item) ?? null);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!promotions) {
    return <div className="loading-screen"><div className="spinner"></div><p>Loading promotion operations…</p></div>;
  }

  return (
    <section>
      <div className="page-header">
        <div className="page-title-group">
          <h1>Admin — Promotions</h1>
          <p>Schedule product or category discounts. Disable promotions to preserve the historical pricing trail.</p>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card"><span className="stat-label">Active now</span><span className="stat-value">{counts.active}</span><span className="stat-desc">Applied by authoritative pricing</span></div>
        <div className="stat-card"><span className="stat-label">Scheduled</span><span className="stat-value">{counts.scheduled}</span><span className="stat-desc">Waiting for their start boundary</span></div>
        <div className="stat-card"><span className="stat-label">Disabled</span><span className="stat-value">{counts.disabled}</span><span className="stat-desc">Retained for audit context</span></div>
      </div>

      {error && <div className="alert-error">Promotion API error: {error}</div>}

      <form className="form-card" onSubmit={(event) => void save(event)} style={{ marginBottom: "2.5rem" }}>
        <h2>{editingId ? `Edit promotion — ${editingId}` : "Create promotion"}</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1.25rem" }}>
          <label>Promotion ID<input required pattern="[A-Za-z0-9._-]+" disabled={editingId !== null} value={draft.promotionId} onChange={(event) => setDraft({ ...draft, promotionId: event.target.value })} /></label>
          <label>Name<input required maxLength={120} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
          <label>Discount percentage<input required type="number" min="0.01" max="100" step="0.01" value={draft.discountPercent} onChange={(event) => setDraft({ ...draft, discountPercent: event.target.value })} /></label>
          <label>Scope<select value={draft.scope} onChange={(event) => setDraft({ ...draft, scope: event.target.value as PromotionDraft["scope"] })}><option value="PRODUCT">Products</option><option value="CATEGORY">Category</option></select></label>
          {draft.scope === "PRODUCT"
            ? <label>Product IDs<input required placeholder="prod-1, prod-2" value={draft.productIdsText} onChange={(event) => setDraft({ ...draft, productIdsText: event.target.value })} /></label>
            : <label>Category<input required maxLength={60} value={draft.category} onChange={(event) => setDraft({ ...draft, category: event.target.value })} /></label>}
          <label>Starts at<input required type="datetime-local" value={draft.startsAt} onChange={(event) => setDraft({ ...draft, startsAt: event.target.value })} /></label>
          <label>Ends at<input required type="datetime-local" value={draft.endsAt} onChange={(event) => setDraft({ ...draft, endsAt: event.target.value })} /></label>
          <label style={{ alignSelf: "end" }}><span><input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} /> Enabled</span></label>
        </div>
        <div className="actions" style={{ justifyContent: "flex-end", marginTop: "1rem" }}>
          {editingId && <button type="button" className="btn btn-secondary" onClick={resetForm}>Cancel edit</button>}
          <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : editingId ? "Save changes" : "Create promotion"}</button>
        </div>
      </form>

      {promotions.length === 0 ? <div className="empty-state"><h3>No promotions yet</h3><p>Create a scheduled discount above.</p></div> : (
        <div className="table-container">
          <table className="table">
            <thead><tr><th>Promotion</th><th>Scope</th><th>Discount</th><th>Window</th><th>Lifecycle</th><th>Actions</th></tr></thead>
            <tbody>{promotions.map((promotion) => (
              <tr key={promotion.promotionId}>
                <td><strong>{promotion.name}</strong><br /><code>{promotion.promotionId}</code></td>
                <td>{promotion.scope === "PRODUCT" ? `Products: ${promotion.productIds.join(", ")}` : `Category: ${promotion.category}`}</td>
                <td><strong>{promotion.discountPercent}%</strong></td>
                <td>{new Date(promotion.startsAt).toLocaleString()}<br />to {new Date(promotion.endsAt).toLocaleString()}</td>
                <td><span className={`badge ${promotion.lifecycleState === "ACTIVE" ? "badge-confirmed" : promotion.enabled ? "badge-pending" : "badge-rejected"}`}>{promotion.lifecycleState}</span></td>
                <td><div className="actions"><button className="btn btn-secondary btn-sm" onClick={() => startEdit(promotion)}>Edit</button><button className="btn btn-secondary btn-sm" disabled={busy} onClick={() => void setEnabled(promotion, !promotion.enabled)}>{promotion.enabled ? "Disable" : "Enable"}</button></div></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}
