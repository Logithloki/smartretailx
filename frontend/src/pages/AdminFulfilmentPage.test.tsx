import { render, screen, waitFor, fireEvent, cleanup, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AuthContext } from "../auth/AuthContext";
import { AdminFulfilmentPage } from "./AdminFulfilmentPage";
import { apiFetch, ApiError } from "../api/client";
import { useOrderStatusStream } from "../hooks/useOrderStatusStream";
import type { Order } from "../api/types";
import { AuthApi } from "../auth/AuthContext";

vi.mock("../api/client", () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    body: string;
    constructor(status: number, body: string) {
      super(`HTTP ${status}: ${body}`);
      this.status = status;
      this.body = body;
    }
  },
}));

vi.mock("../hooks/useOrderStatusStream", () => ({
  useOrderStatusStream: vi.fn(),
}));

vi.mock("../config/runtime-config", () => ({
  getRuntimeConfig: () => ({ websocketUrl: "wss://test" }),
}));

function makeOrder(overrides: Partial<Order> = {}): Order {
  return {
    orderId: "ord-test-001",
    userId: "user-1",
    status: "CONFIRMED",
    fulfilmentStatus: "NOT_STARTED",
    items: [
      {
        productId: "p1",
        productName: "Laptop",
        quantity: 1,
        baseUnitPrice: "999.99",
        effectiveUnitPrice: "999.99",
        unitDiscount: "0.00",
        lineDiscount: "0.00",
        lineTotal: "999.99",
        promotionId: null,
      },
    ],
    subtotal: "999.99",
    discountTotal: "0.00",
    totalAmount: "999.99",
    createdAt: "2026-08-19T10:00:00Z",
    updatedAt: "2026-08-19T10:05:00Z",
    statusReason: null,
    ...overrides,
  };
}

function makeAdmin(): AuthApi {
  return {
    status: "authenticated",
    isLoading: false,
    isAuthenticated: true,
    activeNavigator: null,
    user: {
      access_token: "admin-token",
      id_token: "mock-id",
      profile: {
        email: "admin@example.com",
        "cognito:groups": ["admin"],
      },
    },
    error: null,
    signIn: vi.fn(),
    signinRedirect: vi.fn(),
    removeUser: vi.fn(),
    refreshFromCognito: vi.fn(),
  };
}

function renderPage(auth: AuthApi = makeAdmin()) {
  return render(
    <MemoryRouter>
      <AuthContext.Provider value={auth}>
        <AdminFulfilmentPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("AdminFulfilmentPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useOrderStatusStream).mockReturnValue("connected");
  });

  afterEach(() => {
    cleanup();
  });

  it("shows loading spinner initially", () => {
    vi.mocked(apiFetch).mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText("Loading fulfilment queue...")).toBeTruthy();
  });

  it("renders the page title and Live badge when connected", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ orders: [] });
    renderPage();
    await waitFor(() => expect(screen.getByText(/Admin: Fulfilment/)).toBeTruthy());
    expect(screen.getByText("Live")).toBeTruthy();
  });

  it("shows error state with retry button on API failure", async () => {
    vi.mocked(apiFetch).mockRejectedValueOnce(new Error("Network error"));
    renderPage();
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByText("Retry")).toBeTruthy();
  });

  it("renders the empty state when no orders exist", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ orders: [] });
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("No orders in the system")).toBeTruthy(),
    );
  });

  it("renders summary stat cards with correct counts", async () => {
    const orders = [
      makeOrder({ orderId: "o1", fulfilmentStatus: "NOT_STARTED", status: "CONFIRMED" }),
      makeOrder({ orderId: "o2", fulfilmentStatus: "PACKING", status: "CONFIRMED" }),
      makeOrder({ orderId: "o3", fulfilmentStatus: "DELIVERED", status: "CONFIRMED" }),
      makeOrder({ orderId: "o4", status: "CANCELLED", fulfilmentStatus: "NOT_STARTED" }),
    ];
    vi.mocked(apiFetch).mockResolvedValueOnce({ orders });
    renderPage();

    await waitFor(() => {
      const statCards = screen.getAllByRole("status");
      expect(statCards).toHaveLength(4);
    });

    const statCards = screen.getAllByRole("status");
    expect(within(statCards[0]).getByText("1")).toBeTruthy();
    expect(within(statCards[1]).getByText("1")).toBeTruthy();
    expect(within(statCards[2]).getByText("1")).toBeTruthy();
    expect(within(statCards[3]).getByText("1")).toBeTruthy();
  });

  it("renders the order table with correct columns", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ orders: [makeOrder()] });
    renderPage();
    await waitFor(() => expect(screen.getByText("ord-test-001")).toBeTruthy());
    expect(screen.getByText("1 item")).toBeTruthy();
  });

  it("shows action button for confirmed orders needing fulfilment", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ orders: [makeOrder()] });
    renderPage();
    await waitFor(() =>
      expect(screen.getByLabelText("Start packing for order ord-test-001")).toBeTruthy(),
    );
  });

  it("does not show action button for delivered orders", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      orders: [makeOrder({ fulfilmentStatus: "DELIVERED" })],
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("ord-test-001")).toBeTruthy());
    expect(screen.queryByText("Mark delivered")).toBeNull();
  });

  it("does not show action button for cancelled orders", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      orders: [makeOrder({ status: "CANCELLED" })],
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("ord-test-001")).toBeTruthy());
    expect(screen.queryByText("Start packing")).toBeNull();
  });

  it("filters orders by 'Needs action'", async () => {
    const orders = [
      makeOrder({ orderId: "o1", fulfilmentStatus: "NOT_STARTED", status: "CONFIRMED" }),
      makeOrder({ orderId: "o2", fulfilmentStatus: "PACKING", status: "CONFIRMED" }),
    ];
    vi.mocked(apiFetch).mockResolvedValueOnce({ orders });
    renderPage();
    await waitFor(() => expect(screen.getByText("o1")).toBeTruthy());

    const filterButtons = screen.getAllByRole("button", { pressed: false });
    const needsActionBtn = filterButtons.find((b) => b.textContent?.startsWith("Needs action"));
    fireEvent.click(needsActionBtn!);

    expect(screen.getByText("o1")).toBeTruthy();
    expect(screen.queryByText("o2")).toBeNull();
  });

  it("filters orders by search term on order ID", async () => {
    const orders = [
      makeOrder({ orderId: "ord-laptop-001" }),
      makeOrder({ orderId: "ord-phone-002" }),
    ];
    vi.mocked(apiFetch).mockResolvedValueOnce({ orders });
    renderPage();
    await waitFor(() => expect(screen.getByText("ord-laptop-001")).toBeTruthy());

    fireEvent.change(screen.getByLabelText("Search orders"), {
      target: { value: "phone" },
    });

    expect(screen.queryByText("ord-laptop-001")).toBeNull();
    expect(screen.getByText("ord-phone-002")).toBeTruthy();
  });

  it("calls PATCH /fulfilment on action button click", async () => {
    const order = makeOrder();
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ orders: [order] })
      .mockResolvedValueOnce({ ...order, fulfilmentStatus: "PACKING" });

    renderPage();
    await waitFor(() =>
      expect(screen.getByLabelText("Start packing for order ord-test-001")).toBeTruthy(),
    );

    fireEvent.click(screen.getByLabelText("Start packing for order ord-test-001"));

    await waitFor(() => {
      expect(vi.mocked(apiFetch)).toHaveBeenCalledWith(
        "admin-token",
        "/v1/orders/ord-test-001/fulfilment",
        { method: "PATCH", body: { status: "PACKING" } },
      );
    });
  });

  it("shows conflict warning on 409 response and reloads", async () => {
    const order = makeOrder();
    const err = new (vi.mocked(ApiError))(409, "Conflict");
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ orders: [order] })
      .mockRejectedValueOnce(err)
      .mockResolvedValueOnce({ orders: [{ ...order, fulfilmentStatus: "PACKING" }] });

    renderPage();
    await waitFor(() =>
      expect(screen.getByLabelText("Start packing for order ord-test-001")).toBeTruthy(),
    );

    fireEvent.click(screen.getByLabelText("Start packing for order ord-test-001"));

    await waitFor(() =>
      expect(screen.getByText(/Order was updated by another session/)).toBeTruthy(),
    );
  });

  it("opens detail drawer on row click", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ orders: [makeOrder()] });
    renderPage();
    await waitFor(() => expect(screen.getByText("ord-test-001")).toBeTruthy());

    fireEvent.click(screen.getByText("ord-test-001"));

    await waitFor(() => {
      const dialog = screen.getByRole("dialog");
      expect(dialog).toBeTruthy();
      expect(within(dialog).getByText(/ord-test-001/)).toBeTruthy();
    });
  });

  it("drawer shows fulfilment progress tracker for confirmed orders", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      orders: [makeOrder({ fulfilmentStatus: "PACKING" })],
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("ord-test-001")).toBeTruthy());

    fireEvent.click(screen.getByText("ord-test-001"));

    await waitFor(() => {
      expect(screen.getByRole("progressbar")).toBeTruthy();
    });
  });

  it("drawer shows line items table", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ orders: [makeOrder()] });
    renderPage();
    await waitFor(() => expect(screen.getByText("ord-test-001")).toBeTruthy());

    fireEvent.click(screen.getByText("ord-test-001"));

    await waitFor(() => {
      const dialog = screen.getByRole("dialog");
      expect(within(dialog).getByText("Laptop")).toBeTruthy();
    });
  });

  it("closes drawer on close button click", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ orders: [makeOrder()] });
    renderPage();
    await waitFor(() => expect(screen.getByText("ord-test-001")).toBeTruthy());

    fireEvent.click(screen.getByText("ord-test-001"));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeTruthy());

    fireEvent.click(screen.getByLabelText("Close detail panel"));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("shows correct action labels for each fulfilment state", async () => {
    const orders = [
      makeOrder({ orderId: "o1", fulfilmentStatus: "NOT_STARTED" }),
      makeOrder({ orderId: "o2", fulfilmentStatus: "PACKING" }),
      makeOrder({ orderId: "o3", fulfilmentStatus: "DISPATCHED" }),
      makeOrder({ orderId: "o4", fulfilmentStatus: "OUT_FOR_DELIVERY" }),
    ];
    vi.mocked(apiFetch).mockResolvedValueOnce({ orders });
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText("Start packing for order o1")).toBeTruthy();
      expect(screen.getByLabelText("Mark dispatched for order o2")).toBeTruthy();
      expect(screen.getByLabelText("Out for delivery for order o3")).toBeTruthy();
      expect(screen.getByLabelText("Mark delivered for order o4")).toBeTruthy();
    });
  });

  it("shows 'No orders match the current filter' with reset button", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      orders: [makeOrder({ status: "CANCELLED" })],
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("ord-test-001")).toBeTruthy());

    const filterButtons = screen.getAllByRole("button");
    const needsActionBtn = filterButtons.find((b) => b.textContent?.startsWith("Needs action"));
    fireEvent.click(needsActionBtn!);

    expect(screen.getByText("No orders match the current filter")).toBeTruthy();
    expect(screen.getByText("Reset filters")).toBeTruthy();
  });

  it("refresh button reloads data", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ orders: [] })
      .mockResolvedValueOnce({ orders: [makeOrder()] });

    renderPage();
    await waitFor(() => expect(screen.getByText("No orders in the system")).toBeTruthy());

    fireEvent.click(screen.getByLabelText("Refresh order queue"));

    await waitFor(() => expect(screen.getByText("ord-test-001")).toBeTruthy());
  });

  it("fulfilment badge uses correct CSS classes", async () => {
    const orders = [
      makeOrder({ orderId: "o1", fulfilmentStatus: "NOT_STARTED" }),
      makeOrder({ orderId: "o2", fulfilmentStatus: "PACKING" }),
      makeOrder({ orderId: "o3", fulfilmentStatus: "DELIVERED" }),
    ];
    vi.mocked(apiFetch).mockResolvedValueOnce({ orders });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("NOT STARTED").className).toContain("badge-pending");
      expect(screen.getByText("PACKING").className).toContain("badge-fulfilment-active");
      expect(screen.getByText("DELIVERED").className).toContain("badge-confirmed");
    });
  });
});
