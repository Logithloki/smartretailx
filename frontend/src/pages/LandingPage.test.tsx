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

  it("renders the marketing hero with a single H1", () => {
    renderLanding(makeAuth());
    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent(/smarter shopping/i);
  });

  it("Shop now CTA navigates to /products", () => {
    renderLanding(makeAuth());
    fireEvent.click(screen.getByRole("button", { name: /^shop now$/i }));
    expect(navigateMock).toHaveBeenCalledWith("/products");
  });

  it("shows Sign In and Create Account when signed out", () => {
    renderLanding(makeAuth());
    // Header + microcopy both link to signup — assert at least one of each exists.
    expect(screen.getAllByRole("link", { name: /^sign in$/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /create account/i }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /sign out/i })).not.toBeInTheDocument();
  });

  it("shows account nav (Orders, Cart, Sign out) when signed in", () => {
    const auth = makeAuth({
      status: "authenticated",
      isAuthenticated: true,
      user: { profile: { email: "test@example.com" } } as AuthApi["user"],
    });
    renderLanding(auth);
    // Header + footer both surface Orders / Cart / Profile for signed-in users.
    expect(screen.getAllByRole("link", { name: /my orders/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /^cart/i }).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^sign in$/i })).not.toBeInTheDocument();
  });

  it("does not show admin link when the user is a regular customer", () => {
    const auth = makeAuth({
      status: "authenticated",
      isAuthenticated: true,
      user: { profile: { email: "customer@example.com" } } as AuthApi["user"],
    });
    renderLanding(auth);
    expect(screen.queryByRole("link", { name: /^admin$/i })).not.toBeInTheDocument();
  });

  it("mobile menu toggle opens and closes", () => {
    renderLanding(makeAuth());
    const toggle = screen.getByRole("button", { name: /open navigation/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(
      screen.getByRole("button", { name: /close navigation/i }),
    ).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(screen.getByRole("button", { name: /close navigation/i }));
    expect(screen.getByRole("button", { name: /open navigation/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("renders the four featured categories", () => {
    renderLanding(makeAuth());
    const cats = ["Electronics", "Home & Living", "Lifestyle", "Work & Office"];
    for (const cat of cats) {
      expect(screen.getByRole("heading", { name: cat, level: 3 })).toBeInTheDocument();
    }
  });

  it("category cards navigate to /products", () => {
    renderLanding(makeAuth());
    const electronicsCard = screen
      .getByRole("heading", { name: "Electronics", level: 3 })
      .closest("button");
    expect(electronicsCard).toBeTruthy();
    fireEvent.click(electronicsCard!);
    expect(navigateMock).toHaveBeenCalledWith("/products");
  });

  it("footer shows current year and no dead '#' anchor placeholders", () => {
    const { container } = renderLanding(makeAuth());
    const footer = container.querySelector(".site-footer") as HTMLElement | null;
    expect(footer).toBeTruthy();
    expect(within(footer!).getByText(new RegExp(String(new Date().getFullYear())))).toBeInTheDocument();
    for (const a of footer!.querySelectorAll("a[href]")) {
      const href = a.getAttribute("href") || "";
      // In-page anchors and app routes are allowed; the placeholder "#" alone
      // is not — it produces a link that jumps back to the top and looks dead.
      expect(href).not.toBe("#");
    }
  });

  it("has a skip-to-content link for keyboard users", () => {
    renderLanding(makeAuth());
    const skip = screen.getByRole("link", { name: /skip to main content/i });
    expect(skip).toHaveAttribute("href", "#landing-main");
  });
});
