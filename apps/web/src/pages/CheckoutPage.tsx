import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import {
  ApiError,
  api,
  Cart,
  CheckoutIn,
  CheckoutOut,
  formatSlotTime,
  humanizeError,
  PickupDay,
  Session,
} from "../api/client";
import {
  CONTACT_TELEGRAM_HANDLE,
  CONTACT_TELEGRAM_URL,
  CONTACT_WHATSAPP_HANDLE,
  CONTACT_WHATSAPP_URL,
  PICKUP_ADDRESS,
} from "../contact";

type Fields = {
  email: string;
  contact_handle: string;
  recipient_name: string;
  line1: string;
  city: string;
  postal_code: string;
  country_code: string;
};

const COUNTRY_SUGGESTIONS = ["SE", "NO", "DK", "FI", "DE", "GB", "SG", "MY", "JP", "AU", "NZ"];

export function CheckoutPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const cart = useQuery({ queryKey: ["cart"], queryFn: () => api<Cart>("/cart") });
  const session = useQuery({ queryKey: ["session"], queryFn: () => api<Session>("/auth/session") });
  const signedIn = !!session.data;
  const needsPickup = !!cart.data?.needs_pickup;
  const needsShipping = !!cart.data?.needs_shipping;

  const pickupDays = useQuery({
    queryKey: ["pickup-days"],
    queryFn: () => api<PickupDay[]>("/pickup-days"),
    enabled: needsPickup,
  });

  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [slotConflict, setSlotConflict] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<"online" | "pay_at_pickup">("online");
  // The API rejects pay_at_pickup whenever shipping is involved, so the choice
  // only makes sense — and is only offered — for a pickup-only cart.
  const showPaymentChoice = needsPickup && !needsShipping;

  // Default to the first available day once the pickup days load.
  useEffect(() => {
    if (!selectedDate && pickupDays.data && pickupDays.data.length > 0) {
      setSelectedDate(pickupDays.data[0].date);
    }
  }, [pickupDays.data, selectedDate]);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<Fields>({ defaultValues: { country_code: "SE", contact_handle: "" } });

  const payingAtPickup = showPaymentChoice && paymentMethod === "pay_at_pickup";

  const checkout = useMutation({
    mutationFn: (values: Fields) => {
      const payload: CheckoutIn = {
        // Signed-in checkouts never send an email — the backend always uses
        // the account's email on file and ignores this field anyway.
        email: signedIn ? undefined : values.email,
        payment_method: showPaymentChoice ? paymentMethod : "online",
      };
      if (values.contact_handle.trim()) {
        payload.contact_handle = values.contact_handle.trim();
      }
      if (needsShipping) {
        payload.shipping_address = {
          recipient_name: values.recipient_name,
          line1: values.line1,
          city: values.city,
          postal_code: values.postal_code,
          country_code: values.country_code.toUpperCase(),
        };
      }
      if (needsPickup && selectedSlot) {
        payload.pickup_at = selectedSlot;
      }
      return api<CheckoutOut>("/checkout", { method: "POST", body: JSON.stringify(payload) });
    },
    onSuccess: (result) => {
      if (result.guest_lookup_token) sessionStorage.setItem("guestOrderToken", result.guest_lookup_token);
      if (payingAtPickup) {
        // Nothing to pay online — skip the redirect and land straight on the
        // thank-you page instead of following checkout_url.
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
        }
      }
    },
  });

  if (cart.isLoading) {
    return (
      <div className="page">
        <p role="status">Loading checkout…</p>
      </div>
    );
  }

  const selectedDay = pickupDays.data?.find((day) => day.date === selectedDate);
  const canSubmit = !needsPickup || !!selectedSlot;

  return (
    <div className="page checkout">
      <section>
        <p className="eyebrow">SECURE CHECKOUT</p>
        <h1>Where do we reach you?</h1>
        <p>
          {payingAtPickup
            ? "Pay in person when you collect your order — cash, Revolut, or Swish transfer."
            : "Card payments are handled securely by Stripe."}
        </p>
        {needsPickup && (
          <p className="checkout-note">
            Pickup at {PICKUP_ADDRESS} — the details come with your confirmation email too.
          </p>
        )}
      </section>
      <form onSubmit={handleSubmit((data) => checkout.mutate(data))}>
        {signedIn ? (
          <p className="checkout-note">
            Receipt goes to {session.data!.user.email}.{" "}
            <Link to="/account">Not you? Sign out</Link>
          </p>
        ) : (
          <>
            <label>
              Email
              <input type="email" {...register("email", { required: true })} />
            </label>
            {errors.email && <span role="alert">Email is required.</span>}
          </>
        )}

        <label>
          Telegram or WhatsApp (optional)
          <input type="text" {...register("contact_handle")} />
        </label>
        <p className="hint">
          If email doesn't reach you, we'll message you there about your order or payment.
        </p>

        {needsPickup && (
          <div className="pickup-picker">
            <h2>Pickup time</h2>
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
                      {/* day.date is date-only; new Date() parses it as UTC midnight, so
                          format in UTC to keep the weekday from shifting for viewers
                          west of Greenwich. */}
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
          </div>
        )}

        {showPaymentChoice && (
          <div className="payment-choice" role="radiogroup" aria-label="Payment method">
            <h2>Payment</h2>
            <label className="radio-option">
              <input
                type="radio"
                name="payment_method"
                value="online"
                checked={paymentMethod === "online"}
                onChange={() => setPaymentMethod("online")}
              />
              Pay online now
            </label>
            <label className="radio-option">
              <input
                type="radio"
                name="payment_method"
                value="pay_at_pickup"
                checked={paymentMethod === "pay_at_pickup"}
                onChange={() => setPaymentMethod("pay_at_pickup")}
              />
              Pay at pickup — cash or Revolut/Swish transfer
            </label>
          </div>
        )}

        {needsShipping && (
          <>
            <label>
              Recipient name
              <input {...register("recipient_name", { required: true })} />
            </label>
            <label>
              Address
              <input autoComplete="street-address" {...register("line1", { required: true })} />
            </label>
            <div className="field-pair">
              <label>
                City
                <input {...register("city", { required: true })} />
              </label>
              <label>
                Postal code
                <input {...register("postal_code", { required: true })} />
              </label>
            </div>
            <label>
              Country
              <input
                list="country-suggestions"
                maxLength={2}
                style={{ textTransform: "uppercase" }}
                {...register("country_code", { required: true, minLength: 2, maxLength: 2 })}
              />
              <datalist id="country-suggestions">
                {COUNTRY_SUGGESTIONS.map((code) => (
                  <option value={code} key={code} />
                ))}
              </datalist>
            </label>
          </>
        )}

        <p className="contact-line">
          Payment trouble? Message us on Telegram{" "}
          <a href={CONTACT_TELEGRAM_URL} target="_blank" rel="noreferrer">{CONTACT_TELEGRAM_HANDLE}</a>{" "}
          or WhatsApp{" "}
          <a href={CONTACT_WHATSAPP_URL} target="_blank" rel="noreferrer">{CONTACT_WHATSAPP_HANDLE}</a>.
        </p>

        <button className="button full" disabled={checkout.isPending || !canSubmit}>
          {checkout.isPending
            ? "Just a moment…"
            : payingAtPickup
              ? "Confirm order — pay at pickup"
              : "Continue to payment"}
        </button>
        {needsPickup && !selectedSlot && (
          <p className="hint">Choose a pickup time above to continue.</p>
        )}
        {checkout.isError && !slotConflict && <p role="alert">{humanizeError(checkout.error)}</p>}
      </form>
    </div>
  );
}
