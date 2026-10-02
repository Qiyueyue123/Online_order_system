import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, Cart, CartItemIn, humanizeError, money, Product } from "../api/client";
import { MediaCarousel } from "../components/MediaCarousel";
import { ProductArt } from "../components/ProductArt";

// Builds the initial selection map: one entry per option group, defaulted to
// the choice the group marks default: true (falling back to the first choice
// if a misconfigured group somehow has none).
function defaultSelections(product: Product): Record<string, string> {
  const selections: Record<string, string> = {};
  for (const group of product.options ?? []) {
    const defaultChoice = group.choices.find((choice) => choice.default) ?? group.choices[0];
    if (defaultChoice) selections[group.key] = defaultChoice.value;
  }
  return selections;
}

// Sum of surcharge_cents for the currently selected choice in each group.
function surchargeTotal(product: Product, selections: Record<string, string>): number {
  let total = 0;
  for (const group of product.options ?? []) {
    const choice = group.choices.find((c) => c.value === selections[group.key]);
    if (choice) total += choice.surcharge_cents;
  }
  return total;
}

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
          showCaptions
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
  // Overrides on top of each group's default choice; only holds the groups the
  // shopper has actually touched, so it re-defaults cleanly if the product
  // changes underneath it (e.g. slug navigation) without needing an effect.
  const [selectionOverrides, setSelectionOverrides] = useState<Record<string, string>>({});
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
  const optionGroups = product.data.options ?? [];
  const hasOptions = optionGroups.length > 0;
  const selections = { ...defaultSelections(product.data), ...selectionOverrides };
  const surcharge = hasOptions ? surchargeTotal(product.data, selections) : 0;
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
        {hasOptions && (
          <div className="drink-options">
            <div className="option-grid">
              {optionGroups.map((group) => (
                <div key={group.key}>
                  <p className="option-label">{group.label}</p>
                  <div className="chip-row" role="group" aria-label={group.label}>
                    {group.choices.map((choice) => (
                      <button
                        type="button"
                        key={choice.value}
                        className={`chip${selections[group.key] === choice.value ? " active" : ""}`}
                        onClick={() =>
                          setSelectionOverrides((current) => ({ ...current, [group.key]: choice.value }))
                        }
                      >
                        {choice.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            {isDrink && (
              <>
                <p className="recipe-line">Every latte is served iced: 4 g Ajisai 2.0, whisked, poured over 130 ml cow&rsquo;s milk (standard).</p>
                <p className="food-safety-note">Good to know: we use store-bought packaged ice, and every drink comes sealed in a plastic cup with a lid.</p>
              </>
            )}
          </div>
        )}
        <button
          className="button"
          disabled={!selected || add.isPending || soldOut}
          onClick={() =>
            selected &&
            add.mutate(
              hasOptions
                ? { variant_id: selected, quantity: 1, options: selections }
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
