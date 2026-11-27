import { MutationCache, QueryClient } from "@tanstack/react-query"

// После любой успешной записи — сбросить всё. В приложении один
// пользователь, и почти каждая запись двигает несколько экранов разом:
// операция меняет остаток счёта, сводку, бюджет, цели, получателей и
// корзину; платёж по кредиту — ещё и долг. Ручные списки ключей в
// каждом хуке отставали (счёт без сводки, бюджет без целей, кредит без
// бюджета), и цифры на том же экране показывали старое. Обновляются
// только открытые на экране запросы, остальные — при следующем входе.
export const queryClient: QueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
  mutationCache: new MutationCache({
    onSuccess: () => {
      void queryClient.invalidateQueries()
    },
  }),
})
