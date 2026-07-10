import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import {
  AdminCatalogPage,
  AdminCatalogProduct,
  AdminImageIn,
  AdminProductIn,
  AdminProductUpdateIn,
  AdminVariant,
  AdminVariantUpdateIn,
  Product,
  api,
  apiUpload,
  humanizeError,
} from "../../api/client";

type NewProductFields = {
  name: string;
  slug: string;
  category_slug: string;
  description: string;
  sku: string;
  variant_name: string;
  weight_grams: number;
  price_cents: number;
  stock_on_hand: number;
};

function VariantRow({
  variant,
  disabled,
  onSave,
}: {
  variant: AdminVariant;
  disabled: boolean;
  onSave: (variantId: string, priceCents: number, stock: number, active: boolean) => void;
}) {
  const [price, setPrice] = useState(String(variant.price_cents / 100));
  const [stock, setStock] = useState(String(variant.stock_on_hand));
  const [active, setActive] = useState(variant.active);

  return (
    <tr>
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
          min={variant.stock_reserved}
          value={stock}
          onChange={(event) => setStock(event.target.value)}
        />
        {variant.stock_reserved > 0 && (
          <span className="stock-reserved-note">{variant.stock_reserved} reserved</span>
        )}
      </td>
      <td>
        <label className="checkbox-label">
          <input
            aria-label={`${variant.name} active`}
            type="checkbox"
            checked={active}
            onChange={(event) => setActive(event.target.checked)}
          />
          Active
        </label>
      </td>
      <td>
        <button
          disabled={disabled}
          onClick={() => onSave(variant.id, Math.round(Number(price) * 100), Number(stock), active)}
        >
          Save
        </button>
      </td>
    </tr>
  );
}

function ProductEditor({
  product,
  disabled,
  onSave,
}: {
  product: AdminCatalogProduct;
  disabled: boolean;
  onSave: (productId: string, body: AdminProductUpdateIn) => void;
}) {
  const [name, setName] = useState(product.name);
  const [description, setDescription] = useState(product.description);
  const [active, setActive] = useState(product.active);

  return (
    <div className="admin-product-header">
      <div className="field-pair">
        <label>
          Name
          <input
            aria-label={`${product.name} name`}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className="checkbox-label">
          <input
            aria-label={`${product.name} active`}
            type="checkbox"
            checked={active}
            onChange={(event) => setActive(event.target.checked)}
          />
          Active (visible to customers)
        </label>
      </div>
      <label>
        Description
        <textarea
          aria-label={`${product.name} description`}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>
      <button
        disabled={disabled}
        onClick={() => onSave(product.id, { name, description, active })}
      >
        Save product
      </button>
    </div>
  );
}

function MediaManager({
  product,
  disabled,
  uploading,
  onAdd,
  onRemove,
  onUpload,
}: {
  product: AdminCatalogProduct;
  disabled: boolean;
  uploading: boolean;
  onAdd: (productId: string, body: AdminImageIn) => void;
  onRemove: (productId: string, imageId: string) => void;
  onUpload: (productId: string, file: File) => void;
}) {
  const [url, setUrl] = useState("");
  const [altText, setAltText] = useState("");
  const [mediaType, setMediaType] = useState<AdminImageIn["media_type"]>("image");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const uploadInputRef = useRef<HTMLInputElement>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!url.trim()) return;
    onAdd(product.id, {
      url: url.trim(),
      alt_text: altText.trim(),
      media_type: mediaType,
      position: product.images.length,
    });
    setUrl("");
    setAltText("");
    setMediaType("image");
  }

  function submitUpload(event: FormEvent) {
    event.preventDefault();
    if (!uploadFile) return;
    onUpload(product.id, uploadFile);
    setUploadFile(null);
    if (uploadInputRef.current) uploadInputRef.current.value = "";
  }

  return (
    <div className="admin-media-manager">
      <p className="option-label">Photos &amp; videos</p>
      {product.images.length > 0 && (
        <div className="admin-media-list">
          {product.images.map((image) => (
            <div className="admin-media-item" key={image.id}>
              {image.media_type === "video" ? (
                <video src={image.url} muted playsInline />
              ) : (
                <img src={image.url} alt="" loading="lazy" />
              )}
              <button
                type="button"
                aria-label={`Remove ${image.alt_text || (image.media_type === "video" ? "video" : "photo")}`}
                disabled={disabled}
                onClick={() => onRemove(product.id, image.id)}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
      <form className="admin-media-form field-pair" onSubmit={submit}>
        <label>
          Photo or video URL
          <input
            aria-label={`${product.name} new media URL`}
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://…"
          />
        </label>
        <label>
          Alt text
          <input
            aria-label={`${product.name} new media alt text`}
            value={altText}
            onChange={(event) => setAltText(event.target.value)}
          />
        </label>
        <label>
          Type
          <select
            aria-label={`${product.name} new media type`}
            value={mediaType}
            onChange={(event) => setMediaType(event.target.value as AdminImageIn["media_type"])}
          >
            <option value="image">Photo</option>
            <option value="video">Video</option>
          </select>
        </label>
        <button type="submit" disabled={disabled || !url.trim()}>
          Add
        </button>
      </form>
      <form className="admin-media-upload-form field-pair" onSubmit={submitUpload}>
        <label>
          Upload a photo or video
          <input
            ref={uploadInputRef}
            aria-label={`${product.name} upload file`}
            type="file"
            accept="image/*,video/*"
            onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <button type="submit" disabled={disabled || uploading || !uploadFile}>
          {uploading ? "Uploading…" : "Upload"}
        </button>
      </form>
      <p className="field-hint">
        Photos up to 15 MB, videos up to 100 MB / 90 seconds — most formats accepted.
      </p>
    </div>
  );
}

export function AdminProducts({ csrfToken }: { csrfToken: string }) {
  const queryClient = useQueryClient();
  const products = useQuery({
    queryKey: ["admin", "products"],
    queryFn: () => api<AdminCatalogPage>("/admin/products?page_size=100"),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "products"] });

  const updateVariant = useMutation({
    mutationFn: ({ variantId, body }: { variantId: string; body: AdminVariantUpdateIn }) =>
      api<void>(`/admin/variants/${variantId}`, {
        method: "PATCH",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body),
      }),
    onSuccess: invalidate,
  });

  const updateProduct = useMutation({
    mutationFn: ({ productId, body }: { productId: string; body: AdminProductUpdateIn }) =>
      api<Product>(`/admin/products/${productId}`, {
        method: "PATCH",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body),
      }),
    onSuccess: invalidate,
  });

  const addImage = useMutation({
    mutationFn: ({ productId, body }: { productId: string; body: AdminImageIn }) =>
      api<AdminCatalogProduct>(`/admin/products/${productId}/images`, {
        method: "POST",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body),
      }),
    onSuccess: invalidate,
  });

  const uploadImage = useMutation({
    mutationFn: ({ productId, file }: { productId: string; file: File }) => {
      const body = new FormData();
      body.append("file", file);
      return apiUpload<AdminCatalogProduct>(`/admin/products/${productId}/images/upload`, body, {
        headers: { "X-CSRF-Token": csrfToken },
      });
    },
    onSuccess: invalidate,
  });

  const removeImage = useMutation({
    mutationFn: ({ productId, imageId }: { productId: string; imageId: string }) =>
      api<AdminCatalogProduct>(`/admin/products/${productId}/images/${imageId}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": csrfToken },
      }),
    onSuccess: invalidate,
  });

  const createProduct = useMutation({
    mutationFn: (body: AdminProductIn) =>
      api<Product>("/admin/products", {
        method: "POST",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      invalidate();
      reset();
    },
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<NewProductFields>({
    defaultValues: { weight_grams: 100, price_cents: 0, stock_on_hand: 0 },
  });

  function saveVariant(variantId: string, priceCents: number, stock: number, active: boolean) {
    updateVariant.mutate({
      variantId,
      body: {
        price_cents: priceCents,
        stock_on_hand: stock,
        active,
        reason: "Admin update via storefront",
      },
    });
  }

  function saveProduct(productId: string, body: AdminProductUpdateIn) {
    updateProduct.mutate({ productId, body });
  }

  function addProductImage(productId: string, body: AdminImageIn) {
    addImage.mutate({ productId, body });
  }

  function removeProductImage(productId: string, imageId: string) {
    removeImage.mutate({ productId, imageId });
  }

  function uploadProductImage(productId: string, file: File) {
    uploadImage.mutate({ productId, file });
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
          price_cents: Math.round(Number(fields.price_cents) * 100),
          stock_on_hand: Number(fields.stock_on_hand),
        },
      ],
    });
  }

  return (
    <div className="admin-products">
      {updateVariant.isError && <p role="alert">{humanizeError(updateVariant.error)}</p>}
      {updateProduct.isError && <p role="alert">{humanizeError(updateProduct.error)}</p>}
      {addImage.isError && <p role="alert">{humanizeError(addImage.error)}</p>}
      {uploadImage.isError && <p role="alert">{humanizeError(uploadImage.error)}</p>}
      {removeImage.isError && <p role="alert">{humanizeError(removeImage.error)}</p>}
      {products.isLoading && <p role="status">Loading products…</p>}
      {products.data?.items.map((product) => (
        <div className="admin-product-group" key={product.id}>
          <ProductEditor
            product={product}
            disabled={updateProduct.isPending}
            onSave={saveProduct}
          />
          <MediaManager
            product={product}
            disabled={addImage.isPending || uploadImage.isPending || removeImage.isPending}
            uploading={uploadImage.isPending}
            onAdd={addProductImage}
            onRemove={removeProductImage}
            onUpload={uploadProductImage}
          />
          <table>
            <thead>
              <tr>
                <th>Variant</th>
                <th>Price (SEK)</th>
                <th>Stock</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {product.variants.map((variant) => (
                <VariantRow
                  key={variant.id}
                  variant={variant}
                  disabled={updateVariant.isPending}
                  onSave={saveVariant}
                />
              ))}
            </tbody>
          </table>
        </div>
      ))}

      <h2>Add a new product</h2>
      <form onSubmit={handleSubmit(submitNewProduct)}>
        <label>
          Name
          <input {...register("name", { required: true })} />
        </label>
        {errors.name && <span role="alert">Name is required.</span>}
        <label>
          Web address (e.g. iced-hojicha)
          <input {...register("slug", { required: true })} />
        </label>
        {errors.slug && <span role="alert">Web address is required.</span>}
        <label>
          Category
          <input {...register("category_slug")} />
        </label>
        <label>
          Description
          <input {...register("description", { required: true })} />
        </label>
        {errors.description && <span role="alert">Description is required.</span>}
        <div className="field-pair">
          <label>
            Product code (SKU)
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
            Price (SEK)
            <input
              type="number"
              step="0.01"
              min="0"
              {...register("price_cents", { required: true, valueAsNumber: true })}
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
        {createProduct.isError && <p role="alert">{humanizeError(createProduct.error)}</p>}
      </form>
    </div>
  );
}
