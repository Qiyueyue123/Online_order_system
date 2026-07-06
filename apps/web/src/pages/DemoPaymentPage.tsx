import { useMutation } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, money, Order } from "../api/client";

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
      <p className="eyebrow">LOCAL DEMONSTRATION</p>
      {!payment.data ? (
        <>
          <h1>Simulate payment</h1>
          <p>This page replaces Stripe while developing locally. It never charges a card.</p>
          <button className="button" disabled={payment.isPending} onClick={() => payment.mutate()}>
            {payment.isPending ? "Completing…" : "Complete test payment"}
          </button>
          {payment.isError && <p role="alert">{payment.error.message}</p>}
        </>
      ) : (
        <>
          <h1>Payment completed.</h1>
          <p>Order <strong>{payment.data.display_number}</strong> is paid for {money(payment.data.total_cents)}.</p>
          <Link className="button" to="/">Continue shopping</Link>
        </>
      )}
    </div>
  );
}
