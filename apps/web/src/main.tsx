import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { App } from "./App";
import { CartPage } from "./pages/CartPage";
import { CatalogPage } from "./pages/CatalogPage";
import { CheckoutPage } from "./pages/CheckoutPage";
import { AccountPage } from "./pages/AccountPage";
import { AuthPage } from "./pages/AuthPage";
import { DemoPaymentPage } from "./pages/DemoPaymentPage";
import { OrderFlowPage } from "./pages/OrderFlowPage";
import { ProductPage } from "./pages/ProductPage";
import { StorePage } from "./pages/StorePage";
import { ThankYouPage } from "./pages/ThankYouPage";
import { AdminPage } from "./pages/admin/AdminPage";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});
const router = createBrowserRouter([
  {
    element: <App />,
    children: [
      { path: "/", element: <CatalogPage /> },
      { path: "/store", element: <StorePage /> },
      { path: "/products/:slug", element: <ProductPage /> },
      { path: "/cart", element: <CartPage /> },
      { path: "/checkout", element: <CheckoutPage /> },
      { path: "/signin", element: <AuthPage /> },
      { path: "/account", element: <AccountPage /> },
      { path: "/demo-payment/:orderId", element: <DemoPaymentPage /> },
      { path: "/thanks", element: <ThankYouPage /> },
      { path: "/admin", element: <AdminPage /> },
    ],
  },
  // Top-level, outside the App layout: the order flow is a full-screen
  // "scroll-through" experience without the site header/footer.
  { path: "/order", element: <OrderFlowPage /> },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
