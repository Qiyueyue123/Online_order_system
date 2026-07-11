import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ApiError,
  api,
  Cart,
  CartItemIn,
  CheckoutIn,
  CheckoutOut,
  DrinkOptions,
  formatDrinkOptions,
  formatSlotTime,
  humanizeError,
  money,
  PickupDay,
  Product,
  ProductPage as ProductPageResult,
  Session,
  StorefrontConfig,
} from "../api/client";
import {
  CONTACT_TELEGRAM_HANDLE,
  CONTACT_TELEGRAM_URL,
  CONTACT_WHATSAPP_HANDLE,
  CONTACT_WHATSAPP_URL,
  PICKUP_ADDRESS,
} from "../contact";
import { MediaCarousel } from "../components/MediaCarousel";
import { ProductArt } from "../components/ProductArt";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";

type Step = "menu" | "customise" | "contact" | "pickup" | "payment";

const STEP_INDEX: Record<Step, number> = { menu: 1, customise: 2, contact: 3, pickup: 4, payment: 5 };
const TOTAL_STEPS = 5;

const SUGAR_OPTIONS: DrinkOptions["sugar_g"][] = [2, 4, 6, 8];
const MATCHA_OPTIONS: DrinkOptions["matcha_g"][] = [4, 6];
const MILK_VOLUME_OPTIONS: DrinkOptions["milk_ml"][] = [130, 160];
// Must match app.services.cart.MATCHA_UPGRADE_SURCHARGE_CENTS — preview-only,
// the server is the source of truth for what's actually charged.
const MATCHA_UPGRADE_SURCHARGE_CENTS = 1500;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function ProgressBar({ step }: { step: Step }) {
  const pct = (STEP_INDEX[step] / TOTAL_STEPS) * 100;
  return (
    <div className="order-progress" aria-hidden="true">
      <div className="order-progress-bar" style={{ width: `${pct}%` }} />
    </div>
  );
}

function TopBar({ onBack }: { onBack: () => void }) {
  return (
    <div className="order-topbar">
      <button type="button" className="order-back" aria-label="Back" onClick={onBack}>
        ←
      </button>
      <span className="order-brand">QY &amp; YX&rsquo;S CAFE</span>
      <span className="order-topbar-spacer" aria-hidden="true" />
    </div>
  );
}

function MenuCard({
  product,
  selected,
  onSelect,
}: {
  product: Product;
  selected: boolean;
  onSelect: () => void;
}) {
  const variant = product.variants[0];
  const images = product.images;
  return (
    // A carousel with its own arrow/dot buttons can live inside this card, so
    // it can't be a native <button> (no nested interactive controls) — a
    // div with a button role plus keyboard handling stands in for one. The
    // carousel's own controls call stopPropagation, so they don't select
    // the card when clicked.
    <div
      role="button"
      tabIndex={0}
      className={`menu-card${selected ? " selected" : ""}`}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      aria-pressed={selected}
    >
      <span className="menu-card-art">
        {images.length > 0 ? (
          <MediaCarousel items={images} mediaClassName="menu-card-photo" label={`${product.name} photos`} />
        ) : (
          <ProductArt slug={product.slug} category={product.category} name={product.name} />
        )}
      </span>
      <span className="menu-card-body">
        <span className="menu-card-name">{product.name}</span>
        <span className="menu-card-price">
          {variant ? (product.variants.length > 1 ? `From ${money(variant.price_cents)}` : money(variant.price_cents)) : "Unavailable"}
        </span>
      </span>
      <span className={`check-circle${selected ? " active" : ""}`} aria-hidden="true">
        {selected ? "✓" : ""}
      </span>
    </div>
  );
}

export function OrderFlowPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const reducedMotion = usePrefersReducedMotion();

  const [step, setStep] = useState<Step>("menu");

  const products = useQuery({
    queryKey: ["products", "drinks"],
    queryFn: () => api<ProductPageResult>(`/products?${new URLSearchParams({ category: "drinks" })}`),
  });
  const cart = useQuery({ queryKey: ["cart"], queryFn: () => api<Cart>("/cart") });
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/auth/session"),
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 1,
  });
  const signedIn = !!session.data;
  const needsPickup = !!cart.data?.needs_pickup;
  const needsShipping = !!cart.data?.needs_shipping;

  const pickupDays = useQuery({
    queryKey: ["pickup-days"],
    queryFn: () => api<PickupDay[]>("/pickup-days"),
    enabled: step === "pickup" && needsPickup,
  });

  // Online payments are off until the owner trusts an automated confirmation
  // flow; if this call fails, default to disabled so the safe (pay-at-pickup
  // only) path wins.
  const storefrontConfig = useQuery({
    queryKey: ["storefront-config"],
    queryFn: () => api<StorefrontConfig>("/storefront-config"),
    retry: false,
  });
  const onlinePaymentsEnabled = storefrontConfig.data?.online_payments_enabled === true;

  // Customise step state
  const [customiseSlug, setCustomiseSlug] = useState<string | null>(null);
  const [variantId, setVariantId] = useState("");
  const [matchaG, setMatchaG] = useState<DrinkOptions["matcha_g"]>(4);
  const [whisk, setWhisk] = useState<DrinkOptions["whisk"]>("water");
  const [baseMilk, setBaseMilk] = useState<DrinkOptions["base_milk"]>("cow");
  const [milkMl, setMilkMl] = useState<DrinkOptions["milk_ml"]>(130);
  const [sugarG, setSugarG] = useState<DrinkOptions["sugar_g"]>(4);
  const [qty, setQty] = useState(1);

  // Contact step state
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState(false);
  const [contactHandle, setContactHandle] = useState("");

  // Pickup step state
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [slotConflict, setSlotConflict] = useState(false);

  // Payment step state
  const [paymentMethod, setPaymentMethod] = useState<"online" | "pay_at_pickup">("online");

  const canChoosePayment = needsPickup && !needsShipping;
  const showPaymentChoice = canChoosePayment && onlinePaymentsEnabled;
  // When online payments are off, a pickup-only cart always pays at pickup;
  // carts needing shipping keep the prior default (never offered
  // pay-at-pickup) and will 422 if online is disabled, which is acceptable
  // while shipped items are placeholders.
  const effectivePaymentMethod: "online" | "pay_at_pickup" = !onlinePaymentsEnabled
    ? canChoosePayment
      ? "pay_at_pickup"
      : "online"
    : showPaymentChoice
      ? paymentMethod
      : "online";
  const payingAtPickup = effectivePaymentMethod === "pay_at_pickup";

  const add = useMutation({
    mutationFn: (payload: CartItemIn) => api<Cart>("/cart/items", { method: "PUT", body: JSON.stringify(payload) }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["cart"], updated);
      setCustomiseSlug(null);
      setStep("menu");
    },
  });

  const removeItem = useMutation({
    mutationFn: (itemId: string) => api<Cart>(`/cart/items/${itemId}`, { method: "DELETE" }),
    onSuccess: (updated) => queryClient.setQueryData(["cart"], updated),
  });

  const checkout = useMutation({
    mutationFn: () => {
      const payload: CheckoutIn = {
        email: signedIn ? undefined : email.trim(),
        payment_method: effectivePaymentMethod,
      };
      if (contactHandle.trim()) payload.contact_handle = contactHandle.trim();
      if (needsPickup && selectedSlot) payload.pickup_at = selectedSlot;
      return api<CheckoutOut>("/checkout", { method: "POST", body: JSON.stringify(payload) });
    },
    onSuccess: (result) => {
      if (result.guest_lookup_token) sessionStorage.setItem("guestOrderToken", result.guest_lookup_token);
      if (payingAtPickup) {
        const params = new URLSearchParams({ order: result.display_number });
        if (selectedSlot) params.set("pickup", selectedSlot);
        navigate(`/thanks?${params.toString()}`);
        return;
      }
      window.location.assign(result.checkout_url);
    },
    onError: (error) => {
      setSlotConflict(false);
      if (error instanceof ApiError && (error.status === 409 || error.status === 422)) {
        const message = error.message.toLowerCase();
        if (message.includes("slot") || message.includes("pickup")) {
          setSlotConflict(true);
          setSelectedSlot(null);
          queryClient.invalidateQueries({ queryKey: ["pickup-days"] });
          setStep("pickup");
        }
      }
    },
  });

  function openCustomise(product: Product) {
    setCustomiseSlug(product.slug);
    setVariantId(product.variants[0]?.id ?? "");
    setMatchaG(4);
    setWhisk("water");
    setBaseMilk("cow");
    setMilkMl(130);
    setSugarG(4);
    setQty(1);
    setStep("customise");
  }

  function handleBack() {
    if (step === "menu") {
      navigate("/");
    } else if (step === "customise" || step === "contact") {
      setStep("menu");
    } else if (step === "pickup") {
      setStep("contact");
    } else if (step === "payment") {
      setStep(needsPickup ? "pickup" : "contact");
    }
  }

  function handleContactContinue() {
    if (!signedIn && !EMAIL_RE.test(email.trim())) {
      setEmailError(true);
      return;
    }
    setEmailError(false);
    setStep(needsPickup ? "pickup" : "payment");
  }

  const itemCount = cart.data?.items.reduce((sum, item) => sum + item.quantity, 0) ?? 0;
  const activeProduct = products.data?.items.find((p) => p.slug === customiseSlug);
  const activeVariant = activeProduct?.variants.find((v) => v.id === variantId) ?? activeProduct?.variants[0];
  const isDrink = activeProduct?.category_slug === "drinks";
  const surcharge = isDrink && matchaG === 6 ? MATCHA_UPGRADE_SURCHARGE_CENTS : 0;
  const unitPrice = (activeVariant?.price_cents ?? 0) + surcharge;
  const soldOut = !!activeVariant && activeVariant.available_stock === 0;

  const selectedDay = pickupDays.data?.find((day) => day.date === selectedDate);
  // Default to the first available day once the pickup days load (mirrors CheckoutPage).
  useEffect(() => {
    if (!selectedDate && pickupDays.data && pickupDays.data.length > 0) {
      setSelectedDate(pickupDays.data[0].date);
    }
  }, [pickupDays.data, selectedDate]);

  return (
    <div className="order-page">
      <TopBar onBack={handleBack} />
      <ProgressBar step={step} />
      <div className={`order-content order-step${reducedMotion ? " no-anim" : ""}`} key={step}>
        {step === "menu" && (
          <section aria-labelledby="order-step-heading">
            <h1 id="order-step-heading">What can we whisk for you?</h1>
            {products.isLoading && <p role="status">Loading the menu…</p>}
            {products.isError && <p role="alert">The menu could not be loaded. Please try again.</p>}
            <div className="menu-grid">
              {products.data?.items.map((product) => (
                <MenuCard
                  key={product.id}
                  product={product}
                  selected={!!cart.data?.items.some((item) => item.product_slug === product.slug)}
                  onSelect={() => openCustomise(product)}
                />
              ))}
            </div>
            {!!cart.data?.items.length && (
              <div className="order-lines">
                <h2>Your order</h2>
                {cart.data.items.map((item) => {
                  const options = formatDrinkOptions(item.options);
                  return (
                    <div className="order-line" key={item.id}>
                      <div>
                        <p className="order-line-name">{item.product_name}</p>
                        <p className="order-line-meta">
                          {item.variant_name} · Qty {item.quantity}
                          {options ? ` · ${options}` : ""}
                        </p>
                      </div>
                      <div className="order-line-end">
                        <strong>{money(item.line_total_cents)}</strong>
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => removeItem.mutate(item.id)}
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  );
                })}
                <p className="order-subtotal">Your subtotal: {money(cart.data.subtotal_cents)}</p>
              </div>
            )}
          </section>
        )}

        {step === "customise" && activeProduct && (
          <section aria-labelledby="order-step-heading">
            <div className="order-customise-art">
              {activeProduct.images.length > 0 ? (
                <MediaCarousel
                  items={activeProduct.images}
                  mediaClassName="order-customise-media"
                  label={`${activeProduct.name} photos`}
                  eagerFirst
                  showCaptions
                />
              ) : (
                <ProductArt slug={activeProduct.slug} category={activeProduct.category} name={activeProduct.name} />
              )}
            </div>
            <h1 id="order-step-heading">{activeProduct.name}</h1>
            {activeProduct.variants.length > 1 && (
              <>
                <label htmlFor="order-variant">Size</label>
                <select id="order-variant" value={variantId} onChange={(e) => setVariantId(e.target.value)}>
                  {activeProduct.variants.map((variant) => (
                    <option key={variant.id} value={variant.id}>
                      {variant.name} · {money(variant.price_cents)}
                    </option>
                  ))}
                </select>
              </>
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
              </div>
            )}
            <p className="option-label">Quantity</p>
            <div className="qty-stepper" role="group" aria-label="Quantity">
              <button type="button" onClick={() => setQty((q) => Math.max(1, q - 1))} disabled={qty <= 1} aria-label="Decrease quantity">
                −
              </button>
              <span aria-live="polite">{qty}</span>
              <button type="button" onClick={() => setQty((q) => Math.min(9, q + 1))} disabled={qty >= 9} aria-label="Increase quantity">
                +
              </button>
            </div>
            {add.isError && <p role="alert">{humanizeError(add.error)}</p>}
          </section>
        )}

        {step === "contact" && (
          <section aria-labelledby="order-step-heading">
            <h1 id="order-step-heading">Where do we reach you?</h1>
            {signedIn ? (
              <p className="checkout-note">
                Receipt goes to {session.data!.user.email}.{" "}
                <Link to="/account">Not you? Sign out</Link>
              </p>
            ) : (
              <>
                <label htmlFor="order-email">Email</label>
                <input
                  id="order-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
                {emailError && <span role="alert">Enter a valid email to continue.</span>}
              </>
            )}
            <label htmlFor="order-contact-handle">Telegram or WhatsApp (optional)</label>
            <input
              id="order-contact-handle"
              type="text"
              value={contactHandle}
              onChange={(e) => setContactHandle(e.target.value)}
            />
            <p className="hint">
              If email doesn't reach you, we'll message you there about your order or payment.
            </p>
          </section>
        )}

        {step === "pickup" && (
          <section aria-labelledby="order-step-heading">
            <h1 id="order-step-heading">When should we have it ready?</h1>
            <p className="checkout-note">Pickup at {PICKUP_ADDRESS}.</p>
            {pickupDays.isLoading && <p role="status">Loading pickup times…</p>}
            {!pickupDays.isLoading && pickupDays.data?.length === 0 && (
              <p className="pickup-empty">
                No pickup times are open right now — check back soon, or message us.
              </p>
            )}
            {!!pickupDays.data?.length && (
              <>
                <div className="pickup-days" role="group" aria-label="Pickup day">
                  {pickupDays.data.map((day) => (
                    <button
                      type="button"
                      key={day.date}
                      className={`chip${day.date === selectedDate ? " active" : ""}`}
                      onClick={() => {
                        setSelectedDate(day.date);
                        setSelectedSlot(null);
                      }}
                    >
                      {new Date(day.date).toLocaleDateString(undefined, {
                        timeZone: "UTC",
                        weekday: "short",
                        month: "short",
                        day: "numeric",
                      })}
                    </button>
                  ))}
                </div>
                {selectedDay && selectedDay.slots.length === 0 && (
                  <p className="pickup-empty">No times left on this day — pick another day above.</p>
                )}
                {selectedDay && selectedDay.slots.length > 0 && (
                  <div className="pickup-slots" role="group" aria-label="Pickup time slot">
                    {selectedDay.slots.map((slot) => (
                      <button
                        type="button"
                        key={slot.time}
                        className={`chip${slot.time === selectedSlot ? " active" : ""}`}
                        onClick={() => {
                          setSelectedSlot(slot.time);
                          setSlotConflict(false);
                        }}
                      >
                        {formatSlotTime(slot.time)}
                        {slot.remaining <= 2 && <span className="slot-remaining"> · {slot.remaining} left</span>}
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
            {slotConflict && (
              <p role="alert">
                That time just filled up — pick another. Times free up when unpaid orders expire, so check back soon.
              </p>
            )}
          </section>
        )}

        {step === "payment" && (
          <section aria-labelledby="order-step-heading">
            <h1 id="order-step-heading">Review &amp; pay</h1>
            <div className="order-lines">
              {cart.data?.items.map((item) => {
                const options = formatDrinkOptions(item.options);
                return (
                  <div className="order-line" key={item.id}>
                    <div>
                      <p className="order-line-name">{item.product_name}</p>
                      <p className="order-line-meta">
                        {item.variant_name} · Qty {item.quantity}
                        {options ? ` · ${options}` : ""}
                      </p>
                    </div>
                    <strong>{money(item.line_total_cents)}</strong>
                  </div>
                );
              })}
              <p className="order-subtotal">Subtotal: {money(cart.data?.subtotal_cents ?? 0)}</p>
            </div>
            {needsShipping ? (
              <p className="checkout-note">
                Your bag has items that ship — use the{" "}
                <Link to="/checkout">full checkout</Link>.
              </p>
            ) : (
              <>
                {showPaymentChoice && (
                  <div className="payment-choice" role="radiogroup" aria-label="Payment method">
                    <label className="radio-option">
                      <input
                        type="radio"
                        name="order-payment-method"
                        value="online"
                        checked={paymentMethod === "online"}
                        onChange={() => setPaymentMethod("online")}
                      />
                      Pay online now
                    </label>
                    <label className="radio-option">
                      <input
                        type="radio"
                        name="order-payment-method"
                        value="pay_at_pickup"
                        checked={paymentMethod === "pay_at_pickup"}
                        onChange={() => setPaymentMethod("pay_at_pickup")}
                      />
                      Pay at pickup — cash or Revolut transfer
                    </label>
                  </div>
                )}

                {!onlinePaymentsEnabled && canChoosePayment && (
                  <div className="payment-choice">
                    <h2>Payment</h2>
                    <p>
                      Pay when you collect — cash, or send a Revolut transfer and message us on
                      Telegram{" "}
                      <a href={CONTACT_TELEGRAM_URL} target="_blank" rel="noreferrer">{CONTACT_TELEGRAM_HANDLE}</a>{" "}
                      or WhatsApp{" "}
                      <a href={CONTACT_WHATSAPP_URL} target="_blank" rel="noreferrer">{CONTACT_WHATSAPP_HANDLE}</a>{" "}
                      so we can confirm it.
                    </p>
                  </div>
                )}
                <p className="contact-line">
                  Payment trouble? Message us on Telegram{" "}
                  <a href={CONTACT_TELEGRAM_URL} target="_blank" rel="noreferrer">{CONTACT_TELEGRAM_HANDLE}</a>{" "}
                  or WhatsApp{" "}
                  <a href={CONTACT_WHATSAPP_URL} target="_blank" rel="noreferrer">{CONTACT_WHATSAPP_HANDLE}</a>.
                </p>
                {checkout.isPending && <p role="status">Just a moment…</p>}
                {checkout.isError && !slotConflict && <p role="alert">{humanizeError(checkout.error)}</p>}
              </>
            )}
          </section>
        )}
      </div>

      {step === "menu" && (
        <div className="order-cta">
          <button
            type="button"
            className="button full"
            disabled={cart.isLoading || itemCount === 0}
            onClick={() => setStep("contact")}
          >
            Continue
          </button>
          {itemCount === 0 && !cart.isLoading && (
            <p className="hint">Add a drink above to continue.</p>
          )}
        </div>
      )}

      {step === "customise" && activeProduct && (
        <div className="order-cta">
          <button
            type="button"
            className="button full"
            disabled={!activeVariant || add.isPending || soldOut}
            onClick={() =>
              activeVariant &&
              add.mutate(
                isDrink
                  ? {
                      variant_id: activeVariant.id,
                      quantity: qty,
                      options: { matcha_g: matchaG, whisk, base_milk: baseMilk, milk_ml: milkMl, sugar_g: sugarG },
                    }
                  : { variant_id: activeVariant.id, quantity: qty },
              )
            }
          >
            {soldOut ? "Sold out" : add.isPending ? "Adding…" : `Add to order — ${money(unitPrice * qty)}`}
          </button>
        </div>
      )}

      {step === "contact" && (
        <div className="order-cta">
          <button type="button" className="button full" onClick={handleContactContinue}>
            Continue
          </button>
        </div>
      )}

      {step === "pickup" && (
        <div className="order-cta">
          <button
            type="button"
            className="button full"
            disabled={!selectedSlot}
            onClick={() => setStep("payment")}
          >
            Continue
          </button>
          {!selectedSlot && <p className="hint">Choose a pickup time above to continue.</p>}
        </div>
      )}

      {step === "payment" && !needsShipping && (
        <div className="order-cta">
          <button
            type="button"
            className="button full"
            disabled={checkout.isPending}
            onClick={() => checkout.mutate()}
          >
            {checkout.isPending
              ? "Just a moment…"
              : payingAtPickup
                ? "Confirm order — pay at pickup"
                : "Continue to payment"}
          </button>
        </div>
      )}
    </div>
  );
}
