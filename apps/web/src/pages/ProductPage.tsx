import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, Cart, CartItemIn, DrinkOptions, money, Product } from "../api/client";
import { ProductArt } from "../components/ProductArt";

const SUGAR_OPTIONS: DrinkOptions["sugar_g"][] = [2, 4, 6, 8];

function ProductGallery({ product }: { product: Product }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const images = product.images;
  if (images.length === 0) {
    return (
      <div className="detail-art">
        <ProductArt slug={product.slug} category={product.category} name={product.name} />
      </div>
    );
  }
  const active = images[activeIndex] ?? images[0];
  return (
    <div className="detail-gallery">
      <div className="detail-art">
        <img className="product-photo" src={active.url} alt={active.alt_text} />
      </div>
      {images.length > 1 && (
        <div className="gallery-thumbs" role="group" aria-label="Product photos">
          {images.map((image, index) => (
            <button
              type="button"
              key={image.url}
              className={`gallery-thumb${index === activeIndex ? " active" : ""}`}
              aria-pressed={index === activeIndex}
              aria-label={`Show photo ${index + 1}: ${image.alt_text}`}
              onClick={() => setActiveIndex(index)}
            >
              <img src={image.url} alt="" loading="lazy" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function ProductPage() {
  const { slug = "" } = useParams();
  const queryClient = useQueryClient();
  const product = useQuery({ queryKey: ["product", slug], queryFn: () => api<Product>(`/products/${slug}`) });
  const [variantId, setVariantId] = useState("");
  const [whisk, setWhisk] = useState<DrinkOptions["whisk"]>("water");
  const [sugarG, setSugarG] = useState<DrinkOptions["sugar_g"]>(4);
  const add = useMutation({
    mutationFn: (payload: CartItemIn) =>
      api<Cart>("/cart/items", { method: "PUT", body: JSON.stringify(payload) }),
    onSuccess: (cart) => queryClient.setQueryData(["cart"], cart),
  });
  if (product.isLoading) return <div className="page"><p role="status">Loading product…</p></div>;
  if (!product.data) return <div className="page"><p role="alert">Product not found.</p></div>;
  const selected = variantId || product.data.variants[0]?.id;
  // ProductOut.category carries the display name ("Drinks"), not the slug.
  const isDrink = product.data.category?.toLowerCase() === "drinks";
  return (
    <div className="page product-detail">
      <ProductGallery product={product.data} />
      <section>
        <Link className="back-link" to="/">← Menu</Link>
        <p className="eyebrow">{product.data.category}</p>
        <h1>{product.data.name}</h1>
        <p>{product.data.description}</p>
        <label htmlFor="variant">{isDrink ? "Iced or hot" : "Size"}</label>
        <select id="variant" value={selected} onChange={(e) => setVariantId(e.target.value)}>
          {product.data.variants.map((variant) => <option key={variant.id} value={variant.id}>{variant.name} · {money(variant.price_cents)} · {variant.available_stock} left</option>)}
        </select>
        {isDrink && (
          <div className="drink-options">
            <p className="option-label">Whisked with</p>
            <div className="chip-row" role="group" aria-label="Whisked with">
              <button
                type="button"
                className={`chip${whisk === "water" ? " active" : ""}`}
                onClick={() => setWhisk("water")}
              >
                Water (standard)
              </button>
              <button
                type="button"
                className={`chip${whisk === "oat" ? " active" : ""}`}
                onClick={() => setWhisk("oat")}
              >
                Oat milk (frothier)
              </button>
            </div>
            <p className="option-label">Sugar</p>
            <div className="chip-row" role="group" aria-label="Sugar">
              {SUGAR_OPTIONS.map((grams) => (
                <button
                  type="button"
                  key={grams}
                  className={`chip${sugarG === grams ? " active" : ""}`}
                  onClick={() => setSugarG(grams)}
                >
                  {grams} g{grams === 4 ? " (standard)" : ""}
                </button>
              ))}
            </div>
            <p className="recipe-line">Every latte: 4 g Ajisai 2.0, whisked, poured over cow&rsquo;s milk.</p>
          </div>
        )}
        <button
          className="button"
          disabled={!selected || add.isPending}
          onClick={() =>
            selected &&
            add.mutate(
              isDrink
                ? { variant_id: selected, quantity: 1, options: { whisk, sugar_g: sugarG } }
                : { variant_id: selected, quantity: 1 },
            )
          }
        >
          {add.isPending ? "Adding…" : "Add to bag"}
        </button>
        {add.isSuccess && <p role="status">Added. <Link to="/cart">View your bag</Link></p>}
        {add.isError && <p role="alert">{add.error.message}</p>}
      </section>
    </div>
  );
}
