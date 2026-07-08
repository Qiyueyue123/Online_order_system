import { useQuery } from "@tanstack/react-query";
import { Link, Outlet } from "react-router-dom";
import { api, ApiError, Cart, Session } from "./api/client";

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
      <div className="demo-strip">Portfolio demonstration · Stripe test mode · Prices in SGD</div>
      <header>
        <Link className="brand" to="/" aria-label="Mori Matcha home">
          <span>森</span> MORI MATCHA
        </Link>
        <nav aria-label="Primary navigation">
          <Link to="/">Shop</Link>
          <Link to="/#story">Our story</Link>
          <Link to={session ? "/account" : "/signin"}>
            {session ? session.user.name : "Sign in"}
          </Link>
          {session?.user.role === "admin" && <Link to="/admin">Admin</Link>}
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
          <span className="brand"><span>森</span> MORI MATCHA</span>
          <p>Fictional Japanese tea goods, curated in Singapore. A portfolio storefront—every order here is a demonstration.</p>
        </div>
        <div className="footer-col">
          <h4>Shop</h4>
          <ul>
            <li><Link to="/">All products</Link></li>
            <li><Link to="/#story">Our story</Link></li>
            <li><Link to="/cart">Your bag</Link></li>
          </ul>
        </div>
        <div className="footer-col">
          <h4>Account</h4>
          <ul>
            <li><Link to={session ? "/account" : "/signin"}>{session ? "Your account" : "Sign in"}</Link></li>
          </ul>
        </div>
        <p className="footer-disclaimer">Taxes, import duties and currency conversion are outside this demonstration. Payments run through Stripe test mode; no real charge is ever made.</p>
      </footer>
    </>
  );
}
