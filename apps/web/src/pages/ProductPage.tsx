import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, Cart, money, Product } from "../api/client";
import { ProductArt } from "../components/ProductArt";

export function ProductPage() {
  const { slug = "" } = useParams();
  const queryClient = useQueryClient();
  const product = useQuery({ queryKey: ["product", slug], queryFn: () => api<Product>(`/products/${slug}`) });
  const [variantId, setVariantId] = useState("");
  const add = useMutation({
    mutationFn: (id: string) => api<Cart>("/cart/items", { method: "PUT", body: JSON.stringify({ variant_id: id, quantity: 1 }) }),
    onSuccess: (cart) => queryClient.setQueryData(["cart"], cart),
  });
  if (product.isLoading) return <div className="page"><p role="status">Loading product…</p></div>;
  if (!product.data) return <div className="page"><p role="alert">Product not found.</p></div>;
  const selected = variantId || product.data.variants[0]?.id;
  return (
    <div className="page product-detail">
      <div className="detail-art">
        <ProductArt slug={product.data.slug} category={product.data.category} name={product.data.name} />
      </div>
      <section>
        <Link className="back-link" to="/">← Collection</Link>
        <p className="eyebrow">{product.data.category}</p>
        <h1>{product.data.name}</h1>
        <p>{product.data.description}</p>
        <label htmlFor="variant">Size</label>
        <select id="variant" value={selected} onChange={(e) => setVariantId(e.target.value)}>
          {product.data.variants.map((variant) => <option key={variant.id} value={variant.id}>{variant.name} · {money(variant.price_sgd_cents)} · {variant.available_stock} left</option>)}
        </select>
        <button className="button" disabled={!selected || add.isPending} onClick={() => add.mutate(selected)}>
          {add.isPending ? "Adding…" : "Add to bag"}
        </button>
        {add.isSuccess && <p role="status">Added. <Link to="/cart">View your bag</Link></p>}
        {add.isError && <p role="alert">{add.error.message}</p>}
      </section>
    </div>
  );
}
