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
          <a href="#story">Our story</a>
          <Link to={session ? "/account" : "/signin"}>
            {session ? session.user.name : "Sign in"}
          </Link>
          <Link className="cart-link" to="/cart">
            Bag <span aria-label={`${itemCount} items`}>{itemCount}</span>
          </Link>
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
      <footer>
        <div>
          <span className="brand">MORI MATCHA</span>
          <p>Fictional Japanese tea goods, curated in Singapore.</p>
        </div>
        <p>Taxes, import duties and currency conversion are outside this demonstration.</p>
      </footer>
    </>
  );
}
