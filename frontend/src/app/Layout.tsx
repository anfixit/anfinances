import { Menu, X } from "lucide-react"
import { useEffect, useState } from "react"
import { NavLink, Outlet } from "react-router-dom"

import { useAuth } from "@/auth/useAuth"
import { ThemeToggle } from "@/components/ThemeToggle"

interface NavItem {
  to: string
  label: string
  end?: boolean
}

const NAV_ITEMS: readonly NavItem[] = [
  { to: "/", label: "Главная", end: true },
  { to: "/transactions", label: "Операции" },
  { to: "/budgets", label: "Бюджет" },
  { to: "/recurring", label: "План-минимум" },
  { to: "/accounts", label: "Счета" },
  { to: "/categories", label: "Категории" },
  { to: "/currencies", label: "Валюты" },
  { to: "/settings", label: "Настройки" },
]

export function Layout() {
  const { user, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    if (!menuOpen) {
      return
    }

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"

    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [menuOpen])

  return (
    <div className="layout">
      <header className="header">
        <span className="brand">anfinances</span>

        <nav className="nav nav--desktop" aria-label="Основная навигация">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} {...(item.end === undefined ? {} : { end: item.end })}>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <span className="spacer" />
        <ThemeToggle />
        {user?.email && <span className="user">{user.email}</span>}
        <button
          type="button"
          className="link header-logout"
          onClick={() => void logout()}
        >
          Выйти
        </button>
        <button
          type="button"
          className="icon-button menu-toggle"
          aria-label={menuOpen ? "Закрыть меню" : "Открыть меню"}
          aria-expanded={menuOpen}
          aria-controls="mobile-navigation"
          onClick={() => setMenuOpen((value) => !value)}
        >
          {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
        </button>
      </header>

      {menuOpen && (
        <div
          className="mobile-nav-scrim"
          onClick={() => setMenuOpen(false)}
        >
          <nav
            id="mobile-navigation"
            className="mobile-nav"
            aria-label="Мобильная навигация"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mobile-nav__account">
              <span className="mobile-nav__title">Меню</span>
              {user?.email && (
                <span className="mobile-nav__email">{user.email}</span>
              )}
            </div>

            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                {...(item.end === undefined ? {} : { end: item.end })}
                onClick={() => setMenuOpen(false)}
              >
                {item.label}
              </NavLink>
            ))}

            <button
              type="button"
              className="mobile-nav__logout"
              onClick={() => void logout()}
            >
              Выйти
            </button>
          </nav>
        </div>
      )}

      <main className="page">
        <Outlet />
      </main>
    </div>
  )
}
