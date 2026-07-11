import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import {
  AdminCatalogPage,
  AdminCatalogProduct,
  AdminImage,
  AdminImageIn,
  AdminImageOrderIn,
  AdminImageUpdateIn,
  AdminProductIn,
  AdminProductUpdateIn,
  AdminVariant,
  AdminVariantUpdateIn,
  OptionGroupIn,
  Product,
  api,
  apiUpload,
  humanizeError,
} from "../../api/client";

// Turns a free-text label into a slug-safe key/value: lowercase, non
// [a-z0-9] runs collapsed to a single underscore, no leading/trailing
// underscore. Falls back to "option" so an empty label never produces an
// empty (and therefore invalid) key.
function slugify(text: string): string {
  const slug = text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return slug || "option";
}

// Appends _2, _3, … until the candidate isn't already in `taken`, so two
// choices/groups with the same label don't collide on the same slug.
function uniqueSlug(base: string, taken: Set<string>): string {
  let candidate = base;
  let suffix = 2;
  while (taken.has(candidate)) {
    candidate = `${base}_${suffix}`;
    suffix += 1;
  }
  return candidate;
}

type ChoiceDraft = {
  value: string;
  label: string;
  surchargeKr: string;
  default: boolean;
  isNew: boolean;
};

type GroupDraft = {
  key: string;
  label: string;
  choices: ChoiceDraft[];
  isNew: boolean;
};

function groupsFromProduct(product: AdminCatalogProduct): GroupDraft[] {
  return (product.options ?? []).map((group) => ({
    key: group.key,
    label: group.label,
    isNew: false,
    choices: group.choices.map((choice) => ({
      value: choice.value,
      label: choice.label,
      surchargeKr: String(choice.surcharge_cents / 100),
      default: choice.default,
      isNew: false,
    })),
  }));
}

// Only a group/choice error blocks the save outright (labels, at-least-one-
// choice) — a missing default is auto-fixed in buildOptionsPayload rather
// than rejected, per spec.
function validateGroups(groups: GroupDraft[]): string | null {
  for (const group of groups) {
    if (!group.label.trim()) return "Every option group needs a label.";
    if (group.choices.length === 0) return `"${group.label}" needs at least one choice.`;
    for (const choice of group.choices) {
      if (!choice.label.trim()) return `Every choice in "${group.label}" needs a label.`;
    }
  }
  return null;
}

function buildOptionsPayload(groups: GroupDraft[]): OptionGroupIn[] {
  const takenKeys = new Set(groups.filter((group) => !group.isNew).map((group) => group.key));
  return groups.map((group) => {
    let key = group.key;
    if (group.isNew) {
      key = uniqueSlug(slugify(group.label), takenKeys);
      takenKeys.add(key);
    }
    const takenValues = new Set(group.choices.filter((choice) => !choice.isNew).map((choice) => choice.value));
    const hasDefault = group.choices.some((choice) => choice.default);
    const choices = group.choices.map((choice, index) => {
      let value = choice.value;
      if (choice.isNew) {
        value = uniqueSlug(slugify(choice.label), takenValues);
        takenValues.add(value);
      }
      return {
        value,
        label: choice.label.trim(),
        surcharge_cents: Math.round(Number(choice.surchargeKr || "0") * 100),
        // If nothing was marked default (e.g. the default choice got
        // removed), fall back to the first choice rather than reject.
        default: hasDefault ? choice.default : index === 0,
      };
    });
    return { key, label: group.label.trim(), choices };
  });
}

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

function MediaCaptionEditor({
  productName,
  image,
  disabled,
  onSave,
}: {
  productName: string;
  image: AdminImage;
  disabled: boolean;
  onSave: (caption: string) => void;
}) {
  const [caption, setCaption] = useState(image.caption ?? "");
  const dirty = caption !== (image.caption ?? "");

  return (
    <form
      className="admin-media-caption-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(caption.trim());
      }}
    >
      <label>
        Caption
        <input
          aria-label={`${productName} media caption for ${image.alt_text || image.media_type}`}
          value={caption}
          onChange={(event) => setCaption(event.target.value)}
          placeholder="Shown under this photo or video"
        />
      </label>
      <button type="submit" disabled={disabled || !dirty}>
        Save caption
      </button>
    </form>
  );
}

function MediaManager({
  product,
  disabled,
  uploading,
  savingCaption,
  reordering,
  onAdd,
  onRemove,
  onUpload,
  onUpdateCaption,
  onReorder,
}: {
  product: AdminCatalogProduct;
  disabled: boolean;
  uploading: boolean;
  savingCaption: boolean;
  reordering: boolean;
  onAdd: (productId: string, body: AdminImageIn) => void;
  onRemove: (productId: string, imageId: string) => void;
  onUpload: (productId: string, file: File, caption: string) => void;
  onUpdateCaption: (productId: string, imageId: string, caption: string) => void;
  onReorder: (productId: string, imageIds: string[]) => void;
}) {
  const [url, setUrl] = useState("");
  const [altText, setAltText] = useState("");
  const [caption, setCaption] = useState("");
  const [mediaType, setMediaType] = useState<AdminImageIn["media_type"]>("image");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadCaption, setUploadCaption] = useState("");
  const uploadInputRef = useRef<HTMLInputElement>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!url.trim()) return;
    onAdd(product.id, {
      url: url.trim(),
      alt_text: altText.trim(),
      caption: caption.trim() || null,
      media_type: mediaType,
      position: product.images.length,
    });
    setUrl("");
    setAltText("");
    setCaption("");
    setMediaType("image");
  }

  function submitUpload(event: FormEvent) {
    event.preventDefault();
    if (!uploadFile) return;
    onUpload(product.id, uploadFile, uploadCaption.trim());
    setUploadFile(null);
    setUploadCaption("");
    if (uploadInputRef.current) uploadInputRef.current.value = "";
  }

  function moveImage(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= product.images.length) return;
    const ids = product.images.map((image) => image.id);
    [ids[index], ids[target]] = [ids[target], ids[index]];
    onReorder(product.id, ids);
  }

  return (
    <div className="admin-media-manager">
      <p className="option-label">Photos &amp; videos</p>
      {product.images.length > 0 && (
        <div className="admin-media-list">
          {product.images.map((image, index) => {
            const label = image.alt_text || (image.media_type === "video" ? "video" : "photo");
            return (
              <div className="admin-media-item" key={image.id}>
                {image.media_type === "video" ? (
                  <video src={image.url} muted playsInline />
                ) : (
                  <img src={image.url} alt="" loading="lazy" />
                )}
                <MediaCaptionEditor
                  productName={product.name}
                  image={image}
                  disabled={savingCaption}
                  onSave={(next) => onUpdateCaption(product.id, image.id, next)}
                />
                <div className="admin-media-order-actions">
                  <button
                    type="button"
                    aria-label="Move earlier"
                    disabled={disabled || reordering || index === 0}
                    onClick={() => moveImage(index, -1)}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label="Move later"
                    disabled={disabled || reordering || index === product.images.length - 1}
                    onClick={() => moveImage(index, 1)}
                  >
                    ↓
                  </button>
                </div>
                <button
                  type="button"
                  aria-label={`Remove ${label}`}
                  disabled={disabled}
                  onClick={() => onRemove(product.id, image.id)}
                >
                  Remove
                </button>
              </div>
            );
          })}
        </div>
      )}
      {product.images.length > 1 && (
        <p className="field-hint">First item is the cover — it's shown as the storefront card thumbnail.</p>
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
          Caption
          <input
            aria-label={`${product.name} new media caption`}
            value={caption}
            onChange={(event) => setCaption(event.target.value)}
            placeholder="Shown under this photo or video"
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
        <label>
          Caption
          <input
            aria-label={`${product.name} upload caption`}
            value={uploadCaption}
            onChange={(event) => setUploadCaption(event.target.value)}
            placeholder="Shown under this photo or video"
          />
        </label>
        <button type="submit" disabled={disabled || uploading || !uploadFile}>
          {uploading ? "Uploading…" : "Upload"}
        </button>
      </form>
      <p className="field-hint">
        Photos up to 15 MB, videos up to 500 MB / 90 seconds — most formats accepted.
        Videos over 100 MB are compressed automatically.
      </p>
    </div>
  );
}

function OptionsEditor({
  product,
  pending,
  error,
  success,
  onSave,
}: {
  product: AdminCatalogProduct;
  pending: boolean;
  error: string | null;
  success: boolean;
  onSave: (productId: string, options: OptionGroupIn[]) => void;
}) {
  const [groups, setGroups] = useState<GroupDraft[]>(() => groupsFromProduct(product));
  const [localError, setLocalError] = useState<string | null>(null);

  function updateGroup(groupIndex: number, label: string) {
    setGroups((current) => current.map((group, i) => (i === groupIndex ? { ...group, label } : group)));
  }

  function updateChoice(groupIndex: number, choiceIndex: number, patch: Partial<ChoiceDraft>) {
    setGroups((current) =>
      current.map((group, i) =>
        i === groupIndex
          ? { ...group, choices: group.choices.map((choice, ci) => (ci === choiceIndex ? { ...choice, ...patch } : choice)) }
          : group,
      ),
    );
  }

  function setDefault(groupIndex: number, choiceIndex: number) {
    setGroups((current) =>
      current.map((group, i) =>
        i === groupIndex
          ? { ...group, choices: group.choices.map((choice, ci) => ({ ...choice, default: ci === choiceIndex })) }
          : group,
      ),
    );
  }

  function addChoice(groupIndex: number) {
    setGroups((current) =>
      current.map((group, i) =>
        i === groupIndex
          ? {
              ...group,
              choices: [
                ...group.choices,
                { value: "", label: "", surchargeKr: "0", default: group.choices.length === 0, isNew: true },
              ],
            }
          : group,
      ),
    );
  }

  function removeChoice(groupIndex: number, choiceIndex: number) {
    setGroups((current) =>
      current.map((group, i) =>
        i === groupIndex ? { ...group, choices: group.choices.filter((_, ci) => ci !== choiceIndex) } : group,
      ),
    );
  }

  function addGroup() {
    setGroups((current) => [
      ...current,
      {
        key: "",
        label: "",
        isNew: true,
        choices: [{ value: "", label: "", surchargeKr: "0", default: true, isNew: true }],
      },
    ]);
  }

  function removeGroup(groupIndex: number) {
    setGroups((current) => current.filter((_, i) => i !== groupIndex));
  }

  function submit() {
    const validationError = validateGroups(groups);
    if (validationError) {
      setLocalError(validationError);
      return;
    }
    setLocalError(null);
    onSave(product.id, buildOptionsPayload(groups));
  }

  return (
    <div className="admin-options-editor">
      <p className="option-label">Customisation options</p>
      <p className="field-hint">
        These are the buttons customers see on the product page. Extra price is added per drink.
      </p>
      {groups.map((group, groupIndex) => (
        <div className="admin-options-group" key={groupIndex}>
          <label>
            Group label
            <input
              aria-label={`${product.name} option group ${groupIndex + 1} label`}
              value={group.label}
              onChange={(event) => updateGroup(groupIndex, event.target.value)}
              title={group.key || undefined}
            />
          </label>
          <table>
            <thead>
              <tr>
                <th>Choice</th>
                <th>Extra price (SEK)</th>
                <th>Default</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {group.choices.map((choice, choiceIndex) => (
                <tr key={choiceIndex}>
                  <td>
                    <input
                      aria-label={`${product.name} option group ${groupIndex + 1} choice ${choiceIndex + 1} label`}
                      value={choice.label}
                      onChange={(event) => updateChoice(groupIndex, choiceIndex, { label: event.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      aria-label={`${product.name} option group ${groupIndex + 1} choice ${choiceIndex + 1} extra price`}
                      value={choice.surchargeKr}
                      onChange={(event) =>
                        updateChoice(groupIndex, choiceIndex, { surchargeKr: event.target.value })
                      }
                    />
                  </td>
                  <td>
                    <input
                      type="radio"
                      name={`admin-option-default-${product.id}-${groupIndex}`}
                      aria-label={`${product.name} option group ${groupIndex + 1} choice ${choiceIndex + 1} default`}
                      checked={choice.default}
                      onChange={() => setDefault(groupIndex, choiceIndex)}
                    />
                  </td>
                  <td>
                    <button
                      type="button"
                      aria-label={`Remove ${product.name} option group ${groupIndex + 1} choice ${choiceIndex + 1}`}
                      onClick={() => removeChoice(groupIndex, choiceIndex)}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="admin-options-group-actions">
            <button type="button" onClick={() => addChoice(groupIndex)}>
              Add choice
            </button>
            <button type="button" className="button-danger" onClick={() => removeGroup(groupIndex)}>
              Remove group
            </button>
          </div>
        </div>
      ))}
      <div className="admin-options-group-actions">
        <button type="button" onClick={addGroup}>
          Add option group
        </button>
        <button type="button" className="button" disabled={pending} onClick={submit}>
          {pending ? "Saving…" : "Save options"}
        </button>
      </div>
      {localError && <p role="alert">{localError}</p>}
      {!localError && error && <p role="alert">{error}</p>}
      {!localError && !error && success && <p role="status">Options saved.</p>}
    </div>
  );
}

function DeleteProductControl({
  product,
  pending,
  error,
  onDelete,
}: {
  product: AdminCatalogProduct;
  pending: boolean;
  error: string | null;
  onDelete: (productId: string) => void;
}) {
  const [confirming, setConfirming] = useState(false);

  return (
    <div className="admin-delete-product">
      {!confirming ? (
        <button
          type="button"
          className="button-danger"
          onClick={() => setConfirming(true)}
        >
          Delete product
        </button>
      ) : (
        <span className="admin-delete-confirm">
          Really delete?{" "}
          <button
            type="button"
            className="button-danger"
            disabled={pending}
            onClick={() => onDelete(product.id)}
          >
            Yes, delete
          </button>{" "}
          <button type="button" disabled={pending} onClick={() => setConfirming(false)}>
            Cancel
          </button>
        </span>
      )}
      {error && <p role="alert">{error}</p>}
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

  // Separate from updateProduct: an options change also has to bust the
  // public product queries (ProductPage, OrderFlowPage's menu) since
  // shoppers see these chips directly, not just the admin list.
  const updateOptions = useMutation({
    mutationFn: ({ productId, body }: { productId: string; body: AdminProductUpdateIn }) =>
      api<Product>(`/admin/products/${productId}`, {
        method: "PATCH",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["products"] });
      queryClient.invalidateQueries({ queryKey: ["product"] });
    },
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
    mutationFn: ({ productId, file, caption }: { productId: string; file: File; caption: string }) => {
      const body = new FormData();
      body.append("file", file);
      if (caption) body.append("caption", caption);
      return apiUpload<AdminCatalogProduct>(`/admin/products/${productId}/images/upload`, body, {
        headers: { "X-CSRF-Token": csrfToken },
      });
    },
    onSuccess: invalidate,
  });

  const updateImageCaption = useMutation({
    mutationFn: ({
      productId,
      imageId,
      body,
    }: {
      productId: string;
      imageId: string;
      body: AdminImageUpdateIn;
    }) =>
      api<AdminCatalogProduct>(`/admin/products/${productId}/images/${imageId}`, {
        method: "PATCH",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body),
      }),
    onSuccess: invalidate,
  });

  const reorderImages = useMutation({
    mutationFn: ({ productId, body }: { productId: string; body: AdminImageOrderIn }) =>
      api<AdminCatalogProduct>(`/admin/products/${productId}/images/order`, {
        method: "PUT",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body),
      }),
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

  const deleteProduct = useMutation({
    mutationFn: (productId: string) =>
      api<void>(`/admin/products/${productId}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": csrfToken },
      }),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
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

  function saveOptions(productId: string, options: OptionGroupIn[]) {
    updateOptions.mutate({ productId, body: { options } });
  }

  function addProductImage(productId: string, body: AdminImageIn) {
    addImage.mutate({ productId, body });
  }

  function removeProductImage(productId: string, imageId: string) {
    removeImage.mutate({ productId, imageId });
  }

  function uploadProductImage(productId: string, file: File, caption: string) {
    uploadImage.mutate({ productId, file, caption });
  }

  function updateProductImageCaption(productId: string, imageId: string, caption: string) {
    updateImageCaption.mutate({ productId, imageId, body: { caption: caption || null } });
  }

  function reorderProductImages(productId: string, imageIds: string[]) {
    reorderImages.mutate({ productId, body: { image_ids: imageIds } });
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
      {updateImageCaption.isError && <p role="alert">{humanizeError(updateImageCaption.error)}</p>}
      {reorderImages.isError && <p role="alert">{humanizeError(reorderImages.error)}</p>}
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
            savingCaption={updateImageCaption.isPending}
            reordering={reorderImages.isPending}
            onAdd={addProductImage}
            onRemove={removeProductImage}
            onUpload={uploadProductImage}
            onUpdateCaption={updateProductImageCaption}
            onReorder={reorderProductImages}
          />
          <OptionsEditor
            // Remount when the server's option data actually changes (e.g.
            // right after a successful save) so drafted keys/values sync up;
            // unrelated refetches (a variant save elsewhere) leave this
            // identical and don't clobber an in-progress edit.
            key={JSON.stringify(product.options ?? [])}
            product={product}
            pending={updateOptions.isPending && updateOptions.variables?.productId === product.id}
            error={
              updateOptions.isError && updateOptions.variables?.productId === product.id
                ? humanizeError(updateOptions.error)
                : null
            }
            success={updateOptions.isSuccess && updateOptions.variables?.productId === product.id}
            onSave={saveOptions}
          />
          <DeleteProductControl
            product={product}
            pending={deleteProduct.isPending && deleteProduct.variables === product.id}
            error={
              deleteProduct.isError && deleteProduct.variables === product.id
                ? humanizeError(deleteProduct.error)
                : null
            }
            onDelete={(productId) => deleteProduct.mutate(productId)}
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
