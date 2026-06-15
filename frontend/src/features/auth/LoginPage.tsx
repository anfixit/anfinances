import { zodResolver } from "@hookform/resolvers/zod"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { Navigate } from "react-router-dom"

import { loginSchema } from "@/auth/schemas"
import type { LoginInput } from "@/auth/schemas"
import { useAuth } from "@/auth/useAuth"
import { AppError } from "@/lib/api/errors"

export function LoginPage() {
  const { status, login } = useAuth()
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput>({ resolver: zodResolver(loginSchema) })

  if (status === "authenticated") {
    return <Navigate to="/" replace />
  }

  const submit = handleSubmit(async (data) => {
    setFormError(null)
    try {
      await login(data.email, data.password)
    } catch (err) {
      setFormError(err instanceof AppError ? err.message : "Не удалось войти")
    }
  })

  return (
    <main className="page">
      <h1>Вход</h1>
      <form onSubmit={(e) => void submit(e)} className="form">
        <label className="field">
          <span>Email</span>
          <input type="email" autoComplete="username" {...register("email")} />
          {errors.email && (
            <span className="error">{errors.email.message}</span>
          )}
        </label>
        <label className="field">
          <span>Пароль</span>
          <input
            type="password"
            autoComplete="current-password"
            {...register("password")}
          />
          {errors.password && (
            <span className="error">{errors.password.message}</span>
          )}
        </label>
        {formError && <p className="error">{formError}</p>}
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Вхожу…" : "Войти"}
        </button>
      </form>
    </main>
  )
}
