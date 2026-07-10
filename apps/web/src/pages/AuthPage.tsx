import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { api, humanizeError, Session } from "../api/client";

type Fields = { name: string; email: string; password: string };

export function AuthPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { register, handleSubmit, formState: { errors } } = useForm<Fields>();
  const auth = useMutation({
    mutationFn: (values: Fields) =>
      api<Session>(mode === "login" ? "/auth/login" : "/auth/register", {
        method: "POST",
        body: JSON.stringify(
          mode === "login"
            ? { email: values.email, password: values.password }
            : values,
        ),
      }),
    onSuccess: async (session) => {
      queryClient.setQueryData(["session"], session);
      await queryClient.invalidateQueries({ queryKey: ["cart"] });
      navigate("/account");
    },
  });
  return (
    <div className="page auth-page">
      <section>
        <p className="eyebrow">YOUR ACCOUNT</p>
        <h1>{mode === "login" ? "Welcome back." : "Create an account."}</h1>
        <p>We only use your account to keep your order history and send receipts.</p>
      </section>
      <form onSubmit={handleSubmit((values) => auth.mutate(values))}>
        {mode === "register" && (
          <label>Name
            <input autoComplete="name" {...register("name", { required: true })} />
          </label>
        )}
        <label>Email
          <input type="email" autoComplete="email" {...register("email", { required: true })} />
        </label>
        <label>Password
          <input
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            {...register("password", { required: true, minLength: mode === "register" ? 10 : 1 })}
          />
        </label>
        {errors.password && <p role="alert">Use at least 10 characters when registering.</p>}
        <button className="button full" disabled={auth.isPending}>
          {auth.isPending ? "Please wait…" : mode === "login" ? "Sign in" : "Register"}
        </button>
        {auth.isError && <p role="alert">{humanizeError(auth.error)}</p>}
        <button
          className="text-button"
          type="button"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? "Need an account? Register" : "Already registered? Sign in"}
        </button>
      </form>
    </div>
  );
}
