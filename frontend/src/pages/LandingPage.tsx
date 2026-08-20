import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { useCart } from "../context/CartContext";
import { createCognitoLogoutUrl } from "../auth-config";
import { getRuntimeConfig } from "../config/runtime-config";

// Public landing page. Renders for both authenticated and unauthenticated
// visitors so the site has a real front door instead of jumping straight to
// the catalogue or the sign-in form. Authenticated visitors see a personalised
// header and shopper-focused CTAs; unauthenticated visitors get Sign In / Sign
// Up prominence and can still browse the marketing content freely.
export function LandingPage() {
  const auth = useAuth();
  const isAdmin = useIsAdmin();
  const navigate = useNavigate();
  const { itemCount } = useCart();
  const [mobileOpen, setMobileOpen] = useState(false);
  const userEmail = auth.user?.profile.email as string | undefined;
  const authed = auth.isAuthenticated;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setMobileOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    // Close the menu automatically if the viewport crosses back into desktop
    // sizes; leaving it open produces awkward overlays on resize.
    function onResize() {
      if (window.innerWidth >= 900 && mobileOpen) setMobileOpen(false);
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [mobileOpen]);

  async function signOut(): Promise<void> {
    await auth.removeUser();
    window.location.assign(createCognitoLogoutUrl(getRuntimeConfig()));
  }

  function goShop(): void {
    // Products page is behind ProtectedRoute; unauth visitors will land on
    // the sign-in prompt first. That is the correct funnel for a real shop.
    navigate("/products");
  }

  return (
    <div className="landing">
      <a href="#landing-main" className="skip-to-content">
        Skip to main content
      </a>

      <header className="site-header" role="banner">
        <div className="site-header-inner">
          <Link to="/" className="site-brand" aria-label="SmartRetailX home">
            <span className="site-brand-mark" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>
            </span>
            <span className="site-brand-word">SmartRetailX</span>
          </Link>

          <button
            type="button"
            className="site-nav-toggle"
            aria-controls="site-nav"
            aria-expanded={mobileOpen}
            aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
            onClick={() => setMobileOpen((v) => !v)}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              {mobileOpen ? (
                <>
                  <line x1="6" y1="6" x2="18" y2="18" />
                  <line x1="6" y1="18" x2="18" y2="6" />
                </>
              ) : (
                <>
                  <line x1="4" y1="7" x2="20" y2="7" />
                  <line x1="4" y1="12" x2="20" y2="12" />
                  <line x1="4" y1="17" x2="20" y2="17" />
                </>
              )}
            </svg>
          </button>

          <nav
            id="site-nav"
            className={`site-nav${mobileOpen ? " site-nav-open" : ""}`}
            aria-label="Primary"
          >
            <ul className="site-nav-list">
              <li><a href="#shop" onClick={() => setMobileOpen(false)}>Shop</a></li>
              <li><a href="#deals" onClick={() => setMobileOpen(false)}>Deals</a></li>
              <li><a href="#benefits" onClick={() => setMobileOpen(false)}>Why SmartRetailX</a></li>
              <li><a href="#how-it-works" onClick={() => setMobileOpen(false)}>How it works</a></li>
              {authed && (
                <li>
                  <Link to="/orders" onClick={() => setMobileOpen(false)}>
                    My Orders
                  </Link>
                </li>
              )}
              {isAdmin && (
                <li>
                  <Link to="/admin/fulfilment" onClick={() => setMobileOpen(false)}>
                    Admin
                  </Link>
                </li>
              )}
            </ul>

            <div className="site-nav-actions">
              {authed ? (
                <>
                  <Link
                    to="/cart"
                    className="site-cart-link"
                    onClick={() => setMobileOpen(false)}
                    aria-label={
                      itemCount > 0
                        ? `Cart (${itemCount} item${itemCount === 1 ? "" : "s"})`
                        : "Cart (empty)"
                    }
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M2 4h3l2.7 12.4a2 2 0 0 0 2 1.6h8.6a2 2 0 0 0 2-1.6L22 8H6"/><circle cx="9" cy="21" r="1.5"/><circle cx="18" cy="21" r="1.5"/></svg>
                    <span>Cart</span>
                    {itemCount > 0 && (
                      <span className="site-cart-badge" aria-hidden="true">
                        {itemCount > 99 ? "99+" : itemCount}
                      </span>
                    )}
                  </Link>
                  <Link
                    to="/profile"
                    className="btn btn-ghost btn-sm"
                    onClick={() => setMobileOpen(false)}
                  >
                    <span className="site-user-name">{userEmail ?? "Account"}</span>
                  </Link>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => void signOut()}
                  >
                    Sign out
                  </button>
                </>
              ) : (
                <>
                  <Link
                    to="/login"
                    className="btn btn-ghost btn-sm"
                    onClick={() => setMobileOpen(false)}
                  >
                    Sign in
                  </Link>
                  <Link
                    to="/signup"
                    className="btn btn-sm"
                    onClick={() => setMobileOpen(false)}
                  >
                    Create account
                  </Link>
                </>
              )}
            </div>
          </nav>
        </div>
      </header>

      <main id="landing-main" className="landing-main">
        {/* HERO */}
        <section className="landing-hero" aria-labelledby="hero-heading">
          <div className="landing-hero-inner">
            <div className="landing-hero-copy">
              <span className="landing-eyebrow">
                Modern shopping · Live stock · Real-time tracking
              </span>
              <h1 id="hero-heading" className="landing-hero-title">
                Smarter shopping<br />starts here.
              </h1>
              <p className="landing-hero-lede">
                SmartRetailX is a modern online store built for the way people
                actually shop today &mdash; browse a curated catalogue, see live
                stock, place orders in seconds and watch them progress from
                packing to delivery in real time.
              </p>
              <div className="landing-hero-ctas">
                <button
                  type="button"
                  className="btn btn-lg landing-hero-primary"
                  onClick={goShop}
                >
                  Shop now
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                </button>
                <a
                  href="#deals"
                  className="btn btn-secondary btn-lg landing-hero-secondary"
                >
                  Explore deals
                </a>
              </div>
              {!authed && (
                <p className="landing-hero-microcopy">
                  New to SmartRetailX?{" "}
                  <Link to="/signup" className="link-underline">
                    Create your free account
                  </Link>{" "}
                  &mdash; it takes under a minute.
                </p>
              )}
            </div>
            <div className="landing-hero-visual" aria-hidden="true">
              <div className="landing-hero-card landing-hero-card-1">
                <div className="landing-hero-card-badge">Live</div>
                <div className="landing-hero-card-title">Order #ord-7f21</div>
                <div className="landing-hero-card-meta">Out for delivery</div>
                <div className="landing-hero-progress">
                  <div className="landing-hero-progress-fill" />
                </div>
              </div>
              <div className="landing-hero-card landing-hero-card-2">
                <div className="landing-hero-card-title">In stock</div>
                <div className="landing-hero-card-value">2,481</div>
                <div className="landing-hero-card-meta">items available today</div>
              </div>
              <div className="landing-hero-card landing-hero-card-3">
                <div className="landing-hero-card-title">Secured by</div>
                <div className="landing-hero-card-value">Cognito · MFA</div>
                <div className="landing-hero-card-meta">SigV4 downloads</div>
              </div>
              <div className="landing-hero-orb" />
            </div>
          </div>
        </section>

        {/* VALUE STRIP */}
        <section className="landing-value-strip" aria-label="Why customers choose SmartRetailX">
          <ul>
            <li>
              <span className="landing-value-icon" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v4"/><path d="M12 18v4"/><path d="m4.93 4.93 2.83 2.83"/><path d="m16.24 16.24 2.83 2.83"/><path d="M2 12h4"/><path d="M18 12h4"/><path d="m4.93 19.07 2.83-2.83"/><path d="m16.24 7.76 2.83-2.83"/></svg>
              </span>
              <div>
                <strong>Live stock availability</strong>
                <span>Only see products you can actually buy right now.</span>
              </div>
            </li>
            <li>
              <span className="landing-value-icon" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              </span>
              <div>
                <strong>Secure account</strong>
                <span>Optional multi-factor authentication on every account.</span>
              </div>
            </li>
            <li>
              <span className="landing-value-icon" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2a10 10 0 1 0 10 10"/><polyline points="12 6 12 12 16 14"/></svg>
              </span>
              <div>
                <strong>Real-time order tracking</strong>
                <span>Watch every order move from packing to your door.</span>
              </div>
            </li>
            <li>
              <span className="landing-value-icon" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M20 12V8a2 2 0 0 0-2-2h-3l-2-2h-2L9 6H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h6"/><path d="m16 18 2 2 4-4"/></svg>
              </span>
              <div>
                <strong>Simple order management</strong>
                <span>Cancel, download summaries and manage your history.</span>
              </div>
            </li>
          </ul>
        </section>

        {/* FEATURED CATEGORIES */}
        <section id="shop" className="landing-section landing-categories" aria-labelledby="categories-heading">
          <header className="landing-section-header">
            <h2 id="categories-heading">Explore the catalogue</h2>
            <p>Curated categories, real stock levels, honest prices.</p>
          </header>
          <div className="landing-category-grid">
            <button type="button" className="landing-category-card cat-electronics" onClick={goShop}>
              <div className="landing-category-icon" aria-hidden="true">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="4" width="20" height="14" rx="2"/><line x1="8" y1="22" x2="16" y2="22"/><line x1="12" y1="18" x2="12" y2="22"/></svg>
              </div>
              <div className="landing-category-copy">
                <h3>Electronics</h3>
                <p>Laptops, phones, headphones and gadgets from trusted brands.</p>
                <span className="landing-category-cta">Browse Electronics <span aria-hidden="true">&rarr;</span></span>
              </div>
            </button>
            <button type="button" className="landing-category-card cat-home" onClick={goShop}>
              <div className="landing-category-icon" aria-hidden="true">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="m3 10 9-7 9 7"/><path d="M5 8v12a1 1 0 0 0 1 1h4V15h4v6h4a1 1 0 0 0 1-1V8"/></svg>
              </div>
              <div className="landing-category-copy">
                <h3>Home &amp; Living</h3>
                <p>Everyday essentials and pieces that make a house feel yours.</p>
                <span className="landing-category-cta">Browse Home <span aria-hidden="true">&rarr;</span></span>
              </div>
            </button>
            <button type="button" className="landing-category-card cat-lifestyle" onClick={goShop}>
              <div className="landing-category-icon" aria-hidden="true">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M20.84 4.6a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.07a5.5 5.5 0 1 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.79 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
              </div>
              <div className="landing-category-copy">
                <h3>Lifestyle</h3>
                <p>Curated finds for the way you live &mdash; wellness, style, gifts.</p>
                <span className="landing-category-cta">Browse Lifestyle <span aria-hidden="true">&rarr;</span></span>
              </div>
            </button>
            <button type="button" className="landing-category-card cat-office" onClick={goShop}>
              <div className="landing-category-icon" aria-hidden="true">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M20 7h-4V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/><path d="M12 12v3"/></svg>
              </div>
              <div className="landing-category-copy">
                <h3>Work &amp; Office</h3>
                <p>Everything from stationery to standing desks for your workspace.</p>
                <span className="landing-category-cta">Browse Office <span aria-hidden="true">&rarr;</span></span>
              </div>
            </button>
          </div>
        </section>

        {/* DEALS */}
        <section id="deals" className="landing-section landing-deals" aria-labelledby="deals-heading">
          <div className="landing-deals-inner">
            <div className="landing-deals-copy">
              <span className="landing-eyebrow landing-eyebrow-invert">Today&rsquo;s Smart Deals</span>
              <h2 id="deals-heading">Better prices,<br />smarter shopping.</h2>
              <p>
                Every promotional price on SmartRetailX is calculated
                server-side against the authoritative product catalogue. What
                you see in your cart is the price you pay &mdash; no last-minute
                surprises at checkout.
              </p>
              <button
                type="button"
                className="btn btn-lg btn-invert"
                onClick={goShop}
              >
                See what&rsquo;s on offer
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
              </button>
            </div>
            <div className="landing-deals-visual" aria-hidden="true">
              <div className="landing-deal-chip landing-deal-chip-1">−15%</div>
              <div className="landing-deal-chip landing-deal-chip-2">−22%</div>
              <div className="landing-deal-chip landing-deal-chip-3">Save £40</div>
              <div className="landing-deal-chip landing-deal-chip-4">2 for 1</div>
            </div>
          </div>
        </section>

        {/* BENEFITS */}
        <section id="benefits" className="landing-section landing-benefits" aria-labelledby="benefits-heading">
          <header className="landing-section-header">
            <h2 id="benefits-heading">Built for real shopping.</h2>
            <p>Everything you&rsquo;d expect from a modern online store, done well.</p>
          </header>
          <div className="landing-benefit-grid">
            <article className="landing-benefit">
              <div className="landing-benefit-icon" aria-hidden="true">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
              </div>
              <h3>Live stock visibility</h3>
              <p>Every product card shows current availability. If the shelf is empty, you&rsquo;ll know before you add to cart.</p>
            </article>
            <article className="landing-benefit">
              <div className="landing-benefit-icon" aria-hidden="true">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
              </div>
              <h3>Account protection</h3>
              <p>Optional TOTP multi-factor authentication, secure password reset and a clear activity trail.</p>
            </article>
            <article className="landing-benefit">
              <div className="landing-benefit-icon" aria-hidden="true">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
              </div>
              <h3>Real-time order updates</h3>
              <p>Order status is pushed to your browser as soon as it changes. No refresh, no polling, no waiting.</p>
            </article>
            <article className="landing-benefit">
              <div className="landing-benefit-icon" aria-hidden="true">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
              </div>
              <h3>Downloadable summaries</h3>
              <p>Every order comes with a signed, private PDF summary you can save for your records.</p>
            </article>
          </div>
        </section>

        {/* HOW IT WORKS */}
        <section id="how-it-works" className="landing-section landing-how" aria-labelledby="how-heading">
          <header className="landing-section-header">
            <h2 id="how-heading">How SmartRetailX works</h2>
            <p>From first click to front door in four steps.</p>
          </header>
          <ol className="landing-how-steps">
            <li>
              <div className="landing-how-num" aria-hidden="true">01</div>
              <h3>Browse</h3>
              <p>Search the catalogue, filter by category, see honest availability.</p>
            </li>
            <li>
              <div className="landing-how-num" aria-hidden="true">02</div>
              <h3>Add to cart</h3>
              <p>Cart persists on your device &mdash; pick things up where you left off.</p>
            </li>
            <li>
              <div className="landing-how-num" aria-hidden="true">03</div>
              <h3>Checkout</h3>
              <p>Server-authoritative prices, one confirmation, one signed summary.</p>
            </li>
            <li>
              <div className="landing-how-num" aria-hidden="true">04</div>
              <h3>Track</h3>
              <p>Real-time status from packing through delivery, straight to your account.</p>
            </li>
          </ol>
        </section>

        {/* FINAL CTA */}
        <section className="landing-final-cta" aria-labelledby="final-cta-heading">
          <div className="landing-final-cta-inner">
            <h2 id="final-cta-heading">Ready to shop smarter?</h2>
            <p>
              Join SmartRetailX for a faster, clearer, more trustworthy online
              shopping experience.
            </p>
            <div className="landing-final-cta-actions">
              <button type="button" className="btn btn-lg" onClick={goShop}>
                Browse products
              </button>
              {!authed && (
                <Link to="/signup" className="btn btn-secondary btn-lg">
                  Create your account
                </Link>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer" role="contentinfo">
        <div className="site-footer-inner">
          <div className="site-footer-brand">
            <span className="site-brand-mark" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>
            </span>
            <div>
              <strong>SmartRetailX</strong>
              <span>Smarter online shopping.</span>
            </div>
          </div>
          <div className="site-footer-cols">
            <div>
              <h4>Shop</h4>
              <ul>
                <li><a href="#shop">Categories</a></li>
                <li><a href="#deals">Deals</a></li>
                <li>
                  <button
                    type="button"
                    className="site-footer-linklike"
                    onClick={goShop}
                  >
                    All products
                  </button>
                </li>
              </ul>
            </div>
            <div>
              <h4>Account</h4>
              <ul>
                {authed ? (
                  <>
                    <li><Link to="/orders">My Orders</Link></li>
                    <li><Link to="/profile">Profile</Link></li>
                    <li><Link to="/cart">Cart</Link></li>
                  </>
                ) : (
                  <>
                    <li><Link to="/login">Sign in</Link></li>
                    <li><Link to="/signup">Create account</Link></li>
                    <li><Link to="/forgot-password">Reset password</Link></li>
                  </>
                )}
              </ul>
            </div>
            <div>
              <h4>SmartRetailX</h4>
              <ul>
                <li><a href="#benefits">Why SmartRetailX</a></li>
                <li><a href="#how-it-works">How it works</a></li>
              </ul>
            </div>
          </div>
        </div>
        <div className="site-footer-bottom">
          <span>&copy; {new Date().getFullYear()} SmartRetailX</span>
          <span className="site-footer-note">Cognito &middot; ECS Fargate &middot; eu-west-1</span>
        </div>
      </footer>
    </div>
  );
}
