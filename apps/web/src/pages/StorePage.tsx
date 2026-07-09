import { useQuery } from "@tanstack/react-query";
import { api, ProductPage as ProductPageResult } from "../api/client";
import { ProductArt } from "../components/ProductArt";
import { ProductCard } from "./CatalogPage";

const PLACEHOLDERS = [
  { slug: "seasonal-tins", name: "Seasonal tins" },
  { slug: "brewing-tools", name: "Brewing tools" },
  { slug: "gift-sets", name: "Gift sets" },
];

export function StorePage() {
  const products = useQuery({
    queryKey: ["products", "matcha"],
    queryFn: () => api<ProductPageResult>(`/products?${new URLSearchParams({ category: "matcha" })}`),
  });
  const items = products.data?.items ?? [];
  return (
    <section className="collection">
      <div className="section-heading">
        <div><p className="eyebrow">FOR HOME</p><h2>Take-home shelf</h2></div>
      </div>
      {products.isLoading && <p role="status">Loading the shelf…</p>}
      {products.isError && <p role="alert">The shelf could not be loaded. Please try again.</p>}
      <div className="product-grid retail-grid">
        {items.map((product, index) => <ProductCard product={product} index={index} key={product.id} />)}
        {PLACEHOLDERS.map((placeholder, index) => (
          <div className="product-card product-card--placeholder" key={placeholder.slug} aria-label={`${placeholder.name}, coming soon`}>
            <div className="product-art">
              <ProductArt slug={placeholder.slug} category="matcha" name={placeholder.name} tone={items.length + index} />
              <span className="coming-soon-badge">Coming soon</span>
            </div>
            <div className="product-meta">
              <div><p className="eyebrow">matcha</p><h3>{placeholder.name}</h3></div>
              <strong>Coming soon</strong>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
