import { useMutation } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { api, ApiError, Order } from "../api/client";
import { OrderStatusView } from "../components/OrderStatusView";

export function TrackOrderPage() {
  const [displayNumber, setDisplayNumber] = useState("");
  const [email, setEmail] = useState("");
  const track = useMutation({
    mutationFn: () =>
      api<Order>(`/orders/track?${new URLSearchParams({ display_number: displayNumber, email })}`),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    track.mutate();
  }

  let errorMessage: string | null = null;
  if (track.isError) {
    const error = track.error;
    if (error instanceof ApiError && error.status === 404) {
      errorMessage = "No order matches that number and email.";
    } else if (error instanceof ApiError && error.status === 429) {
      errorMessage = "Too many attempts — please try again in a few minutes.";
    } else {
      errorMessage = error instanceof Error ? error.message : "Something went wrong.";
    }
  }

  return (
    <div className="page narrow">
      <p className="eyebrow">TRACK YOUR ORDER</p>
      <h1>Where&rsquo;s my matcha?</h1>
      {!track.data && (
        <form onSubmit={submit}>
          <label>
            Order number
            <input value={displayNumber} onChange={(e) => setDisplayNumber(e.target.value)} required />
          </label>
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <button className="button full" disabled={track.isPending}>
            {track.isPending ? "Looking up…" : "Track order"}
          </button>
          {errorMessage && <p role="alert">{errorMessage}</p>}
        </form>
      )}
      {track.data && <OrderStatusView order={track.data} />}
    </div>
  );
}
