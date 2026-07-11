import { useQuery } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { api, formatNoticeDate, money, Notice, Product, ProductPage as ProductPageResult } from "../api/client";
import { HeroCarousel } from "../components/HeroCarousel";
import { MediaCarousel } from "../components/MediaCarousel";
import { ProductArt } from "../components/ProductArt";

function Noticeboard() {
  // Best-effort: a broken or empty notice list should never break the
  // homepage, so failures and empty results both render nothing.
  const notices = useQuery({
    queryKey: ["notices"],
    queryFn: () => api<Notice[]>("/notices"),
    retry: false,
  });
  if (!notices.data || notices.data.length === 0) return null;
  return (
    <section className="noticeboard" aria-label="Shop notices">
      {notices.data.map((notice) => (
        <article key={notice.id} className="notice-card">
          <div className="notice-heading">
            <h3>{notice.title}</h3>
            <span className="notice-date">{formatNoticeDate(notice.created_at)}</span>
          </div>
          <p>{notice.body}</p>
        </article>
      ))}
    </section>
  );
}

export function ProductCard({ product, index }: { product: Product; index: number }) {
  const images = product.images;
  return (
    <Link
      className="product-card"
      to={`/products/${product.slug}`}
      style={{ animationDelay: `${index * 70}ms` }}
    >
      <div className="product-art">
        {images.length > 0 ? (
          <MediaCarousel items={images} mediaClassName="product-photo" label={`${product.name} photos`} />
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
  const location = useLocation();
  const products = useQuery({
    queryKey: ["products", "drinks", query],
    queryFn: () =>
      api<ProductPageResult>(
        `/products?${new URLSearchParams({ category: "drinks", ...(query && { q: query }) })}`,
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
  return (
    <>
      <Noticeboard />
      <section className="hero grain">
        <HeroCarousel />
        <p className="vertical-label">一服 · WHISKED TO ORDER</p>
        <div className="hero-copy">
          <p className="eyebrow">UMEÅ · MADE TO ORDER</p>
          <h1>Matcha, whisked<br />just for you.</h1>
          <p>Order online, then swing by our dorm kitchen — every cup is whisked fresh the moment you arrive.</p>
          <div className="hero-actions">
            <Link className="button order-cta-hero" to="/order">Order now</Link>
            <a className="button button-ghost" href="#collection">See the menu</a>
          </div>
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
        {products.isLoading && <p role="status">Preparing the menu…</p>}
        {products.isError && <p role="alert">The menu could not be loaded. Please try again.</p>}
        {products.data && items.length === 0 && <p>No products match your search.</p>}
        <div className="product-grid">
          {items.map((product, index) => <ProductCard product={product} index={index} key={product.id} />)}
        </div>
      </section>
      <section id="story" className="story grain">
        <p className="eyebrow">OUR STORY</p>
        <h2>From a pop-up<br />to a dorm kitchen.</h2>
        <p>QY &amp; YX&rsquo;s Cafe started as a small pop-up in the Netherlands, whisking matcha for friends between classes. Now we&rsquo;re pouring it in Umeå — order online, and we&rsquo;ll have it ready at the door.</p>
        <p>
          Every drink is whisked from{" "}
          <a href="https://www.nikonekomatcha.com/" target="_blank" rel="noreferrer">Niko Neko</a>
          &rsquo;s Ajisai 2.0, a ceremonial Yabukita matcha from Mie.
        </p>
      </section>
    </>
  );
}
