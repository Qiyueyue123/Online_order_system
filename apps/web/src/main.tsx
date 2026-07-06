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
import { ProductPage } from "./pages/ProductPage";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});
const router = createBrowserRouter([
  {
    element: <App />,
    children: [
      { path: "/", element: <CatalogPage /> },
      { path: "/products/:slug", element: <ProductPage /> },
      { path: "/cart", element: <CartPage /> },
      { path: "/checkout", element: <CheckoutPage /> },
      { path: "/signin", element: <AuthPage /> },
      { path: "/account", element: <AccountPage /> },
      { path: "/demo-payment/:orderId", element: <DemoPaymentPage /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
