import { Link, useSearchParams } from "react-router-dom";
import { formatPickup } from "../api/client";
import {
  CONTACT_TELEGRAM_HANDLE,
  CONTACT_TELEGRAM_URL,
  CONTACT_WHATSAPP_HANDLE,
  CONTACT_WHATSAPP_URL,
  PICKUP_ADDRESS,
} from "../contact";

// Static confirmation shown after checkout — no API calls. Order details
// arrive by email, so this page just reassures the customer that the order
// went through; ?order and ?pickup are both optional and purely cosmetic.
export function ThankYouPage() {
  const [searchParams] = useSearchParams();
  const order = searchParams.get("order");
  const pickup = searchParams.get("pickup");

  return (
    <div className="page narrow thank-you">
      <p className="eyebrow">THANK YOU</p>
      <h1>{order ? <>Thanks — your order <strong>{order}</strong> is in.</> : "Thanks — your order is in."}</h1>
      {pickup && <p className="pickup-time">Pickup {formatPickup(pickup)} at {PICKUP_ADDRESS}</p>}
      <p>A confirmation email with the details is on its way.</p>
      <p>
        Paying by Revolut? Message us once you've sent it so we can confirm it arrived.
      </p>
      <p className="contact-line">
        Questions or payment issues? Telegram{" "}
        <a href={CONTACT_TELEGRAM_URL} target="_blank" rel="noreferrer">{CONTACT_TELEGRAM_HANDLE}</a>{" "}
        or WhatsApp{" "}
        <a href={CONTACT_WHATSAPP_URL} target="_blank" rel="noreferrer">{CONTACT_WHATSAPP_HANDLE}</a>.
      </p>
      <Link className="button" to="/">Back to home</Link>
    </div>
  );
}
