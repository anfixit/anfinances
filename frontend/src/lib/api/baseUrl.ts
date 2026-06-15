// Единый базовый URL API. Дефолт на случай отсутствия .env, чтобы dev
// не падал молча (запрос мимо прокси отдавал бы HTML вместо JSON).
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1"
