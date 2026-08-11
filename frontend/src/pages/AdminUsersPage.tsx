import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../context/useAuth";
import { apiFetch, ApiError } from "../api/client";
import type { UserListResponse, UserProfile } from "../api/types";

export function AdminUsersPage() {
  const auth = useAuth();
  const token = auth.user?.access_token;
  const currentEmail = auth.user?.profile.email;

  const [users, setUsers] = useState<UserProfile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const reload = () => {
    if (!token) return;
    apiFetch<UserListResponse>(token, "/v1/users")
      .then((data) => {
        setUsers(data.users);
      })
      .catch((err: unknown) => {
        // Fallback for demo users if backend user-service directory lists seed accounts
        setError(err instanceof ApiError ? err.message : String(err));
      });
  };

  useEffect(reload, [token]);

  async function handleDeleteUser(userToDelete: UserProfile) {
    if (!token) return;
    if (userToDelete.email === currentEmail) {
      setError("Security Policy: You cannot delete your own logged-in admin account.");
      return;
    }

    if (!window.confirm(`Are you sure you want to permanently delete user "${userToDelete.email}"?`)) {
      return;
    }

    setBusyId(userToDelete.username || userToDelete.userId);
    setError(null);
    setSuccessMsg(null);

    try {
      await apiFetch<void>(
        token,
        `/v1/users/${encodeURIComponent(userToDelete.username || userToDelete.email)}`,
        { method: "DELETE" },
      );
      setSuccessMsg(`User "${userToDelete.email}" was deleted from Cognito Directory.`);
      setUsers((prev) => (prev ? prev.filter((u) => u.email !== userToDelete.email) : []));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  }

  // Derived statistics
  const stats = useMemo(() => {
    if (!users) return { total: 0, admins: 0, customers: 0 };
    let admins = 0;
    let customers = 0;
    for (const u of users) {
      if (u.groups.includes("admin")) {
        admins++;
      } else {
        customers++;
      }
    }
    return { total: users.length, admins, customers };
  }, [users]);

  // Filtered users list
  const filteredUsers = useMemo(() => {
    if (!users) return [];
    const q = search.trim().toLowerCase();
    if (!q) return users;
    return users.filter(
      (u) =>
        u.email.toLowerCase().includes(q) ||
        u.userId.toLowerCase().includes(q) ||
        u.username.toLowerCase().includes(q) ||
        u.groups.some((g) => g.toLowerCase().includes(q)),
    );
  }, [users, search]);

  if (!users) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <p>Loading User Directory from User Microservice & AWS Cognito...</p>
      </div>
    );
  }

  return (
    <section>
      <div className="page-header">
        <div className="page-title-group">
          <h1>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            Admin — User Directory & Role Management
          </h1>
          <p>Manage customer and administrator user accounts registered in AWS Cognito User Pool.</p>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-label">Total Registered Users</span>
          <span className="stat-value">{stats.total}</span>
          <span className="stat-desc">Active accounts in system</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Administrators</span>
          <span className="stat-value">{stats.admins}</span>
          <span className="stat-desc">Privileged admin accounts</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Customers</span>
          <span className="stat-value">{stats.customers}</span>
          <span className="stat-desc">Standard shopper accounts</span>
        </div>
      </div>

      {error && (
        <div className="alert-error" style={{ marginBottom: "1rem" }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          {error}
        </div>
      )}

      {successMsg && (
        <div style={{ background: "var(--emerald-100)", border: "1px solid var(--emerald-border)", color: "var(--emerald-600)", padding: "0.75rem", borderRadius: "var(--radius-md)", fontSize: "0.875rem", marginBottom: "1rem", fontWeight: 600 }}>
          {successMsg}
        </div>
      )}

      <div className="toolbar">
        <div className="search-input-wrap">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            type="text"
            placeholder="Search directory by email, role, or ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {filteredUsers.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
          </div>
          <h3>No matching users found</h3>
          <p>Try clearing your search query.</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>User Email</th>
                <th>User ID</th>
                <th>Assigned Role</th>
                <th>Account Status</th>
                <th style={{ textAlign: "right" }}>Management Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((u) => {
                const isAdmin = u.groups.includes("admin");
                const isCurrent = u.email === currentEmail;

                return (
                  <tr key={u.userId || u.username || u.email}>
                    <td style={{ fontWeight: 600 }}>
                      {u.email} {isCurrent && <span style={{ fontSize: "0.75rem", background: "var(--surface-tertiary)", padding: "0.15rem 0.4rem", borderRadius: "4px", marginLeft: "0.4rem", color: "var(--text-tertiary)" }}>(You)</span>}
                    </td>
                    <td>
                      <code>{u.userId}</code>
                    </td>
                    <td>
                      <span className={`role-pill ${isAdmin ? "admin" : "customer"}`}>
                        {isAdmin ? "Admin" : "Customer"}
                      </span>
                    </td>
                    <td>
                      <span className="badge badge-confirmed">ACTIVE</span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        style={{ color: isCurrent ? "var(--text-tertiary)" : "var(--rose-600)", borderColor: "var(--border-subtle)" }}
                        disabled={isCurrent || busyId === (u.username || u.userId)}
                        onClick={() => handleDeleteUser(u)}
                      >
                        {busyId === (u.username || u.userId) ? (
                          <>
                            <div className="spinner" style={{ width: "12px", height: "12px", borderWidth: "2px" }}></div>
                            Deleting...
                          </>
                        ) : (
                          "Delete User"
                        )}
                      </button>
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
