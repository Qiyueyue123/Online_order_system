import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AdminCatalogPage } from "../../api/client";
import { AdminProducts } from "./AdminProducts";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const productsPage: AdminCatalogPage = {
  items: [
    {
      id: "product-1",
      slug: "ceremonial-matcha",
      name: "Ceremonial Matcha",
      description: "Stone-ground matcha.",
      active: true,
      category: "tea",
      category_slug: "tea",
      images: [],
      variants: [
        {
          id: "variant-1",
          sku: "SKU-1",
          name: "30g tin",
          weight_grams: 30,
          price_cents: 3800,
          available_stock: 10,
          stock_on_hand: 12,
          stock_reserved: 2,
          active: true,
        },
      ],
    },
  ],
  page: 1,
  page_size: 100,
  total: 1,
};

describe("AdminProducts", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders products with their variants, seeded from stock_on_hand not available_stock", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(productsPage), { status: 200 })),
    );

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    expect(await screen.findByText("30g tin")).toBeInTheDocument();
    expect(screen.getByLabelText("30g tin price")).toHaveValue(38);
    expect(screen.getByLabelText("30g tin stock")).toHaveValue(12);
    expect(screen.getByText(/2 reserved/)).toBeInTheDocument();
    expect(screen.getByLabelText("Ceremonial Matcha name")).toHaveValue("Ceremonial Matcha");
  });

  it("sends the edited stock, active flag (and unchanged price) when a variant is saved", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "PATCH") {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.includes("/admin/products")) {
        return Promise.resolve(new Response(JSON.stringify(productsPage), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    const stockInput = await screen.findByLabelText("30g tin stock");
    fireEvent.change(stockInput, { target: { value: "25" } });
    fireEvent.click(screen.getByLabelText("30g tin active"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/variants/variant-1",
        expect.objectContaining({
          method: "PATCH",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
    const patchCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    const body = JSON.parse(patchCall![1]!.body as string);
    expect(body.stock_on_hand).toBe(25);
    expect(body.price_cents).toBe(3800);
    expect(body.active).toBe(false);
    expect(typeof body.reason).toBe("string");
    expect(body.reason.length).toBeGreaterThan(0);
  });

  it("sends edited name/description/active when a product is saved", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "PATCH") {
        return Promise.resolve(new Response(JSON.stringify(productsPage.items[0]), { status: 200 }));
      }
      if (url.includes("/admin/products")) {
        return Promise.resolve(new Response(JSON.stringify(productsPage), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    const nameInput = await screen.findByLabelText("Ceremonial Matcha name");
    fireEvent.change(nameInput, { target: { value: "Renamed Matcha" } });
    fireEvent.click(screen.getByLabelText("Ceremonial Matcha active"));
    fireEvent.click(screen.getByRole("button", { name: "Save product" }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/products/product-1",
        expect.objectContaining({
          method: "PATCH",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
    const patchCall = fetchMock.mock.calls.find(
      ([url, init]) => init?.method === "PATCH" && typeof url === "string" && url.includes("/admin/products/"),
    );
    const body = JSON.parse(patchCall![1]!.body as string);
    expect(body.name).toBe("Renamed Matcha");
    expect(body.description).toBe("Stone-ground matcha.");
    expect(body.active).toBe(false);
  });

  it("adds a new photo via the media manager form", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "POST" && url.includes("/images")) {
        return Promise.resolve(new Response(JSON.stringify(productsPage.items[0]), { status: 201 }));
      }
      if (url.includes("/admin/products")) {
        return Promise.resolve(new Response(JSON.stringify(productsPage), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    const urlInput = await screen.findByLabelText("Ceremonial Matcha new media URL");
    fireEvent.change(urlInput, { target: { value: "https://example.com/photo.jpg" } });
    fireEvent.change(screen.getByLabelText("Ceremonial Matcha new media alt text"), {
      target: { value: "A jar of matcha" },
    });
    fireEvent.change(screen.getByLabelText("Ceremonial Matcha new media type"), {
      target: { value: "video" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/products/product-1/images",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    const body = JSON.parse(postCall![1]!.body as string);
    expect(body).toEqual({
      url: "https://example.com/photo.jpg",
      alt_text: "A jar of matcha",
      caption: null,
      media_type: "video",
      position: 0,
    });
  });

  it("uploads a photo file via the media manager", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "POST" && url.includes("/images/upload")) {
        return Promise.resolve(new Response(JSON.stringify(productsPage.items[0]), { status: 201 }));
      }
      if (url.includes("/admin/products")) {
        return Promise.resolve(new Response(JSON.stringify(productsPage), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    const fileInput = await screen.findByLabelText("Ceremonial Matcha upload file");
    const file = new File(["fake-image-bytes"], "photo.jpg", { type: "image/jpeg" });
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/products/product-1/images/upload",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
    const uploadCall = fetchMock.mock.calls.find(([input]) =>
      (typeof input === "string" ? input : input.toString()).includes("/images/upload"),
    );
    const body = uploadCall![1]!.body as FormData;
    expect(body instanceof FormData).toBe(true);
    expect(body.get("file")).toBe(file);
  });

  it("sends the caption field when set on an upload", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "POST" && url.includes("/images/upload")) {
        return Promise.resolve(new Response(JSON.stringify(productsPage.items[0]), { status: 201 }));
      }
      if (url.includes("/admin/products")) {
        return Promise.resolve(new Response(JSON.stringify(productsPage), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    const fileInput = await screen.findByLabelText("Ceremonial Matcha upload file");
    const file = new File(["fake-image-bytes"], "photo.jpg", { type: "image/jpeg" });
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText("Ceremonial Matcha upload caption"), {
      target: { value: "Whisked fresh at pickup" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/products/product-1/images/upload",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const uploadCall = fetchMock.mock.calls.find(([input]) =>
      (typeof input === "string" ? input : input.toString()).includes("/images/upload"),
    );
    const body = uploadCall![1]!.body as FormData;
    expect(body.get("caption")).toBe("Whisked fresh at pickup");
  });

  it("patches an image caption from the media manager", async () => {
    const productWithImage: AdminCatalogPage = {
      ...productsPage,
      items: [
        {
          ...productsPage.items[0],
          images: [{ id: "image-1", url: "https://example.com/a.jpg", alt_text: "A jar", media_type: "image" }],
        },
      ],
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "PATCH") {
        return Promise.resolve(new Response(JSON.stringify(productWithImage.items[0]), { status: 200 }));
      }
      if (url.includes("/admin/products")) {
        return Promise.resolve(new Response(JSON.stringify(productWithImage), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    const captionInput = await screen.findByLabelText("Ceremonial Matcha media caption for A jar");
    fireEvent.change(captionInput, { target: { value: "Whisked to order" } });
    fireEvent.click(screen.getByRole("button", { name: "Save caption" }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/products/product-1/images/image-1",
        expect.objectContaining({
          method: "PATCH",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
    const patchCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    const body = JSON.parse(patchCall![1]!.body as string);
    expect(body).toEqual({ caption: "Whisked to order" });
  });

  it("removes a photo from the media manager", async () => {
    const productWithImage: AdminCatalogPage = {
      ...productsPage,
      items: [
        {
          ...productsPage.items[0],
          images: [{ id: "image-1", url: "https://example.com/a.jpg", alt_text: "A jar", media_type: "image" }],
        },
      ],
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "DELETE") {
        return Promise.resolve(new Response(JSON.stringify(productsPage.items[0]), { status: 200 }));
      }
      if (url.includes("/admin/products")) {
        return Promise.resolve(new Response(JSON.stringify(productWithImage), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    const removeButton = await screen.findByRole("button", { name: "Remove A jar" });
    fireEvent.click(removeButton);

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/products/product-1/images/image-1",
        expect.objectContaining({
          method: "DELETE",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
  });

  it("sends the reordered id array when moving a media item later", async () => {
    const productWithImages: AdminCatalogPage = {
      ...productsPage,
      items: [
        {
          ...productsPage.items[0],
          images: [
            { id: "image-1", url: "https://example.com/a.jpg", alt_text: "A jar", media_type: "image" },
            { id: "image-2", url: "https://example.com/b.jpg", alt_text: "A cup", media_type: "image" },
          ],
        },
      ],
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "PUT" && url.includes("/images/order")) {
        return Promise.resolve(new Response(JSON.stringify(productWithImages.items[0]), { status: 200 }));
      }
      if (url.includes("/admin/products")) {
        return Promise.resolve(new Response(JSON.stringify(productWithImages), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    const moveLater = await screen.findAllByRole("button", { name: "Move later" });
    fireEvent.click(moveLater[0]);

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/products/product-1/images/order",
        expect.objectContaining({
          method: "PUT",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
    const putCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    const body = JSON.parse(putCall![1]!.body as string);
    expect(body).toEqual({ image_ids: ["image-2", "image-1"] });
  });

  it("disables the first item's Move earlier and the last item's Move later button", async () => {
    const productWithImages: AdminCatalogPage = {
      ...productsPage,
      items: [
        {
          ...productsPage.items[0],
          images: [
            { id: "image-1", url: "https://example.com/a.jpg", alt_text: "A jar", media_type: "image" },
            { id: "image-2", url: "https://example.com/b.jpg", alt_text: "A cup", media_type: "image" },
          ],
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(productWithImages), { status: 200 })),
    );

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    const moveEarlier = await screen.findAllByRole("button", { name: "Move earlier" });
    const moveLater = await screen.findAllByRole("button", { name: "Move later" });
    expect(moveEarlier[0]).toBeDisabled();
    expect(moveLater[moveLater.length - 1]).toBeDisabled();
  });

  it("deletes a product after a two-step confirm", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "DELETE" && !url.includes("/images/")) {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.includes("/admin/products")) {
        return Promise.resolve(new Response(JSON.stringify(productsPage), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    await screen.findByRole("button", { name: "Delete product" });
    // Clicking once only asks for confirmation, no request yet.
    fireEvent.click(screen.getByRole("button", { name: "Delete product" }));
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/products/product-1",
        expect.objectContaining({
          method: "DELETE",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
  });

  it("shows the API's 409 message inline when deleting a product with order history", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "DELETE" && !url.includes("/images/")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ detail: "This product has order history — mark it inactive instead." }),
            { status: 409 },
          ),
        );
      }
      if (url.includes("/admin/products")) {
        return Promise.resolve(new Response(JSON.stringify(productsPage), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "Delete product" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));

    expect(
      await screen.findByText("This product has order history — mark it inactive instead."),
    ).toBeInTheDocument();
  });

  it("adds an option group and a choice, then PATCHes the full options array on Save options", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "PATCH") {
        return Promise.resolve(new Response(JSON.stringify(productsPage.items[0]), { status: 200 }));
      }
      if (url.includes("/admin/products")) {
        return Promise.resolve(new Response(JSON.stringify(productsPage), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    await screen.findByLabelText("Ceremonial Matcha name");
    fireEvent.click(screen.getByRole("button", { name: "Add option group" }));

    fireEvent.change(screen.getByLabelText("Ceremonial Matcha option group 1 label"), {
      target: { value: "Frothed milk" },
    });
    fireEvent.change(screen.getByLabelText("Ceremonial Matcha option group 1 choice 1 label"), {
      target: { value: "Regular" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add choice" }));
    fireEvent.change(screen.getByLabelText("Ceremonial Matcha option group 1 choice 2 label"), {
      target: { value: "Extra frothy" },
    });
    fireEvent.change(screen.getByLabelText("Ceremonial Matcha option group 1 choice 2 extra price"), {
      target: { value: "5" },
    });
    fireEvent.click(screen.getByLabelText("Ceremonial Matcha option group 1 choice 2 default"));

    fireEvent.click(screen.getByRole("button", { name: "Save options" }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/products/product-1",
        expect.objectContaining({
          method: "PATCH",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
    const patchCall = fetchMock.mock.calls.find(
      ([url, init]) => init?.method === "PATCH" && typeof url === "string" && url.includes("/admin/products/"),
    );
    const body = JSON.parse(patchCall![1]!.body as string);
    expect(body).toEqual({
      options: [
        {
          key: "frothed_milk",
          label: "Frothed milk",
          choices: [
            { value: "regular", label: "Regular", surcharge_cents: 0, default: false },
            { value: "extra_frothy", label: "Extra frothy", surcharge_cents: 500, default: true },
          ],
        },
      ],
    });
  });

  it("shows the server's 422 message inline when saving options fails validation", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "PATCH") {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "Validation failed" }), { status: 422 }),
        );
      }
      if (url.includes("/admin/products")) {
        return Promise.resolve(new Response(JSON.stringify(productsPage), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    await screen.findByLabelText("Ceremonial Matcha name");
    fireEvent.click(screen.getByRole("button", { name: "Add option group" }));
    fireEvent.change(screen.getByLabelText("Ceremonial Matcha option group 1 label"), {
      target: { value: "Frothed milk" },
    });
    fireEvent.change(screen.getByLabelText("Ceremonial Matcha option group 1 choice 1 label"), {
      target: { value: "Regular" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save options" }));

    expect(
      await screen.findByText("That doesn't look right — check the highlighted fields and try again."),
    ).toBeInTheDocument();
  });

  it("shows a validation error and does not submit when the new-product form is incomplete", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(productsPage), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);
    await screen.findByDisplayValue("Ceremonial Matcha");

    fireEvent.click(screen.getByRole("button", { name: "Create product" }));

    expect(await screen.findByText("Name is required.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });
});
