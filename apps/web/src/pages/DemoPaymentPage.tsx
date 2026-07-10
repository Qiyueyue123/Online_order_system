import { useMutation } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, formatPickup, humanizeError, money, Order } from "../api/client";


export function DemoPaymentPage() {
  const { orderId = "" } = useParams();
  const lookupToken = sessionStorage.getItem("guestOrderToken");
  const payment = useMutation({
    mutationFn: () =>
      api<Order>(
        `/demo/orders/${orderId}/pay${lookupToken ? `?lookup_token=${encodeURIComponent(lookupToken)}` : ""}`,
        { method: "POST" },
      ),
  });
  return (
    <div className="page narrow demo-payment">
      <p className="eyebrow">PAYMENT</p>
      {!payment.data ? (
        <>
          <h1>Confirm payment</h1>
          <p>Review and confirm your payment to finish the order.</p>
          <button className="button" disabled={payment.isPending} onClick={() => payment.mutate()}>
            {payment.isPending ? "Completing…" : "Complete payment"}
          </button>
          {payment.isError && <p role="alert">{humanizeError(payment.error)}</p>}
        </>
      ) : (
        <>
          <h1>Payment completed.</h1>
          <p>Order <strong>{payment.data.display_number}</strong> is paid for {money(payment.data.total_cents)}.</p>
          {payment.data.pickup_at && <p>Pickup {formatPickup(payment.data.pickup_at)}</p>}
          <Link className="button" to="/">Continue shopping</Link>
        </>
      )}
    </div>
  );
}
