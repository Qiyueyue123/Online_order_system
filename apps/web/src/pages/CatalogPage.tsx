import { useQuery } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { api, money, Product, ProductPage as ProductPageResult } from "../api/client";
import { HeroCarousel } from "../components/HeroCarousel";
import { ProductArt } from "../components/ProductArt";

const CATEGORIES = [
  { value: "", label: "All" },
  { value: "drinks", label: "Drinks" },
  { value: "matcha", label: "Matcha tins" },
];

function ProductCard({ product, index }: { product: Product; index: number }) {
  const photo = product.images[0];
  return (
    <Link
      className="product-card"
      to={`/products/${product.slug}`}
      style={{ animationDelay: `${index * 70}ms` }}
    >
      <div className="product-art">
        {photo ? (
          <img className="product-photo" src={photo.url} alt={photo.alt_text} loading="lazy" />
        ) : (
          <ProductArt slug={product.slug} category={product.category} name={product.name} tone={index} />
        )}
      </div>
      <div className="product-meta">
        <div><p className="eyebrow">{product.category}</p><h3>{product.name}</h3></div>
        <strong>{product.variants[0] ? money(product.variants[0].price_cents) : "Unavailable"}</strong>
      </div>
    </Link>
  );
}

export function CatalogPage() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const query = params.get("q") ?? "";
  const category = params.get("category") ?? "";
  const location = useLocation();
  const products = useQuery({
    queryKey: ["products", query, category],
    queryFn: () =>
      api<ProductPageResult>(
        `/products?${new URLSearchParams({ ...(query && { q: query }), ...(category && { category }) })}`,
      ),
  });
  useEffect(() => {
    if (location.hash === "#story") {
      document.getElementById("story")?.scrollIntoView({ behavior: "smooth" });
    }
  }, [location.hash, products.data]);
  function submit(event: FormEvent) {
    event.preventDefault();
    setParams(search ? { q: search } : {});
  }
  const items = products.data?.items ?? [];
  const drinkItems = items.filter((product) => product.category === "drinks");
  const retailItems = items.filter((product) => product.category !== "drinks");
  const showDrinks = category === "" || category === "drinks";
  const showRetail = category === "" || category === "matcha";
  return (
    <>
      <section className="hero grain">
        <HeroCarousel />
        <p className="vertical-label">一服 · WHISKED TO ORDER</p>
        <div className="hero-copy">
          <p className="eyebrow">UMEÅ · MADE TO ORDER</p>
          <h1>Matcha, whisked<br />just for you.</h1>
          <p>Order online, then swing by our dorm kitchen — every cup is whisked fresh the moment you arrive.</p>
          <a className="button" href="#collection">See the menu</a>
        </div>
      </section>
      <section id="collection" className="collection">
        <div className="section-heading">
          <div><p className="eyebrow">WHISKED FRESH DAILY</p><h2>The menu</h2></div>
          <form role="search" onSubmit={submit}>
            <label className="sr-only" htmlFor="catalog-search">Search products</label>
            <input id="catalog-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search" />
            <button type="submit">Search</button>
          </form>
        </div>
        <div className="filters" aria-label="Product categories">
          {CATEGORIES.map(({ value, label }) => (
            <button className={category === value ? "active" : ""} onClick={() => setParams(value ? { category: value } : {})} key={value}>
              {label}
            </button>
          ))}
        </div>
        {products.isLoading && <p role="status">Preparing the menu…</p>}
        {products.isError && <p role="alert">The menu could not be loaded. Please try again.</p>}
        {products.data && items.length === 0 && <p>No products match your search.</p>}
        {showDrinks && drinkItems.length > 0 && (
          <div className="product-grid">
            {drinkItems.map((product, index) => <ProductCard product={product} index={index} key={product.id} />)}
          </div>
        )}
        {showRetail && retailItems.length > 0 && (
          <>
            <div className="section-heading retail-heading">
              <div><p className="eyebrow">FOR HOME</p><h3>Take-home</h3></div>
            </div>
            <div className="product-grid retail-grid">
              {retailItems.map((product, index) => <ProductCard product={product} index={index} key={product.id} />)}
            </div>
          </>
        )}
      </section>
      <section id="story" className="story grain">
        <p className="eyebrow">OUR STORY</p>
        <h2>From a pop-up<br />to a dorm kitchen.</h2>
        <p>QY &amp; YX&rsquo;s Cafe started as a small pop-up in the Netherlands, whisking matcha for friends between classes. Now we&rsquo;re pouring it in Umeå — order online, and we&rsquo;ll have it ready at the door.</p>
      </section>
    </>
  );
}
