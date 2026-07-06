import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { api } from "../api/client";

type Fields = { email: string; recipient_name: string; line1: string; city: string; postal_code: string; country_code: string };
type Result = { checkout_url: string; guest_lookup_token: string | null };

export function CheckoutPage() {
  const { register, handleSubmit, formState: { errors } } = useForm<Fields>({ defaultValues: { country_code: "SG" } });
  const checkout = useMutation({
    mutationFn: (values: Fields) => api<Result>("/checkout", {
      method: "POST",
      body: JSON.stringify({ email: values.email, shipping_address: { ...values, email: undefined } }),
    }),
    onSuccess: (result) => {
      if (result.guest_lookup_token) sessionStorage.setItem("guestOrderToken", result.guest_lookup_token);
      window.location.assign(result.checkout_url);
    },
  });
  return (
    <div className="page checkout">
      <section><p className="eyebrow">SECURE TEST CHECKOUT</p><h1>Where should we send it?</h1><p>Payments use Stripe test mode. No live charge will be made.</p></section>
      <form onSubmit={handleSubmit((data) => checkout.mutate(data))}>
        <label>Email<input type="email" {...register("email", { required: true })} /></label>
        {errors.email && <span role="alert">Email is required.</span>}
        <label>Recipient name<input {...register("recipient_name", { required: true })} /></label>
        <label>Address<input autoComplete="street-address" {...register("line1", { required: true })} /></label>
        <div className="field-pair"><label>City<input {...register("city", { required: true })} /></label><label>Postal code<input {...register("postal_code", { required: true })} /></label></div>
        <label>Country<select {...register("country_code")}><option value="SG">Singapore</option><option value="MY">Malaysia</option><option value="JP">Japan</option><option value="AU">Australia</option><option value="NZ">New Zealand</option></select></label>
        <button className="button full" disabled={checkout.isPending}>{checkout.isPending ? "Reserving stock…" : "Continue to Stripe test checkout"}</button>
        {checkout.isError && <p role="alert">{checkout.error.message}</p>}
      </form>
    </div>
  );
}
