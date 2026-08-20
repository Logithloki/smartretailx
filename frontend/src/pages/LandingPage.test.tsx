import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { LandingPage } from "./LandingPage";
import { AuthContext, type AuthApi } from "../auth/AuthContext";
import { CartProvider } from "../context/CartContext";

const navigateMock = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigateMock };
});

function makeAuth(overrides: Partial<AuthApi> = {}): AuthApi {
  return {
    status: "unauthenticated",
    isLoading: false,
    isAuthenticated: false,
    activeNavigator: null,
    user: null,
    error: null,
    signIn: vi.fn(),
    signinRedirect: vi.fn(),
    removeUser: vi.fn(),
    refreshFromCognito: vi.fn(),
    ...overrides,
  } as AuthApi;
}

function renderLanding(auth: AuthApi) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <AuthContext.Provider value={auth}>
        <CartProvider>
          <LandingPage />
        </CartProvider>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("LandingPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("renders a public retail hero with one H1 and meaningful imagery", () => {
    renderLanding(makeAuth());
    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent(/everything you need/i);
    expect(screen.getByRole("img", { name: /shopping cart with everyday groceries/i })).toBeInTheDocument();
  });

  it("routes the primary browse CTA to the existing products page", () => {
    renderLanding(makeAuth());
    fireEvent.click(screen.getAllByRole("button", { name: /^browse products$/i })[0]);
    expect(navigateMock).toHaveBeenCalledWith("/products");
  });

  it("shows guest account actions and does not expose an admin link", () => {
    renderLanding(makeAuth());
    expect(screen.getAllByRole("link", { name: /^sign in$/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /create account/i }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /^admin$/i })).not.toBeInTheDocument();
  });

  it("shows account navigation when a customer is authenticated", () => {
    renderLanding(makeAuth({
      status: "authenticated",
      isAuthenticated: true,
      user: { profile: { email: "customer@example.com" } } as AuthApi["user"],
    }));
    expect(screen.getAllByRole("link", { name: /my orders/i }).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });

  it("shows the existing admin workspace link only for an admin group claim", () => {
    renderLanding(makeAuth({
      status: "authenticated",
      isAuthenticated: true,
      user: { profile: { email: "admin@example.com", "cognito:groups": ["admin"] } } as AuthApi["user"],
    }));
    expect(screen.getByRole("link", { name: /^admin$/i })).toHaveAttribute("href", "/admin/fulfilment");
  });

  it("uses the persisted cart quantity in the accessible cart badge", () => {
    window.localStorage.setItem("smartretailx.cart.v1", JSON.stringify([{
      product: { productId: "demo-product", productName: "Demo product", price: "10.00", category: "Demo", active: true },
      quantity: 3,
    }]));
    renderLanding(makeAuth());
    expect(screen.getByRole("link", { name: "Cart (3 items)" })).toBeInTheDocument();
  });

  it("opens and closes the mobile navigation", () => {
    renderLanding(makeAuth());
    const toggle = screen.getByRole("button", { name: /open navigation/i });
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: /close navigation/i })).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByRole("button", { name: /open navigation/i })).toHaveAttribute("aria-expanded", "false");
  });

  it("renders static category visuals without product API content or fake prices", () => {
    renderLanding(makeAuth());
    expect(screen.getByRole("heading", { name: /a thoughtful place to start/i })).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: /illustration/i })).toHaveLength(4);
    expect(screen.queryByText(/£\d/)).not.toBeInTheDocument();
  });

  it("has keyboard landmarks and a usable footer", () => {
    const { container } = renderLanding(makeAuth());
    expect(screen.getByRole("link", { name: /skip to main content/i })).toHaveAttribute("href", "#storefront-main");
    expect(container.querySelector("main#storefront-main")).toBeTruthy();
    const footer = container.querySelector(".store-footer") as HTMLElement;
    expect(within(footer).getByRole("navigation", { name: /footer navigation/i })).toBeInTheDocument();
  });
});
