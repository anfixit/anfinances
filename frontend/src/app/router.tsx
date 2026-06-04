import { createBrowserRouter } from "react-router-dom"

import { HealthCheck } from "@/features/health/HealthCheck"

export const router = createBrowserRouter([
  {
    path: "/",
    element: <HealthCheck />,
  },
])
