import { render, screen, waitFor, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthContext } from "../auth/AuthContext";
import { OrderDetailPage } from "./OrderDetailPage";
import { apiFetch } from "../api/client";
import { useOrderStatusStream } from "../hooks/useOrderStatusStream";
import type { Order } from "../api/types";
import { AuthApi } from "../auth/AuthContext";

vi.mock("../api/client", () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

vi.mock("../hooks/useOrderStatusStream", () => ({
  useOrderStatusStream: vi.fn(),
}));

vi.mock("../config/runtime-config", () => ({
  getRuntimeConfig: () => ({ websocketUrl: "wss://test" }),
}));

const ORDER: Order = {
  orderId: "order-abc-123",
  userId: "user-1",
  status: "CONFIRMED",
  fulfilmentStatus: "PACKING",
  items: [
    {
      productId: "p1",
      productName: "Laptop",
      quantity: 2,
      baseUnitPrice: "999.99",
      effectiveUnitPrice: "899.99",
      unitDiscount: "100.00",
      lineDiscount: "200.00",
      lineTotal: "1799.98",
      promotionId: "promo-1",
    },
  ],
  subtotal: "1999.98",
  discountTotal: "200.00",
  totalAmount: "1799.98",
  createdAt: "2026-08-19T10:00:00Z",
  updatedAt: "2026-08-19T10:05:00Z",
  statusReason: null,
};

function makeAuth(): AuthApi {
  return {
    status: "authenticated",
    isLoading: false,
    isAuthenticated: true,
    activeNavigator: null,
    user: {
      access_token: "mock-token",
      id_token: "mock-id",
      profile: {
        email: "test@example.com",
        "cognito:groups": [],
      },
    },
    error: null,
    signIn: vi.fn(),
    signinRedirect: vi.fn(),
    removeUser: vi.fn(),
    refreshFromCognito: vi.fn(),
  };
}

describe("OrderDetailPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useOrderStatusStream).mockReturnValue("connected");
  });

  afterEach(() => {
    cleanup();
  });

  function renderPage(orderId = "order-abc-123") {
    return render(
      <MemoryRouter initialEntries={[`/orders/${orderId}`]}>
        <AuthContext.Provider value={makeAuth()}>
          <Routes>
            <Route path="/orders/:orderId" element={<OrderDetailPage />} />
          </Routes>
        </AuthContext.Provider>
      </MemoryRouter>,
    );
  }

  it("shows loading state then renders order details", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(ORDER);
    renderPage();

    expect(screen.getByText("Loading order details...")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.queryByText("Loading order details...")).not.toBeInTheDocument();
    });

    expect(screen.getByText("order-abc-123")).toBeInTheDocument();
    expect(screen.getByText("CONFIRMED")).toBeInTheDocument();
    expect(screen.getAllByText("PACKING").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Laptop")).toBeInTheDocument();
  });

  it("renders all line item columns", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(ORDER);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Laptop")).toBeInTheDocument();
    });

    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows fulfilment tracker for confirmed orders", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(ORDER);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Fulfilment progress")).toBeInTheDocument();
    });

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.getByText("NOT STARTED")).toBeInTheDocument();
    expect(screen.getByText("DELIVERED")).toBeInTheDocument();
  });

  it("does not show fulfilment tracker for rejected orders", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ...ORDER,
      status: "REJECTED",
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("REJECTED")).toBeInTheDocument();
    });

    expect(screen.queryByText("Fulfilment progress")).not.toBeInTheDocument();
  });

  it("shows cancel button for cancellable orders", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(ORDER);
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Cancel order" })).toBeInTheDocument();
    });
  });

  it("hides cancel button when fulfilment is DISPATCHED", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ...ORDER,
      fulfilmentStatus: "DISPATCHED",
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText("DISPATCHED").length).toBeGreaterThanOrEqual(1);
    });

    expect(screen.queryByRole("button", { name: "Cancel order" })).not.toBeInTheDocument();
  });

  it("calls cancel API on button click", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(ORDER)
      .mockResolvedValueOnce({ ...ORDER, status: "CANCEL_PENDING" });

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Cancel order" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Cancel order" }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledTimes(2);
      expect(screen.getByText("CANCEL_PENDING")).toBeInTheDocument();
    });
  });

  it("shows error when order fetch fails", async () => {
    vi.mocked(apiFetch).mockRejectedValueOnce(new Error("Order not found"));
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Order not found/)).toBeInTheDocument();
    });

    expect(screen.getByRole("link", { name: "Back to orders" })).toBeInTheDocument();
  });

  it("shows WebSocket connection indicator", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(ORDER);
    vi.mocked(useOrderStatusStream).mockReturnValue("connected");
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Live")).toBeInTheDocument();
    });
  });

  it("displays order summary totals", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(ORDER);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Order total")).toBeInTheDocument();
    });
  });

  it("shows Download Order Summary button", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(ORDER);
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Download Order Summary/i })).toBeInTheDocument();
    });
  });

  it("calls summary API and opens presigned URL on download click", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(ORDER)
      .mockResolvedValueOnce({ orderId: "order-abc-123", url: "https://s3.example.com/presigned" });
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null);

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Download Order Summary/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Download Order Summary/i }));

    await waitFor(() => {
      expect(vi.mocked(apiFetch)).toHaveBeenCalledWith(
        "mock-token",
        "/v1/orders/order-abc-123/summary",
      );
    });

    await waitFor(() => {
      expect(openSpy).toHaveBeenCalledWith("https://s3.example.com/presigned", "_blank", "noopener");
    });

    openSpy.mockRestore();
  });

  it("shows Preparing... text while download is in progress", async () => {
    let resolve: (value: unknown) => void;
    const pending = new Promise((r) => { resolve = r; });
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(ORDER)
      .mockReturnValueOnce(pending as Promise<unknown>);

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Download Order Summary/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Download Order Summary/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Preparing.../i })).toBeInTheDocument();
    });

    resolve!({ orderId: "order-abc-123", url: "https://example.com" });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Download Order Summary/i })).toBeInTheDocument();
    });
  });

  it("shows error when download fails", async () => {
    const { ApiError } = await import("../api/client");
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(ORDER)
      .mockRejectedValueOnce(new ApiError(500, "Internal Server Error"));

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Download Order Summary/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Download Order Summary/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });
});
