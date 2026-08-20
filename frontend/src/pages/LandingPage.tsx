import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createCognitoLogoutUrl } from "../auth-config";
import { getRuntimeConfig } from "../config/runtime-config";
import { useAuth } from "../context/useAuth";
import { useCart } from "../context/CartContext";
import { useIsAdmin } from "../hooks/useIsAdmin";

type Category = {
  title: string;
  description: string;
  accent: "mint" | "amber" | "ink" | "rose";
  icon: "basket" | "device" | "home" | "care";
};

const CATEGORIES: Category[] = [
  { title: "Everyday essentials", description: "Simple shopping for the things you reach for most.", accent: "mint", icon: "basket" },
  { title: "Electronics", description: "Useful technology for work, home and downtime.", accent: "ink", icon: "device" },
  { title: "Home & living", description: "Thoughtful pieces for a more comfortable space.", accent: "amber", icon: "home" },
  { title: "Personal care", description: "Everyday wellbeing, all in one place.", accent: "rose", icon: "care" },
];

function CategoryArtwork({ icon }: Pick<Category, "icon">) {
  if (icon === "basket") {
    return <svg aria-hidden="true" viewBox="0 0 96 96"><path d="M23 38h50l-5 36H28l-5-36Z" /><path d="m35 38 13-17 13 17M36 51h24M33 61h30" /></svg>;
  }
  if (icon === "device") {
    return <svg aria-hidden="true" viewBox="0 0 96 96"><rect x="24" y="17" width="48" height="62" rx="8" /><path d="M38 68h20M42 28h12" /></svg>;
  }
  if (icon === "home") {
    return <svg aria-hidden="true" viewBox="0 0 96 96"><path d="m18 47 30-25 30 25v29H18V47Z" /><path d="M39 76V57h18v19M35 39h26" /></svg>;
  }
  return <svg aria-hidden="true" viewBox="0 0 96 96"><path d="M34 76V42a14 14 0 0 1 28 0v34" /><path d="M28 76h40M40 31h16M47 21v10" /></svg>;
}

export function LandingPage() {
  const auth = useAuth();
  const isAdmin = useIsAdmin();
  const cart = useCart();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const authed = auth.isAuthenticated;
  const userEmail = auth.user?.profile.email as string | undefined;

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent): void {
      if (event.key === "Escape") setMobileOpen(false);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  async function signOut(): Promise<void> {
    await auth.removeUser();
    window.location.assign(createCognitoLogoutUrl(getRuntimeConfig()));
  }

  function goShop(): void {
    navigate("/products");
  }

  function closeMenu(): void {
    setMobileOpen(false);
  }

  return (
    <div className="storefront">
      <a href="#storefront-main" className="skip-to-content">Skip to main content</a>

      <header className="store-header">
        <div className="store-shell store-header-inner">
          <Link to="/" className="store-brand" aria-label="SmartRetailX home" onClick={closeMenu}>
            <span className="store-brand-mark" aria-hidden="true">SR</span>
            <span>SmartRetailX</span>
          </Link>

          <button
            type="button"
            className="store-menu-toggle"
            aria-controls="store-primary-navigation"
            aria-expanded={mobileOpen}
            aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
            onClick={() => setMobileOpen((open) => !open)}
          >
            <span aria-hidden="true">{mobileOpen ? "×" : "☰"}</span>
          </button>

          <nav id="store-primary-navigation" className={mobileOpen ? "store-nav store-nav-open" : "store-nav"} aria-label="Primary navigation">
            <div className="store-nav-links">
              <Link to="/" onClick={closeMenu}>Home</Link>
              <Link to="/products" onClick={closeMenu}>Shop</Link>
              <a href="#shopping" onClick={closeMenu}>Discover</a>
              {authed && <Link to="/orders" onClick={closeMenu}>My orders</Link>}
              {isAdmin && <Link to="/admin/fulfilment" onClick={closeMenu}>Admin</Link>}
            </div>
            <div className="store-nav-actions">
              <Link to="/cart" className="store-cart-link" onClick={closeMenu} aria-label={cart.itemCount ? `Cart (${cart.itemCount} items)` : "Cart (empty)"}>
                Cart <span aria-hidden="true" className="store-cart-count">{cart.itemCount > 99 ? "99+" : cart.itemCount}</span>
              </Link>
              {authed ? (
                <>
                  <Link to="/profile" className="store-account-link" onClick={closeMenu}>{userEmail ?? "Account"}</Link>
                  <button type="button" className="store-button store-button-secondary" onClick={() => void signOut()}>Sign out</button>
                </>
              ) : (
                <>
                  <Link to="/login" className="store-account-link" onClick={closeMenu}>Sign in</Link>
                  <Link to="/signup" className="store-button" onClick={closeMenu}>Create account</Link>
                </>
              )}
            </div>
          </nav>
        </div>
      </header>

      <main id="storefront-main">
        <section className="store-hero" aria-labelledby="store-hero-title">
          <div className="store-shell store-hero-grid">
            <div className="store-hero-copy">
              <p className="store-eyebrow">Shopping made simpler</p>
              <h1 id="store-hero-title">Everything you need, all in one place.</h1>
              <p>Browse the SmartRetailX catalogue, build your basket and keep up with every order from checkout to delivery.</p>
              <div className="store-hero-actions">
                <button type="button" className="store-button store-button-large" onClick={goShop}>Browse products <span aria-hidden="true">→</span></button>
                <Link className="store-text-action" to="/login">Sign in <span aria-hidden="true">→</span></Link>
              </div>
            </div>
            <div className="store-hero-media">
              <img src="/images/storefront-hero.jpg" alt="A shopping cart with everyday groceries in a well-stocked store" />
              <div className="store-hero-media-caption"><span aria-hidden="true">✦</span> Thoughtful shopping, clearly organised</div>
            </div>
          </div>
        </section>

        <section className="store-benefits" aria-label="SmartRetailX benefits">
          <div className="store-shell store-benefit-grid">
            <article><span aria-hidden="true">◈</span><div><h2>Smart stock availability</h2><p>Useful availability details before you head to checkout.</p></div></article>
            <article><span aria-hidden="true">↗</span><div><h2>Real-time order updates</h2><p>Follow your order and fulfilment progress as it changes.</p></div></article>
            <article><span aria-hidden="true">⌁</span><div><h2>Secure account access</h2><p>Manage your account with optional multi-factor authentication.</p></div></article>
            <article><span aria-hidden="true">▣</span><div><h2>Order summaries</h2><p>Find authorised order documents in your order history.</p></div></article>
          </div>
        </section>

        <section id="shopping" className="store-section" aria-labelledby="shopping-heading">
          <div className="store-shell">
            <div className="store-section-heading">
              <div><p className="store-eyebrow">Shop by category</p><h2 id="shopping-heading">A thoughtful place to start.</h2></div>
              <button type="button" className="store-text-action" onClick={goShop}>Explore the catalogue <span aria-hidden="true">→</span></button>
            </div>
            <div className="store-category-grid">
              {CATEGORIES.map((category) => (
                <article className={`store-category-card store-category-${category.accent}`} key={category.title}>
                  <div className="store-category-art" role="img" aria-label={`${category.title} illustration`}><CategoryArtwork icon={category.icon} /></div>
                  <div><h3>{category.title}</h3><p>{category.description}</p><button type="button" className="store-text-action" onClick={goShop}>Browse products <span aria-hidden="true">→</span></button></div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="store-showcase" aria-labelledby="showcase-heading">
          <div className="store-shell store-showcase-grid">
            <div className="store-showcase-copy"><p className="store-eyebrow">Browse with confidence</p><h2 id="showcase-heading">A store designed around the everyday shop.</h2><p>Explore a clear catalogue, revisit your cart when you are ready and let the checkout flow confirm the latest availability.</p><button type="button" className="store-button store-button-light" onClick={goShop}>Explore products</button></div>
            <div className="store-showcase-visual" aria-hidden="true"><div className="store-showcase-card store-showcase-card-main"><span>New ways to browse</span><strong>One clear catalogue</strong></div><div className="store-showcase-card store-showcase-card-note">From basket<br />to doorstep</div><div className="store-showcase-orb" /></div>
          </div>
        </section>

        <section className="store-tracking" aria-labelledby="tracking-heading">
          <div className="store-shell store-tracking-grid">
            <div className="store-tracking-visual" aria-hidden="true"><span>Confirmed</span><i /><span>Packing</span><i /><span>Out for delivery</span><i /><span>Delivered</span></div>
            <div><p className="store-eyebrow">Order tracking</p><h2 id="tracking-heading">Stay updated from confirmation to delivery.</h2><p>SmartRetailX shows clear order and fulfilment updates in your order history, with real-time updates when available.</p>{authed ? <Link to="/orders" className="store-text-action">View my orders <span aria-hidden="true">→</span></Link> : <Link to="/signup" className="store-text-action">Create an account <span aria-hidden="true">→</span></Link>}</div>
          </div>
        </section>

        <section id="how-it-works" className="store-section store-how" aria-labelledby="how-heading">
          <div className="store-shell"><div className="store-section-heading"><div><p className="store-eyebrow">How it works</p><h2 id="how-heading">From browse to tracking in four clear steps.</h2></div></div><ol><li><span>01</span><h3>Browse</h3><p>Explore the product catalogue.</p></li><li><span>02</span><h3>Add to cart</h3><p>Collect what you need in one place.</p></li><li><span>03</span><h3>Checkout</h3><p>Submit your order with server-side stock checks.</p></li><li><span>04</span><h3>Track</h3><p>Follow your order as it progresses.</p></li></ol></div>
        </section>

        <section className="store-final-cta" aria-labelledby="final-heading"><div className="store-shell store-final-cta-inner"><div><p className="store-eyebrow">SmartRetailX</p><h2 id="final-heading">Ready to start shopping?</h2><p>{authed ? "Continue shopping or check the progress of your latest order." : "Create an account to browse the catalogue, build a cart and manage your orders."}</p></div><div className="store-final-actions">{authed ? <><button type="button" className="store-button store-button-light" onClick={goShop}>Continue shopping</button><Link to="/orders" className="store-button store-button-outline-light">View my orders</Link></> : <><Link to="/products" className="store-button store-button-light">Browse products</Link><Link to="/signup" className="store-button store-button-outline-light">Create account</Link></>}</div></div></section>
      </main>

      <footer className="store-footer"><div className="store-shell store-footer-grid"><div><Link to="/" className="store-brand store-brand-footer"><span className="store-brand-mark" aria-hidden="true">SR</span><span>SmartRetailX</span></Link><p>A modern online store with secure accounts, clear shopping tools and helpful order updates.</p></div><nav aria-label="Footer navigation"><Link to="/">Home</Link><Link to="/products">Products</Link>{authed ? <><Link to="/orders">My orders</Link><Link to="/profile">Account</Link></> : <><Link to="/login">Sign in</Link><Link to="/signup">Create account</Link></>}</nav></div><div className="store-shell store-footer-bottom"><span>© {new Date().getFullYear()} SmartRetailX</span><span>Shopping made clearer.</span></div></footer>
    </div>
  );
}
