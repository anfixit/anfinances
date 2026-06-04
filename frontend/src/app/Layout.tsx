import { NavLink, Outlet } from "react-router-dom"

import { useAuth } from "@/auth/useAuth"
import { ThemeToggle } from "@/components/ThemeToggle"

export function Layout() {
  const { user, logout } = useAuth()

  return (
    <div className="layout">
      <header className="header">
        <span className="brand">anfinances</span>
        <nav className="nav">
          <NavLink to="/">Главная</NavLink>
          <NavLink to="/transactions">Операции</NavLink>
          <NavLink to="/accounts">Счета</NavLink>
          <NavLink to="/categories">Категории</NavLink>
          <NavLink to="/currencies">Валюты</NavLink>
        </nav>
        <span className="spacer" />
        <ThemeToggle />
        <span className="user">{user?.email}</span>
        <button type="button" className="link" onClick={() => void logout()}>
          Выйти
        </button>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </div>
  )
}
