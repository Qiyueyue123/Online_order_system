import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import {
  AdminProductIn,
  AdminVariantUpdateIn,
  api,
  Product,
  ProductPage,
  Variant,
} from "../../api/client";

type NewProductFields = {
  name: string;
  slug: string;
  category_slug: string;
  description: string;
  sku: string;
  variant_name: string;
  weight_grams: number;
  price_sgd_cents: number;
  stock_on_hand: number;
};

function VariantRow({
  productName,
  variant,
  disabled,
  onSave,
}: {
  productName: string;
  variant: Variant;
  disabled: boolean;
  onSave: (variantId: string, priceCents: number, stock: number) => void;
}) {
  const [price, setPrice] = useState(String(variant.price_sgd_cents / 100));
  const [stock, setStock] = useState(String(variant.available_stock));

  return (
    <tr>
      <td>{productName}</td>
      <td>{variant.name}</td>
      <td>
        <input
          aria-label={`${variant.name} price`}
          type="number"
          step="0.01"
          min="0"
          value={price}
          onChange={(event) => setPrice(event.target.value)}
        />
      </td>
      <td>
        <input
          aria-label={`${variant.name} stock`}
          type="number"
          min="0"
          value={stock}
          onChange={(event) => setStock(event.target.value)}
        />
      </td>
      <td>
        <button
          disabled={disabled}
          onClick={() => onSave(variant.id, Math.round(Number(price) * 100), Number(stock))}
        >
          Save
        </button>
      </td>
    </tr>
  );
}

export function AdminProducts({ csrfToken }: { csrfToken: string }) {
  const queryClient = useQueryClient();
  const products = useQuery({
    queryKey: ["admin", "products"],
    queryFn: () => api<ProductPage>("/products?page_size=100"),
  });

  const updateVariant = useMutation({
    mutationFn: ({ variantId, body }: { variantId: string; body: AdminVariantUpdateIn }) =>
      api<void>(`/admin/variants/${variantId}`, {
        method: "PATCH",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "products"] }),
  });

  const createProduct = useMutation({
    mutationFn: (body: AdminProductIn) =>
      api<Product>("/admin/products", {
        method: "POST",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
      reset();
    },
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<NewProductFields>({
    defaultValues: { weight_grams: 100, price_sgd_cents: 0, stock_on_hand: 0 },
  });

  function saveVariant(variantId: string, priceCents: number, stock: number) {
    updateVariant.mutate({
      variantId,
      body: {
        price_sgd_cents: priceCents,
        stock_on_hand: stock,
        reason: "Admin update via storefront",
      },
    });
  }

  function submitNewProduct(fields: NewProductFields) {
    createProduct.mutate({
      slug: fields.slug,
      name: fields.name,
      description: fields.description,
      category_slug: fields.category_slug || null,
      variants: [
        {
          sku: fields.sku,
          name: fields.variant_name,
          weight_grams: Number(fields.weight_grams),
          price_sgd_cents: Math.round(Number(fields.price_sgd_cents) * 100),
          stock_on_hand: Number(fields.stock_on_hand),
        },
      ],
    });
  }

  return (
    <div className="admin-products">
      {updateVariant.isError && <p role="alert">{updateVariant.error.message}</p>}
      {products.isLoading && <p role="status">Loading products…</p>}
      <table>
        <thead>
          <tr>
            <th>Product</th>
            <th>Variant</th>
            <th>Price (SGD)</th>
            <th>Stock</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {products.data?.items.flatMap((product) =>
            product.variants.map((variant) => (
              <VariantRow
                key={variant.id}
                productName={product.name}
                variant={variant}
                disabled={updateVariant.isPending}
                onSave={saveVariant}
              />
            )),
          )}
        </tbody>
      </table>

      <h2>Add a new product</h2>
      <form onSubmit={handleSubmit(submitNewProduct)}>
        <label>
          Name
          <input {...register("name", { required: true })} />
        </label>
        {errors.name && <span role="alert">Name is required.</span>}
        <label>
          Slug
          <input {...register("slug", { required: true })} />
        </label>
        {errors.slug && <span role="alert">Slug is required.</span>}
        <label>
          Category slug
          <input {...register("category_slug")} />
        </label>
        <label>
          Description
          <input {...register("description", { required: true })} />
        </label>
        {errors.description && <span role="alert">Description is required.</span>}
        <div className="field-pair">
          <label>
            Variant SKU
            <input {...register("sku", { required: true })} />
          </label>
          <label>
            Variant name
            <input {...register("variant_name", { required: true })} />
          </label>
        </div>
        <div className="field-pair">
          <label>
            Weight (grams)
            <input type="number" min="0" {...register("weight_grams", { required: true, valueAsNumber: true })} />
          </label>
          <label>
            Price (SGD)
            <input
              type="number"
              step="0.01"
              min="0"
              {...register("price_sgd_cents", { required: true, valueAsNumber: true })}
            />
          </label>
        </div>
        <label>
          Stock on hand
          <input type="number" min="0" {...register("stock_on_hand", { required: true, valueAsNumber: true })} />
        </label>
        <button className="button" disabled={createProduct.isPending}>
          {createProduct.isPending ? "Creating…" : "Create product"}
        </button>
        {createProduct.isError && <p role="alert">{createProduct.error.message}</p>}
      </form>
    </div>
  );
}
