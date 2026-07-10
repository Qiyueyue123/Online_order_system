import { useQuery } from "@tanstack/react-query";
import { Link, Outlet } from "react-router-dom";
import { api, ApiError, Cart, Session } from "./api/client";
import {
  CONTACT_TELEGRAM_HANDLE,
  CONTACT_TELEGRAM_URL,
  CONTACT_WHATSAPP_HANDLE,
  CONTACT_WHATSAPP_URL,
} from "./contact";

export function App() {
  const { data: cart } = useQuery({ queryKey: ["cart"], queryFn: () => api<Cart>("/cart") });
  const { data: session } = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/auth/session"),
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 1,
  });
  const itemCount = cart?.items.reduce((sum, item) => sum + item.quantity, 0) ?? 0;
  return (
    <>
      <div className="demo-strip">Portfolio demonstration · Stripe test mode · Prices in SEK · Pickup in Umeå</div>
      <header>
        <Link className="brand" to="/" aria-label="QY &amp; YX's Cafe home">
          <span>抹茶</span> QY &amp; YX&rsquo;S CAFE
        </Link>
        <nav aria-label="Primary navigation">
          <Link to="/">Drinks</Link>
          <Link to="/store">Store</Link>
          <Link to="/#story">Our story</Link>
          {session?.user.role === "admin" ? (
            <Link to="/admin">Admin</Link>
          ) : (
            <Link to={session ? "/account" : "/signin"}>
              {session ? session.user.name : "Sign in"}
            </Link>
          )}
          <Link className="cart-link" to="/cart">
            Bag <span aria-label={`${itemCount} items`}>{itemCount}</span>
          </Link>
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
      <footer>
        <div className="footer-brand">
          <span className="brand"><span>抹茶</span> QY &amp; YX&rsquo;S CAFE</span>
          <p>Matcha drinks whisked to order and picked up at our dorm kitchen in Umeå. A portfolio storefront—every order here is a demonstration.</p>
          <p className="photo-credit">
            Drink and product photography courtesy of{" "}
            <a href="https://www.nikonekomatcha.com/" target="_blank" rel="noreferrer">Niko Neko Matcha</a>.
          </p>
        </div>
        <div className="footer-col">
          <h4>Shop</h4>
          <ul>
            <li><Link to="/">Drinks</Link></li>
            <li><Link to="/store">Store</Link></li>
            <li><Link to="/#story">Our story</Link></li>
            <li><Link to="/cart">Your bag</Link></li>
          </ul>
        </div>
        <div className="footer-col">
          <h4>Account</h4>
          <ul>
            {session?.user.role === "admin" ? (
              <li><Link to="/admin">Admin console</Link></li>
            ) : (
              <li><Link to={session ? "/account" : "/signin"}>{session ? "Your account" : "Sign in"}</Link></li>
            )}
          </ul>
        </div>
        <p className="footer-contact">
          Questions or payment issues? Telegram{" "}
          <a href={CONTACT_TELEGRAM_URL} target="_blank" rel="noreferrer">{CONTACT_TELEGRAM_HANDLE}</a>
          {" · "}WhatsApp{" "}
          <a href={CONTACT_WHATSAPP_URL} target="_blank" rel="noreferrer">{CONTACT_WHATSAPP_HANDLE}</a>
        </p>
        <p className="footer-disclaimer">Taxes, import duties and currency conversion are outside this demonstration. Payments run through Stripe test mode; no real charge is ever made.</p>
      </footer>
    </>
  );
}
