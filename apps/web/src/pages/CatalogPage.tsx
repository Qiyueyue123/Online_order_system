import { useQuery } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, money, ProductPage } from "../api/client";

export function CatalogPage() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const query = params.get("q") ?? "";
  const category = params.get("category") ?? "";
  const products = useQuery({
    queryKey: ["products", query, category],
    queryFn: () =>
      api<ProductPage>(
        `/products?${new URLSearchParams({ ...(query && { q: query }), ...(category && { category }) })}`,
      ),
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    setParams(search ? { q: search } : {});
  }
  return (
    <>
      <section className="hero">
        <p className="eyebrow">STONE-GROUND · SMALL LOTS</p>
        <h1>A quieter kind<br />of energy.</h1>
        <p>Fictional ceremonial matcha and considered tools for a daily ritual.</p>
        <a className="button" href="#collection">Explore the collection</a>
      </section>
      <section id="collection" className="collection">
        <div className="section-heading">
          <div><p className="eyebrow">THE COLLECTION</p><h2>Find your matcha</h2></div>
          <form role="search" onSubmit={submit}>
            <label className="sr-only" htmlFor="catalog-search">Search products</label>
            <input id="catalog-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search" />
            <button type="submit">Search</button>
          </form>
        </div>
        <div className="filters" aria-label="Product categories">
          {["", "matcha", "tools"].map((value) => (
            <button className={category === value ? "active" : ""} onClick={() => setParams(value ? { category: value } : {})} key={value}>
              {value || "All"}
            </button>
          ))}
        </div>
        {products.isLoading && <p role="status">Preparing the collection…</p>}
        {products.isError && <p role="alert">The collection could not be loaded. Please try again.</p>}
        {products.data?.items.length === 0 && <p>No products match your search.</p>}
        <div className="product-grid">
          {products.data?.items.map((product, index) => (
            <Link className="product-card" to={`/products/${product.slug}`} key={product.id}>
              <div className={`product-art art-${index % 3}`}>
                {product.images[0] ? <img src={product.images[0].url} alt={product.images[0].alt_text} /> : <span>抹茶</span>}
              </div>
              <div className="product-meta">
                <div><p className="eyebrow">{product.category}</p><h3>{product.name}</h3></div>
                <strong>{product.variants[0] ? money(product.variants[0].price_sgd_cents) : "Unavailable"}</strong>
              </div>
            </Link>
          ))}
        </div>
      </section>
      <section id="story" className="story">
        <p className="eyebrow">OUR APPROACH</p>
        <h2>Made for the pause<br />between things.</h2>
        <p>Every item in this demonstration catalog is fictional. The experience is built to show deliberate commerce engineering—from inventory to fulfillment.</p>
      </section>
    </>
  );
}
