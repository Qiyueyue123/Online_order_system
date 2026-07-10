import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, Cart, CartItemIn, DrinkOptions, humanizeError, money, Product } from "../api/client";
import { MediaCarousel } from "../components/MediaCarousel";
import { ProductArt } from "../components/ProductArt";

const SUGAR_OPTIONS: DrinkOptions["sugar_g"][] = [2, 4, 6, 8];
const MATCHA_OPTIONS: DrinkOptions["matcha_g"][] = [4, 6];
const MILK_VOLUME_OPTIONS: DrinkOptions["milk_ml"][] = [130, 160];
// Must match app.services.cart.MATCHA_UPGRADE_SURCHARGE_CENTS — only used
// here to preview the price before adding to bag; the server is the source
// of truth for what's actually charged.
const MATCHA_UPGRADE_SURCHARGE_CENTS = 1500;

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
  return (
    <div className="detail-gallery">
      <div className="detail-art">
        <MediaCarousel
          items={images}
          activeIndex={activeIndex}
          onActiveIndexChange={setActiveIndex}
          mediaClassName="detail-media"
          label="Product photos"
          eagerFirst
        />
      </div>
      {images.length > 1 && (
        <div className="gallery-thumbs" role="group" aria-label="Product photos">
          {images.map((image, index) => (
            <button
              type="button"
              key={image.url}
              className={`gallery-thumb${index === activeIndex ? " active" : ""}`}
              aria-pressed={index === activeIndex}
              aria-label={`Show ${image.media_type === "video" ? "video" : "photo"} ${index + 1}: ${image.alt_text}`}
              onClick={() => setActiveIndex(index)}
            >
              {image.media_type === "video" ? (
                <video src={image.url} muted playsInline />
              ) : (
                <img src={image.url} alt="" loading="lazy" />
              )}
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
  const [matchaG, setMatchaG] = useState<DrinkOptions["matcha_g"]>(4);
  const [whisk, setWhisk] = useState<DrinkOptions["whisk"]>("water");
  const [baseMilk, setBaseMilk] = useState<DrinkOptions["base_milk"]>("cow");
  const [milkMl, setMilkMl] = useState<DrinkOptions["milk_ml"]>(130);
  const [sugarG, setSugarG] = useState<DrinkOptions["sugar_g"]>(4);
  const add = useMutation({
    mutationFn: (payload: CartItemIn) =>
      api<Cart>("/cart/items", { method: "PUT", body: JSON.stringify(payload) }),
    onSuccess: (cart) => queryClient.setQueryData(["cart"], cart),
  });
  if (product.isLoading) return <div className="page"><p role="status">Loading product…</p></div>;
  if (!product.data) return <div className="page"><p role="alert">Product not found.</p></div>;
  const variants = product.data.variants;
  const selected = variantId || variants[0]?.id;
  const activeVariant = variants.find((variant) => variant.id === selected) ?? variants[0];
  const isDrink = product.data.category_slug === "drinks";
  const surcharge = isDrink && matchaG === 6 ? MATCHA_UPGRADE_SURCHARGE_CENTS : 0;
  const totalPrice = (activeVariant?.price_cents ?? 0) + surcharge;
  const soldOut = !!activeVariant && activeVariant.available_stock === 0;
  return (
    <div className="page product-detail">
      <ProductGallery product={product.data} />
      <section>
        <Link className="back-link" to="/">← Menu</Link>
        <p className="eyebrow">{product.data.category}</p>
        <h1>{product.data.name}</h1>
        <p>{product.data.description}</p>
        {variants.length > 1 ? (
          <>
            <label htmlFor="variant">Size</label>
            <select id="variant" value={selected} onChange={(e) => setVariantId(e.target.value)}>
              {variants.map((variant) => (
                <option key={variant.id} value={variant.id}>
                  {variant.name} · {money(variant.price_cents)} ·{" "}
                  {variant.available_stock === 0 ? "Sold out" : `${variant.available_stock} left`}
                </option>
              ))}
            </select>
          </>
        ) : (
          activeVariant && (
            <p className="variant-note">
              {isDrink ? "Served iced" : activeVariant.name} ·{" "}
              {activeVariant.available_stock === 0 ? "Sold out" : `${activeVariant.available_stock} left`}
            </p>
          )
        )}
        {isDrink && (
          <div className="drink-options">
            <div className="option-grid">
              <div>
                <p className="option-label">Matcha</p>
                <div className="chip-row" role="group" aria-label="Matcha amount">
                  {MATCHA_OPTIONS.map((grams) => (
                    <button
                      type="button"
                      key={grams}
                      className={`chip${matchaG === grams ? " active" : ""}`}
                      onClick={() => setMatchaG(grams)}
                    >
                      {grams} g{grams === 4 ? " (standard)" : " stronger (+15 kr)"}
                    </button>
                  ))}
                </div>
              </div>
              <div>
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
              </div>
              <div>
                <p className="option-label">Base milk</p>
                <div className="chip-row" role="group" aria-label="Base milk">
                  <button
                    type="button"
                    className={`chip${baseMilk === "cow" ? " active" : ""}`}
                    onClick={() => setBaseMilk("cow")}
                  >
                    Cow&rsquo;s milk (standard)
                  </button>
                  <button
                    type="button"
                    className={`chip${baseMilk === "oat" ? " active" : ""}`}
                    onClick={() => setBaseMilk("oat")}
                  >
                    Oat milk
                  </button>
                </div>
              </div>
              <div>
                <p className="option-label">Milk amount</p>
                <div className="chip-row" role="group" aria-label="Milk amount">
                  {MILK_VOLUME_OPTIONS.map((ml) => (
                    <button
                      type="button"
                      key={ml}
                      className={`chip${milkMl === ml ? " active" : ""}`}
                      onClick={() => setMilkMl(ml)}
                    >
                      {ml} ml{ml === 130 ? " (standard)" : " (milkier)"}
                    </button>
                  ))}
                </div>
              </div>
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
            <p className="recipe-line">Every latte is served iced: 4 g Ajisai 2.0, whisked, poured over 130 ml cow&rsquo;s milk (standard).</p>
            <p className="food-safety-note">Good to know: we use store-bought packaged ice, and every drink comes sealed in a plastic cup with a lid.</p>
          </div>
        )}
        <button
          className="button"
          disabled={!selected || add.isPending || soldOut}
          onClick={() =>
            selected &&
            add.mutate(
              isDrink
                ? {
                    variant_id: selected,
                    quantity: 1,
                    options: { matcha_g: matchaG, whisk, base_milk: baseMilk, milk_ml: milkMl, sugar_g: sugarG },
                  }
                : { variant_id: selected, quantity: 1 },
            )
          }
        >
          {soldOut ? "Sold out" : add.isPending ? "Adding…" : `Add to bag — ${money(totalPrice)}`}
        </button>
        {add.isSuccess && <p role="status">Added. <Link to="/cart">View your bag</Link></p>}
        {add.isError && <p role="alert">{humanizeError(add.error)}</p>}
      </section>
    </div>
  );
}
